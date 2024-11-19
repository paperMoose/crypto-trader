import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
from sqlmodel import Session
from trader.models import OrderType, TradingStrategy, StrategyType
from trader.gemini.client import GeminiClient
from trader.gemini.enums import OrderSide
from trader.services import StrategyService
import asyncio

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
        service = StrategyService(self.client, session)
        
        try:
            # Get current price and update order statuses
            current_price = await service.get_current_price(strategy.symbol)
            self.logger.info(f"Executing strategy for {strategy.name} (Current Price: ${current_price})")
            await service.order_service.update_order_statuses(strategy)
            
            config = strategy.config
            
            # Check existing orders
            buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
            sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
            
            # Check if strategy is complete (sell order filled)
            filled_sell_orders = [o for o in sell_orders if o.status.value == "filled"]
            if filled_sell_orders:
                service.complete_strategy(strategy)
                return
            
            # Place buy order at support if none exists
            if not buy_order:
                self.logger.info(f"Placing buy order at support price {config['support_price']}")
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=config['amount'],
                    price=config['support_price'],
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT_BUY
                )
                return
            
            # If buy order is filled, manage sell orders
            if buy_order.status.value == "filled":
                active_sell_orders = [o for o in sell_orders 
                                    if o.status.value not in ["filled", "cancelled"]]
                
                # Check stop loss
                if float(current_price) <= float(config['stop_loss_price']):
                    await service.execute_stop_loss(
                        strategy=strategy,
                        current_price=current_price,
                        stop_price=config['stop_loss_price'],
                        amount=config['amount'],
                        active_orders=active_sell_orders
                    )
                    return
                
                # Place sell order at resistance if none exists
                if not active_sell_orders:
                    self.logger.info(f"Buy order filled, placing sell order at resistance {config['resistance_price']}")
                    await service.order_service.place_order(
                        strategy=strategy,
                        amount=config['amount'],
                        price=config['resistance_price'],
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT_SELL
                    )
                    # Track potential profit
                    service.update_strategy_profits(
                        strategy,
                        buy_order.price,
                        config['resistance_price'],
                        config['amount']
                    )
                    
        except Exception as e:
            await service.handle_error(strategy, e)

class BreakoutStrategy(BaseStrategy):
    def __init__(self, client: GeminiClient):
        super().__init__(client)
        self.logger = logging.getLogger("BreakoutStrategy")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'breakout_price', 'amount', 'take_profit_1', 'take_profit_2', 'stop_loss'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute breakout strategy"""
        service = StrategyService(self.client, session)
        
        try:
            # Get current price and update order statuses
            current_price = await service.get_current_price(strategy.symbol)
            self.logger.info(f"Executing strategy for {strategy.name} (Current Price: ${current_price})")
            await service.order_service.update_order_statuses(strategy)
            
            config = strategy.config
            
            # Check if initial buy order exists
            buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
            
            if not buy_order:
                self.logger.info(f"Placing breakout buy order at ${config['breakout_price']}")
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=config['amount'],
                    price=config['breakout_price'],
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT_BUY
                )
                return
            
            # If buy order is filled, manage take profit and stop loss orders
            if buy_order.status.value == "filled":
                self.logger.info(f"Buy order {buy_order.order_id} is filled, managing orders")
                
                # Get all sell orders
                sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
                
                # Check if both take profit orders are filled
                filled_sell_orders = [o for o in sell_orders if o.status.value == "filled"]
                if len(filled_sell_orders) == 2:
                    service.complete_strategy(strategy)
                    return
                
                # Get active sell orders for management
                active_sell_orders = [o for o in sell_orders 
                                    if o.status.value not in ["filled", "cancelled"]]
                
                # Check stop loss
                if float(current_price) <= float(config['stop_loss']):
                    await service.execute_stop_loss(
                        strategy=strategy,
                        current_price=current_price,
                        stop_price=config['stop_loss'],
                        amount=config['amount'],
                        active_orders=active_sell_orders
                    )
                    return
                
                # Place take profit orders if none exist
                if not active_sell_orders:
                    self.logger.info(f"Placing take profit orders (Current Price: ${current_price})")
                    await service.place_take_profit_orders(
                        strategy=strategy,
                        prices=[config['take_profit_1'], config['take_profit_2']],
                        amount=config['amount'],
                        buy_price=buy_order.price  # Pass buy price for profit tracking
                    )
                    
        except Exception as e:
            await service.handle_error(strategy, e)

class TakeProfitStrategy(BaseStrategy):
    def __init__(self, client: GeminiClient):
        super().__init__(client)
        self.logger = logging.getLogger("TakeProfitStrategy")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'current_position', 'entry_price', 'take_profit_price', 'stop_loss_price'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute take profit strategy for existing position"""
        service = StrategyService(self.client, session)
        
        try:
            # Get current price and update order statuses
            current_price = await service.get_current_price(strategy.symbol)
            self.logger.info(f"Executing strategy for {strategy.name} (Current Price: ${current_price})")
            await service.order_service.update_order_statuses(strategy)
            
            config = strategy.config
            
            # Check existing sell orders
            sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
            
            # Check if strategy is complete (sell order filled)
            filled_sell_orders = [o for o in sell_orders if o.status.value == "filled"]
            if filled_sell_orders:
                service.complete_strategy(strategy)
                return
            
            # Check stop loss
            if float(current_price) <= float(config['stop_loss_price']):
                active_sell_orders = [o for o in sell_orders 
                                    if o.status.value not in ["filled", "cancelled"]]
                await service.execute_stop_loss(
                    strategy=strategy,
                    current_price=current_price,
                    stop_price=config['stop_loss_price'],
                    amount=config['current_position'],
                    active_orders=active_sell_orders
                )
                return
            
            # Place take profit order if none exists
            active_sell_orders = [o for o in sell_orders 
                                if o.status.value not in ["filled", "cancelled"]]
            if not active_sell_orders:
                self.logger.info(f"Placing take profit order at {config['take_profit_price']}")
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=config['current_position'],
                    price=config['take_profit_price'],
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT_SELL
                )
                    
        except Exception as e:
            await service.handle_error(strategy, e)

class StrategyManager:
    def __init__(self, session: Session, client: GeminiClient):
        self.session = session
        self.client = client
        self.logger = logging.getLogger("StrategyManager")
        self.strategies = {
            StrategyType.RANGE: RangeStrategy(client),
            StrategyType.BREAKOUT: BreakoutStrategy(client),
            StrategyType.TAKE_PROFIT: TakeProfitStrategy(client)
        }
        self.service = StrategyService(client, session, self.strategies)
        self.logger.info("Strategy Manager initialized")

    async def monitor_strategies(self):
        """Monitor and execute all active strategies"""
        self.logger.info("Starting strategy monitor loop\n")
        
        while True:
            try:
                # Get active strategies from service
                strategies = await self.service.get_active_strategies()
                self.logger.info(f"Found {len(strategies)} active strategies\n")
                
                for strategy in strategies:
                    self.logger.debug(f"Checking strategy: {strategy.name}")
                    
                    # Check if it's time to execute strategy based on check_interval
                    if await self.service.should_execute_strategy(strategy):
                        self.logger.info(f"Executing strategy: {strategy.name} (Type: {strategy.type})")
                        
                        # Execute strategy logic
                        await self.strategies[strategy.type].execute(strategy, self.session)
                        
                        # Update last checked timestamp
                        await self.service.update_strategy_timestamp(strategy)
                        
                        self.logger.info(f"Strategy execution completed: {strategy.name}\n")

                await asyncio.sleep(1)  # Prevent tight loop
                
            except Exception as e:
                self.logger.error(f"Error monitoring strategies: {str(e)}\n", exc_info=True)
                await asyncio.sleep(5)  # Back off on error

    async def update_strategy_orders(self, strategy_data):
        """Update existing strategy with new orders"""
        try:
            return await self.service.update_strategy_orders(strategy_data)
        except Exception as e:
            self.logger.error(f"Error updating strategy orders: {str(e)}")
            raise

    async def deactivate_strategy(self, strategy_name: str):
        """Deactivate a strategy"""
        try:
            return await self.service.cancel_and_deactivate_strategy_by_name(strategy_name)
        except Exception as e:
            self.logger.error(f"Error deactivating strategy: {str(e)}")
            raise

    async def create_strategy(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Create and save a new trading strategy"""
        self.logger.info(f"Creating strategy: {strategy_data['name']}")
        try:
            return await self.service.update_strategy_orders(strategy_data)
        except Exception as e:
            self.logger.error(f"Error creating strategy: {str(e)}")
            raise