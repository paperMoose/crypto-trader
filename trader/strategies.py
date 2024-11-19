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
        logger.info(f"Executing range strategy for {strategy.name}")
        config = strategy.config
        
        # Check existing orders
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
        stop_loss_order = next((o for o in strategy.orders if o.order_type == OrderType.STOP_LIMIT_SELL), None)
        
        logger.info(f"Current orders - Buy: {buy_order and buy_order.status}, "
                   f"Sell: {len(sell_orders)} orders, "
                   f"Stop Loss: {stop_loss_order and stop_loss_order.status}")
        
        # Place buy order at support if none exists
        if not buy_order:
            logger.info(f"Placing buy order at support price {config['support_price']}")
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
            session.commit()
            logger.info(f"Buy order placed successfully: {order.order_id}")
            return
        
        # If buy order is filled, place sell and stop loss orders
        if buy_order.status == OrderState.FILLED:
            # Place sell order at resistance if none exists
            if not sell_orders:
                logger.info(f"Buy order filled, placing sell order at resistance {config['resistance_price']}")
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
                logger.info(f"Sell order placed successfully: {order.order_id}")
            
            # Place stop loss order if none exists
            if not stop_loss_order:
                logger.info(f"Placing stop loss order at {config['stop_loss_price']}")
                response = await self.client.place_order(
                    symbol=Symbol(strategy.symbol),
                    amount=config['amount'],
                    price=config['stop_loss_price'],
                    side=OrderSide.SELL,
                    order_type=GeminiOrderType.EXCHANGE_STOP_LIMIT,
                    stop_price=str(float(config['stop_loss_price']) * 1.01)  # Set stop slightly above limit
                )
                
                order = Order(
                    order_id=response.order_id,
                    status=OrderState.PLACED,
                    amount=config['amount'],
                    price=config['stop_loss_price'],
                    side=OrderSide.SELL.value,
                    symbol=strategy.symbol,
                    order_type=OrderType.STOP_LIMIT_SELL,
                    strategy_id=strategy.id,
                    stop_price=str(float(config['stop_loss_price']) * 1.01)
                )
                session.add(order)
                logger.info(f"Stop loss order placed successfully: {order.order_id}")
        
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
                    strategy_id=strategy.id,
                    stop_price=str(float(config['stop_loss']) * 1.01)
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
        logger.info("Strategy Manager initialized")
    
    async def create_strategy(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Create and save a new trading strategy"""
        logger.info(f"Creating strategy: {strategy_data['name']}")
        strategy = save_strategy(strategy_data, session=self.session)
        self.session.commit()
        logger.info(f"Strategy created successfully: {strategy.id}")
        return strategy
    
    async def monitor_strategies(self):
        """Monitor and execute all active strategies"""
        logger.info("Starting strategy monitor loop")
        while True:
            try:
                strategies = get_active_strategies(session=self.session)
                logger.info(f"Found {len(strategies)} active strategies")
                
                for strategy in strategies:
                    logger.debug(f"Checking strategy: {strategy.name}")
                    current_time = datetime.utcnow()
                    
                    if (current_time - strategy.last_checked_at).seconds >= strategy.check_interval:
                        logger.info(f"Executing strategy: {strategy.name} (Type: {strategy.type})")
                        
                        # Update order statuses
                        logger.debug(f"Updating orders for strategy: {strategy.name}")
                        await self.update_orders(strategy)
                        
                        # Execute strategy logic
                        await self.strategies[strategy.type].execute(strategy, self.session)
                        
                        # Update last checked timestamp
                        strategy.last_checked_at = current_time
                        self.session.add(strategy)
                        self.session.commit()
                        logger.info(f"Strategy execution completed: {strategy.name}")

                await asyncio.sleep(1)  # Prevent tight loop
                
            except Exception as e:
                logger.error(f"Error monitoring strategies: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # Back off on error
    
    async def update_orders(self, strategy):
        try:
            logger.info(f"Updating orders for strategy: {strategy.name}")
            for order in strategy.orders:
                logger.debug(f"Checking order status: {order.order_id}")
                response = await self.client.check_order_status(order.order_id)
                
                # Only update if we got a valid response with a status
                if hasattr(response, 'status') and response.status is not None:
                    old_status = order.status
                    order_data = {
                        "status": response.status
                    }
                    update_order(
                        order.order_id, 
                        session=self.session, 
                        **order_data
                    )
                    logger.info(f"Order {order.order_id} status updated: {old_status} -> {response.status}")
            
            # Only commit if all updates were successful
            self.session.commit()
            logger.debug("Order updates committed successfully")
            
        except Exception as e:
            # Roll back on error to maintain consistency
            self.session.rollback()
            logger.error(f"Error updating orders: {str(e)}", exc_info=True)