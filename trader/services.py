import logging
from typing import Optional, List, Tuple, Dict, Any
from sqlmodel import Session
from trader.models import Order, OrderType, StrategyState, TradingStrategy, OrderState, StrategyType
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType as GeminiOrderType
from datetime import datetime
from trader.database import (
    save_strategy, 
    get_active_strategies, 
    get_strategy_by_name
)
from trader.gemini.schemas import GeminiAPIError

logger = logging.getLogger(__name__)

class OrderService:
    def __init__(self, client: GeminiClient, session: Session):
        self.client = client
        self.session = session
        self.logger = logging.getLogger("OrderService")

    async def place_order(
        self,
        strategy: TradingStrategy,
        amount: str,
        price: str,
        side: OrderSide,
        order_type: OrderType
    ) -> Order:
        """Place order and persist to database"""
        try:
            self.logger.info(f"Placing {side.value} order for {amount} at ${price}")
            
            response = await self.client.place_order(
                symbol=Symbol(strategy.symbol),
                amount=amount,
                price=price,
                side=side,
                order_type=GeminiOrderType.EXCHANGE_LIMIT
            )
            
            order = Order(
                order_id=response.order_id,
                status=OrderState.ACCEPTED,
                amount=amount,
                price=price,
                side=side.value,
                symbol=strategy.symbol,
                order_type=order_type,
                strategy_id=strategy.id
            )
            
            self.session.add(order)
            self.session.commit()
            return order
            
        except GeminiAPIError as e:
            self.logger.error(f"Gemini API error placing order: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Error placing order: {str(e)}")
            self.session.rollback()
            raise

    async def cancel_orders(self, orders: List[Order]) -> None:
        """Cancel multiple orders"""
        for order in orders:
            try:
                await self.client.cancel_order(order.order_id)
            except Exception as e:
                self.logger.error(f"Error cancelling order {order.order_id}: {str(e)}")

    async def update_order_statuses(self, strategy: TradingStrategy) -> None:
        """Update status of all orders in a strategy"""
        for order in strategy.orders:
            try:
                response = await self.client.check_order_status(order.order_id)
                if hasattr(response, 'status') and response.status is not None:
                    old_status = order.status
                    order.status = OrderState(response.status.value if hasattr(response.status, 'value') else response.status)
                    self.logger.info(f"Order {order.order_id} updated - Status: {old_status} -> {order.status}")
            except Exception as e:
                self.logger.error(f"Error updating order {order.order_id}: {str(e)}")
        
        self.session.commit()

class StrategyService:
    def __init__(self, client: GeminiClient, session: Session, strategies=None):
        self.client = client
        self.session = session
        self.order_service = OrderService(client, session)
        self.strategies = strategies
        self.logger = logging.getLogger("StrategyService")

    async def get_current_price(self, symbol: str) -> str:
        """Get current price for a symbol"""
        return await self.client.get_price(Symbol(symbol))

    def set_strategy_state(self, strategy: TradingStrategy, state: StrategyState, active: bool = True) -> None:
        """Set strategy state and active status"""
        strategy.state = state
        strategy.is_active = active
        self.session.commit()
        self.logger.info(f"Strategy {strategy.name} state changed to {state.value}")

    def activate_strategy(self, strategy: TradingStrategy) -> None:
        """Activate a strategy"""
        self.set_strategy_state(strategy, StrategyState.ACTIVE, active=True)

    def pause_strategy(self, strategy: TradingStrategy) -> None:
        """Pause a strategy"""
        self.set_strategy_state(strategy, StrategyState.PAUSED, active=False)

    def complete_strategy(self, strategy: TradingStrategy) -> None:
        """Mark a strategy as completed"""
        self.set_strategy_state(strategy, StrategyState.COMPLETED, active=False)

    def cancel_strategy(self, strategy: TradingStrategy) -> None:
        """Cancel a strategy"""
        self.set_strategy_state(strategy, StrategyState.CANCELED, active=False)

    def fail_strategy(self, strategy: TradingStrategy) -> None:
        """Mark a strategy as failed"""
        self.set_strategy_state(strategy, StrategyState.FAILED, active=False)

    async def cancel_and_deactivate_strategy(self, strategy: TradingStrategy) -> None:
        """Cancel all orders and deactivate strategy"""
        # Get all active orders
        active_orders = [o for o in strategy.orders 
                        if o.status.value not in ["filled", "cancelled"]]
        
        # Cancel all active orders
        await self.order_service.cancel_orders(active_orders)
        
        # Mark strategy as cancelled
        self.cancel_strategy(strategy)
        self.logger.info(f"Strategy {strategy.name} cancelled and deactivated")

    async def pause_strategy_with_orders(self, strategy: TradingStrategy) -> None:
        """Pause strategy and cancel all pending orders"""
        # Get all active orders
        active_orders = [o for o in strategy.orders 
                        if o.status.value not in ["filled", "cancelled"]]
        
        # Cancel all active orders
        await self.order_service.cancel_orders(active_orders)
        
        # Mark strategy as paused
        self.pause_strategy(strategy)
        self.logger.info(f"Strategy {strategy.name} paused with orders cancelled")

    async def resume_strategy(self, strategy: TradingStrategy) -> None:
        """Resume a paused strategy"""
        if strategy.state != StrategyState.PAUSED:
            raise ValueError(f"Cannot resume strategy {strategy.name} - not in PAUSED state")
        
        # Reactivate strategy
        self.activate_strategy(strategy)
        self.logger.info(f"Strategy {strategy.name} resumed")

    def validate_state_transition(self, strategy: TradingStrategy, new_state: StrategyState) -> bool:
        """
        Validate if a state transition is allowed
        Returns True if transition is valid, False otherwise
        """
        # Define valid state transitions
        valid_transitions = {
            StrategyState.ACTIVE: [StrategyState.PAUSED, StrategyState.COMPLETED, 
                                 StrategyState.CANCELED, StrategyState.FAILED],
            StrategyState.PAUSED: [StrategyState.ACTIVE, StrategyState.CANCELED],
            StrategyState.COMPLETED: [],  # Terminal state
            StrategyState.CANCELED: [],   # Terminal state
            StrategyState.FAILED: []      # Terminal state
        }

        return new_state in valid_transitions.get(strategy.state, [])

    async def handle_error(self, strategy: TradingStrategy, error: Exception) -> None:
        """Handle strategy error by logging and updating state"""
        self.logger.error(f"Error in strategy {strategy.name}: {str(error)}", exc_info=True)
        
        # Cancel any active orders
        active_orders = [o for o in strategy.orders 
                        if o.status.value not in ["filled", "cancelled"]]
        if active_orders:
            await self.order_service.cancel_orders(active_orders)
        
        # Mark strategy as failed
        self.fail_strategy(strategy)

    async def execute_stop_loss(
        self,
        strategy: TradingStrategy,
        current_price: str,
        stop_price: str,
        amount: str,
        active_orders: List[Order]
    ) -> Optional[Order]:
        """Execute stop loss order and cancel existing orders"""
        self.logger.info(f"Price ${current_price} hit stop loss at ${stop_price}, executing market sell")
        
        # Cancel existing orders
        await self.order_service.cancel_orders(active_orders)
        
        # Place market sell order
        order = await self.order_service.place_order(
            strategy=strategy,
            amount=amount,
            price=str(float(stop_price) * 0.99),  # Slightly below stop to ensure execution
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT_SELL
        )
        
        # Mark strategy as completed
        self.complete_strategy(strategy)
        return order

    async def place_take_profit_orders(
        self,
        strategy: TradingStrategy,
        prices: List[str],
        amount: str
    ) -> List[Order]:
        """Place multiple take profit orders"""
        orders = []
        for price in prices:
            order = await self.order_service.place_order(
                strategy=strategy,
                amount=str(float(amount) / len(prices)),  # Split amount equally
                price=price,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
            orders.append(order)
        return orders 

    async def get_active_strategies(self) -> List[TradingStrategy]:
        """Get all active strategies from database"""
        return get_active_strategies(session=self.session)

    async def should_execute_strategy(self, strategy: TradingStrategy) -> bool:
        """Check if strategy should be executed based on check_interval"""
        current_time = datetime.utcnow()
        return (current_time - strategy.last_checked_at).seconds >= strategy.check_interval

    async def update_strategy_timestamp(self, strategy: TradingStrategy) -> None:
        """Update strategy's last_checked_at timestamp"""
        strategy.last_checked_at = datetime.utcnow()
        self.session.add(strategy)
        self.session.commit()

    async def update_strategy_orders(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Update existing strategy with new orders"""
        # Validate strategy type exists
        strategy_type = StrategyType(strategy_data["type"])
        if strategy_type not in self.strategies:
            raise ValueError(f"Invalid strategy type: {strategy_type}")
            
        # Validate strategy config
        if not self.strategies[strategy_type].validate_config(strategy_data["config"]):
            raise ValueError(f"Invalid configuration for strategy: {strategy_data['name']}")

        existing = get_strategy_by_name(strategy_data["name"], session=self.session)
        
        if existing:
            config_changed = existing.config != strategy_data["config"]
            
            if config_changed:
                self.logger.info(f"Config changed for strategy: {strategy_data['name']}, updating orders")
                # Cancel existing orders
                await self.cancel_and_deactivate_strategy(existing)
                # Update config in database
                existing.config = strategy_data["config"]
                existing.is_active = True
                existing.state = StrategyState.ACTIVE
                self.session.commit()
                return existing
            else:
                self.logger.info(f"No config changes for strategy: {strategy_data['name']}")
                return existing
        
        # Create new strategy if it doesn't exist
        self.logger.info(f"Creating new strategy: {strategy_data['name']}")
        strategy = save_strategy(strategy_data, session=self.session)
        self.session.commit()
        return strategy

    async def cancel_and_deactivate_strategy_by_name(self, strategy_name: str) -> TradingStrategy:
        """Find strategy by name and deactivate it"""
        strategy = get_strategy_by_name(strategy_name, session=self.session)
        if not strategy:
            raise ValueError(f"Strategy not found: {strategy_name}")
        
        await self.cancel_and_deactivate_strategy(strategy)
        return strategy