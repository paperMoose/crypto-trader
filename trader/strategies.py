import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any
from sqlmodel import Session
from trader.models import OrderType, TradingStrategy, Order, OrderState, StrategyType, StrategyState
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType as GeminiOrderType
from trader.database import (
    save_strategy, 
    get_active_strategies, 
    update_order, 
    get_strategy_by_name
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
                      if o.side == OrderSide.SELL.value]
        
        # Check if sell order is filled (strategy completed successfully)
        filled_sell_orders = [o for o in sell_orders if o.status.value == "filled"]
        if filled_sell_orders:
            self.logger.info("Sell order filled, marking strategy as completed")
            strategy.is_active = False
            strategy.state = StrategyState.COMPLETED
            session.commit()
            return
        
        # Get active sell orders for management
        active_sell_orders = [o for o in sell_orders 
                             if o.status.value not in ["filled", "cancelled"]]
        
        self.logger.info(f"Current orders - Buy: {buy_order and buy_order.status}, "
                        f"Sell: {len(active_sell_orders)} orders")
        
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
            if not active_sell_orders:
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
            if active_sell_orders:
                # Check if price has hit stop loss
                if float(current_price) <= float(config['stop_loss_price']):
                    self.logger.info(f"Price ${current_price} hit stop loss at ${config['stop_loss_price']}, executing market sell")
                    
                    # Cancel existing sell order
                    for order in active_sell_orders:
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
                    
                    # Mark strategy as completed after stop loss
                    strategy.is_active = False
                    strategy.state = StrategyState.COMPLETED
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
        
        # If buy order is filled, check stop loss first before placing take profit orders
        if buy_order.status.value == "filled":
            self.logger.info(f"Buy order {buy_order.order_id} is filled, managing orders")
            
            # Get all sell orders (including filled ones)
            sell_orders = [o for o in strategy.orders 
                          if o.side == OrderSide.SELL.value]
            
            # Check if both take profit orders are filled
            filled_sell_orders = [o for o in sell_orders if o.status.value == "filled"]
            if len(filled_sell_orders) == 2:  # Both take profit orders filled
                self.logger.info("Both take profit orders filled, marking strategy as completed")
                strategy.is_active = False
                strategy.state = StrategyState.COMPLETED
                session.commit()
                return

            # Get active sell orders for management
            active_sell_orders = [o for o in sell_orders 
                                if o.status.value not in ["filled", "cancelled"]]
            
            # Check stop loss first
            if float(current_price) <= float(config['stop_loss']):
                self.logger.info(f"Price ${current_price} hit stop loss at ${config['stop_loss']}, executing market sell")
                
                # Cancel existing take profit orders
                for order in active_sell_orders:
                    await self.client.cancel_order(order.order_id)
                
                # Place market sell order
                response = await self.client.place_order(
                    symbol=Symbol(strategy.symbol),
                    amount=config['amount'],
                    price=str(float(config['stop_loss']) * 0.99),
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
                
                # Mark strategy as completed after stop loss
                strategy.is_active = False
                strategy.state = StrategyState.COMPLETED
                session.commit()
                return
            
            # Only place take profit orders if we haven't hit stop loss and have no active sell orders
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
                        price=str(float(config['stop_loss']) * 0.99),
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
    
    async def cancel_strategy_orders(self, strategy):
        """Cancel all active orders for a strategy"""
        self.logger.info(f"Cancelling all orders for strategy: {strategy.name}")
        
        # Get all active orders from the strategy object
        active_orders = [order for order in strategy.orders 
                        if order.status.value not in ["filled", "cancelled"]]
        
        for order in active_orders:
            try:
                self.logger.info(f"Cancelling order {order.order_id}")
                await self.client.cancel_order(order.order_id)
            except Exception as e:
                self.logger.error(f"Error cancelling order {order.order_id}: {str(e)}")
                continue
        
        # Update order statuses after cancellation
        await self.update_orders(strategy)
        self.session.refresh(strategy)
        
        self.logger.info(f"Finished cancelling orders for strategy: {strategy.name}")

    async def update_strategy_orders(self, strategy_data):
        """Update existing strategy with new orders"""
        existing = get_strategy_by_name(strategy_data["name"], session=self.session)
        
        if existing:
            config_changed = (
                existing.config != strategy_data["config"]
            )
            
            if config_changed:
                self.logger.info(f"Config changed for strategy: {strategy_data['name']}, updating orders")
                # Cancel existing orders
                await self.cancel_strategy_orders(existing)
                # Update config in database
                existing.config = strategy_data["config"]
                self.session.commit()
                # Execute strategy to create new orders
                await self.strategies[existing.type].execute(existing, self.session)
                return existing
            else:
                self.logger.info(f"No config changes for strategy: {strategy_data['name']}")
                return existing
        
        self.logger.info(f"Creating new strategy: {strategy_data['name']}")
        return await self.create_strategy(strategy_data)

    async def deactivate_strategy(self, strategy_name: str) -> TradingStrategy:
        """Deactivate a strategy by setting is_active to False and state to CANCELED"""
        self.logger.info(f"Deactivating strategy: {strategy_name}")
        
        strategy = get_strategy_by_name(strategy_name, session=self.session)
        if not strategy:
            raise ValueError(f"Strategy not found: {strategy_name}")
        
        # Cancel any existing orders
        await self.cancel_strategy_orders(strategy)
        
        # Update strategy state
        strategy.is_active = False
        strategy.state = StrategyState.CANCELED
        self.session.commit()
        
        self.logger.info(f"Strategy {strategy_name} has been deactivated")
        return strategy