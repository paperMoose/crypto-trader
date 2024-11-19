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
    def __init__(self, client: GeminiClient):
        super().__init__(client)
        self.logger = logging.getLogger("RangeStrategy")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'support_price', 'resistance_price', 'amount', 'stop_loss_price'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute range trading strategy"""
        # Get current price first for logging
        current_price = await self.client.get_price(Symbol(strategy.symbol))
        self.logger.info(f"Executing strategy for {strategy.name} (Current Price: ${current_price})")
        config = strategy.config
        
        # Check existing orders
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        sell_orders = [o for o in strategy.orders 
                      if o.side == OrderSide.SELL.value 
                      and o.status.value not in ["filled", "cancelled"]]
        
        self.logger.info(f"Current orders - Buy: {buy_order and buy_order.status}, "
                        f"Sell: {len(sell_orders)} orders")
        
        # Place buy order at support if none exists
        if not buy_order:
            self.logger.info(f"Placing buy order at support price {config['support_price']}")
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=config['amount'],
                price=config['support_price'],
                side=OrderSide.BUY,
                order_type=GeminiOrderType.EXCHANGE_LIMIT
            )
            
            order = Order(
                order_id=response.order_id,
                status=OrderState.ACCEPTED,
                amount=config['amount'],
                price=config['support_price'],
                side=OrderSide.BUY.value,
                symbol=strategy.symbol,
                order_type=OrderType.LIMIT_BUY,
                strategy_id=strategy.id
            )
            session.add(order)
            session.commit()
            return
        
        # If buy order is filled, place sell order and monitor stop loss
        if buy_order.status == OrderState.FILLED:
            # Place sell order at resistance if none exists
            if not sell_orders:
                self.logger.info(f"Buy order filled, placing sell order at resistance {config['resistance_price']}")
                response = await self.client.place_order(
                    symbol=Symbol(strategy.symbol),
                    amount=config['amount'],
                    price=config['resistance_price'],
                    side=OrderSide.SELL,
                    order_type=GeminiOrderType.EXCHANGE_LIMIT
                )
                
                order = Order(
                    order_id=response.order_id,
                    status=OrderState.ACCEPTED,
                    amount=config['amount'],
                    price=config['resistance_price'],
                    side=OrderSide.SELL.value,
                    symbol=strategy.symbol,
                    order_type=OrderType.LIMIT_SELL,
                    strategy_id=strategy.id
                )
                session.add(order)
                session.commit()
                return
            
            # Monitor for stop loss if we have active sell order
            if sell_orders:
                # Already have current price from above
                
                # Check if price has hit stop loss
                if float(current_price) <= float(config['stop_loss_price']):
                    self.logger.info(f"Price ${current_price} hit stop loss at ${config['stop_loss_price']}, executing market sell")
                    
                    # Cancel existing sell order
                    for order in sell_orders:
                        await self.client.cancel_order(order.order_id)
                    
                    # Place market sell order
                    response = await self.client.place_order(
                        symbol=Symbol(strategy.symbol),
                        amount=config['amount'],
                        price=str(float(config['stop_loss_price']) * 0.99),  # Slightly below stop to ensure execution
                        side=OrderSide.SELL,
                        order_type=GeminiOrderType.EXCHANGE_LIMIT
                    )
                    
                    order = Order(
                        order_id=response.order_id,
                        status=OrderState.ACCEPTED,
                        amount=config['amount'],
                        price=str(float(config['stop_loss_price']) * 0.99),
                        side=OrderSide.SELL.value,
                        symbol=strategy.symbol,
                        order_type=OrderType.LIMIT_SELL,
                        strategy_id=strategy.id
                    )
                    session.add(order)
                    session.commit()

class BreakoutStrategy(BaseStrategy):
    def __init__(self, client: GeminiClient):
        super().__init__(client)
        self.logger = logging.getLogger("BreakoutStrategy")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'breakout_price', 'amount', 'take_profit_1', 'take_profit_2', 'stop_loss'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute breakout strategy"""
        session.refresh(strategy)
        config = strategy.config
        
        # Get current price first for logging
        current_price = await self.client.get_price(Symbol(strategy.symbol))
        self.logger.info(f"Executing strategy for {strategy.name} (Current Price: ${current_price})")
        
        # Check if initial buy order exists
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        
        if not buy_order:
            self.logger.info(f"Placing breakout buy order at ${config['breakout_price']}")
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=config['amount'],
                price=config['breakout_price'],
                side=OrderSide.BUY,
                order_type=GeminiOrderType.EXCHANGE_LIMIT
            )
            
            buy_order = Order(
                order_id=response.order_id,
                status=OrderState.ACCEPTED,
                amount=config['amount'],
                price=config['breakout_price'],
                side=OrderSide.BUY.value,
                symbol=strategy.symbol,
                order_type=OrderType.LIMIT_BUY,
                strategy_id=strategy.id
            )
            session.add(buy_order)
            session.commit()
            return
        
        # If buy order is filled, place take profit orders and monitor stop loss
        if buy_order.status.value == "filled":
            self.logger.info(f"Buy order {buy_order.order_id} is filled, managing orders")
            
            # Get all active sell orders
            active_sell_orders = [o for o in strategy.orders 
                                if o.side == OrderSide.SELL.value 
                                and o.status.value not in ["filled", "cancelled"]]
            
            # If no active sell orders, place take profit orders
            if not active_sell_orders:
                self.logger.info(f"Placing take profit orders (Current Price: ${current_price})")
                # Place take profit orders
                for tp_price in [config['take_profit_1'], config['take_profit_2']]:
                    tp_response = await self.client.place_order(
                        symbol=Symbol(strategy.symbol),
                        amount=str(float(config['amount']) / 2),
                        price=tp_price,
                        side=OrderSide.SELL,
                        order_type=GeminiOrderType.EXCHANGE_LIMIT
                    )
                    
                    tp_order = Order(
                        order_id=tp_response.order_id,
                        status=OrderState.ACCEPTED,
                        amount=str(float(config['amount']) / 2),
                        price=tp_price,
                        side=OrderSide.SELL.value,
                        symbol=strategy.symbol,
                        order_type=OrderType.LIMIT_SELL,
                        strategy_id=strategy.id
                    )
                    session.add(tp_order)
                session.commit()
                return
            
            # Monitor for stop loss if we have active take profit orders
            if active_sell_orders:
                # Already have current price from above
                
                # Check if price has hit stop loss
                if float(current_price) <= float(config['stop_loss']):
                    self.logger.info(f"Price ${current_price} hit stop loss at ${config['stop_loss']}, executing market sell")
                    
                    # Cancel existing take profit orders
                    for order in active_sell_orders:
                        await self.client.cancel_order(order.order_id)
                    
                    # Place market sell order
                    response = await self.client.place_order(
                        symbol=Symbol(strategy.symbol),
                        amount=config['amount'],
                        price=str(float(config['stop_loss']) * 0.99),  # Slightly below stop to ensure execution
                        side=OrderSide.SELL,
                        order_type=GeminiOrderType.EXCHANGE_LIMIT
                    )
                    
                    order = Order(
                        order_id=response.order_id,
                        status=OrderState.ACCEPTED,
                        amount=config['amount'],
                        price=str(float(config['stop_loss']) * 0.99),
                        side=OrderSide.SELL.value,
                        symbol=strategy.symbol,
                        order_type=OrderType.LIMIT_SELL,
                        strategy_id=strategy.id
                    )
                    session.add(order)
                    session.commit()

class StrategyManager:
    def __init__(self, session: Session, client: GeminiClient):
        self.session = session
        self.client = client
        self.logger = logging.getLogger("StrategyManager")
        self.strategies = {
            StrategyType.RANGE: RangeStrategy(client),
            StrategyType.BREAKOUT: BreakoutStrategy(client)
        }
        self.logger.info("Strategy Manager initialized")
    
    async def create_strategy(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Create and save a new trading strategy"""
        self.logger.info(f"Creating strategy: {strategy_data['name']}")
        strategy = save_strategy(strategy_data, session=self.session)
        self.session.commit()
        self.logger.info(f"Strategy created successfully: {strategy.id}")
        return strategy
    
    async def monitor_strategies(self):
        """Monitor and execute all active strategies"""
        self.logger.info("Starting strategy monitor loop\n")
        while True:
            try:
                strategies = get_active_strategies(session=self.session)
                self.logger.info(f"Found {len(strategies)} active strategies\n")
                
                for strategy in strategies:
                    self.logger.debug(f"Checking strategy: {strategy.name}")
                    current_time = datetime.utcnow()
                    
                    if (current_time - strategy.last_checked_at).seconds >= strategy.check_interval:
                        self.logger.info(f"Executing strategy: {strategy.name} (Type: {strategy.type})")
                        
                        # Update order statuses
                        self.logger.debug(f"Updating orders for strategy: {strategy.name}")
                        await self.update_orders(strategy)
                        
                        # Execute strategy logic
                        await self.strategies[strategy.type].execute(strategy, self.session)
                        
                        # Update last checked timestamp
                        strategy.last_checked_at = current_time
                        self.session.add(strategy)
                        self.session.commit()
                        self.logger.info(f"Strategy execution completed: {strategy.name}\n")

                await asyncio.sleep(1)  # Prevent tight loop
                
            except Exception as e:
                self.logger.error(f"Error monitoring strategies: {str(e)}\n", exc_info=True)
                await asyncio.sleep(5)  # Back off on error
    
    async def update_orders(self, strategy):
        try:
            self.logger.info(f"Updating orders for strategy: {strategy.name}")
            for order in strategy.orders:
                self.logger.debug(f"Checking order status: {order.order_id}")
                response = await self.client.check_order_status(order.order_id)
                
                if hasattr(response, 'status') and response.status is not None:
                    old_status = order.status
                    
                    order_data = {
                        "status": response.status,
                        "amount": response.original_amount,
                        "price": response.price,
                        "side": response.side,
                        "symbol": response.symbol,
                    }
                    
                    if hasattr(response, 'stop_price') and response.stop_price is not None:
                        order_data["stop_price"] = response.stop_price
                    
                    update_order(
                        order.order_id, 
                        session=self.session, 
                        **order_data
                    )
                    self.logger.info(f"Order {order.order_id} updated - Status: {old_status} -> {response.status}")
            
            self.session.commit()
            self.logger.debug("Order updates committed successfully\n")
            
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error updating orders: {str(e)}\n", exc_info=True)