import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from trader.models import OrderType, TradingStrategy, Order, StrategyState, OrderState, StrategyType
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType as GeminiOrderType
from trader.database import (
    save_strategy, 
    get_active_strategies, 
    update_strategy,
    save_order,
    update_order
)

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    def __init__(self, client: GeminiClient):
        self.client = client
    
    @abstractmethod
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute strategy logic"""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration"""
        pass

class RangeStrategy(BaseStrategy):
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'support_price', 'resistance_price', 'amount', 'stop_loss_price'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute range trading strategy"""
        config = strategy.config
        
        # Check existing orders
        buy_orders = [o for o in strategy.orders if o.side == OrderSide.BUY.value]
        sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
        
        # Place buy order at support if none exists
        if not buy_orders:
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=config['amount'],
                price=config['support_price'],
                side=OrderSide.BUY,
                order_type=GeminiOrderType.EXCHANGE_LIMIT
            )
            
            order = Order(
                order_id=response.order_id,
                status=OrderState.PLACED,
                amount=config['amount'],
                price=config['support_price'],
                side=OrderSide.BUY.value,
                symbol=strategy.symbol,
                order_type=OrderType.LIMIT_BUY,
                strategy_id=strategy.id
            )
            session.add(order)
        
        # Place sell order at resistance if none exists
        if not sell_orders:
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=config['amount'],
                price=config['resistance_price'],
                side=OrderSide.SELL,
                order_type=GeminiOrderType.EXCHANGE_LIMIT
            )
            
            order = Order(
                order_id=response.order_id,
                status=OrderState.PLACED,
                amount=config['amount'],
                price=config['resistance_price'],
                side=OrderSide.SELL.value,
                symbol=strategy.symbol,
                order_type=OrderType.LIMIT_SELL,
                strategy_id=strategy.id
            )
            session.add(order)
        
        session.commit()

class BreakoutStrategy(BaseStrategy):
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'breakout_price', 'amount', 'take_profit_1', 'take_profit_2', 'stop_loss'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute breakout strategy"""
        session.refresh(strategy)
        config = strategy.config
        
        # Check if initial buy order exists
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        
        if not buy_order:
            # Place initial breakout buy order
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=config['amount'],
                price=config['breakout_price'],
                side=OrderSide.BUY,
                order_type=GeminiOrderType.EXCHANGE_STOP_LIMIT,
                stop_price=str(float(config['breakout_price']) * 0.99)
            )
            
            buy_order = Order(
                order_id=response.order_id,
                status=OrderState.PLACED,
                amount=config['amount'],
                price=config['breakout_price'],
                side=OrderSide.BUY.value,
                symbol=strategy.symbol,
                order_type=OrderType.STOP_LIMIT_BUY,
                strategy_id=strategy.id
            )
            session.add(buy_order)
            session.commit()
            return
        
        # If buy order is filled, place take profit and stop loss orders
        if buy_order.status == OrderState.FILLED:
            sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
            if not sell_orders:  # Only place sell orders if none exist
                # Place take profit orders
                for tp_price in [config['take_profit_1'], config['take_profit_2']]:
                    response = await self.client.place_order(
                        symbol=Symbol(strategy.symbol),
                        amount=str(float(config['amount']) / 2),  # Split amount between take profits
                        price=tp_price,
                        side=OrderSide.SELL,
                        order_type=GeminiOrderType.EXCHANGE_LIMIT
                    )
                    
                    order = Order(
                        order_id=response.order_id,
                        status=OrderState.PLACED,
                        amount=str(float(config['amount']) / 2),
                        price=tp_price,
                        side=OrderSide.SELL.value,
                        symbol=strategy.symbol,
                        order_type=OrderType.LIMIT_SELL,
                        strategy_id=strategy.id
                    )
                    session.add(order)
                
                # Place stop loss order
                response = await self.client.place_order(
                    symbol=Symbol(strategy.symbol),
                    amount=config['amount'],
                    price=config['stop_loss'],
                    side=OrderSide.SELL,
                    order_type=GeminiOrderType.EXCHANGE_STOP_LIMIT,
                    stop_price=str(float(config['stop_loss']) * 1.01)
                )
                
                order = Order(
                    order_id=response.order_id,
                    status=OrderState.PLACED,
                    amount=config['amount'],
                    price=config['stop_loss'],
                    side=OrderSide.SELL.value,
                    symbol=strategy.symbol,
                    order_type=OrderType.STOP_LIMIT_SELL,
                    strategy_id=strategy.id
                )
                session.add(order)
                session.commit()

class StrategyManager:
    def __init__(self, session: Session, client: GeminiClient):
        self.session = session
        self.client = client
        self.strategies = {
            StrategyType.RANGE: RangeStrategy(client),
            StrategyType.BREAKOUT: BreakoutStrategy(client)
        }
    
    async def create_strategy(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Create and save a new trading strategy"""
        strategy = save_strategy(strategy_data, session=self.session)
        self.session.commit()
        return strategy
    
    async def monitor_strategies(self):
        """Monitor and execute all active strategies"""
        while True:
            try:
                strategies = get_active_strategies(self.session.get_bind())
                
                for strategy in strategies:
                    if (datetime.utcnow() - strategy.last_checked_at).seconds >= strategy.check_interval:
                        await self.update_orders(strategy, self.session.get_bind())
                        await self.strategies[strategy.type].execute(strategy, self.session)
                        
                        # Update last checked timestamp
                        update_strategy(
                            strategy.id,
                            engine=self.session.get_bind(),
                            last_checked_at=datetime.utcnow()
                        )
                        self.session.commit()

                await asyncio.sleep(1)  # Prevent tight loop
                
            except Exception as e:
                logger.error(f"Error monitoring strategies: {str(e)}")
                await asyncio.sleep(5)  # Back off on error
    
    async def update_orders(self, strategy, session):
        for order in strategy.orders:
            response = await self.client.check_order_status(order.order_id)
            if response.status != order.status:
                order_data = {
                    "status": response.status
                }
                update_order(order.order_id, session=session, **order_data)
        session.commit()