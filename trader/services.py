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
from decimal import Decimal
from sqlmodel import select

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
        active_orders: List[Order],
        buy_price: Optional[str] = None
    ) -> Optional[Order]:
        """Execute stop loss order and update profits"""
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
        
        # Update profits if buy price is provided
        if buy_price and order:
            self.update_strategy_profits(strategy, buy_price, stop_price, amount)
            
        return order

    async def place_take_profit_orders(
        self,
        strategy: TradingStrategy,
        prices: List[str],
        amount: str,
        buy_price: Optional[str] = None
    ) -> List[Order]:
        """Place take profit orders and track potential profit"""
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
        
        # Log potential profits if buy price is provided
        if buy_price:
            for price in prices:
                potential_profit = (Decimal(price) - Decimal(buy_price)) * Decimal(amount) / len(prices)
                self.logger.info(
                    f"Potential profit for take profit order at ${price}: "
                    f"${potential_profit:.2f} (Before taxes: ${potential_profit * Decimal('0.5'):.2f})"
                )
        
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

    def update_strategy_profits(self, strategy: TradingStrategy, buy_price: str, sell_price: str, amount: str) -> None:
        """
        Update strategy profits after a successful trade
        Args:
            strategy: The trading strategy
            buy_price: The price at which the asset was bought
            sell_price: The price at which the asset was sold
            amount: The amount of the asset traded
        """
        try:
            # Convert strings to Decimal for precise calculation
            buy_dec = Decimal(buy_price)
            sell_dec = Decimal(sell_price)
            amount_dec = Decimal(amount)
            
            # Calculate profit
            trade_profit = (sell_dec - buy_dec) * amount_dec
            
            # Update total profit
            current_total = Decimal(strategy.total_profit or "0.0")
            new_total = current_total + trade_profit
            strategy.total_profit = str(new_total)
            
            # Update realized profit
            current_realized = Decimal(strategy.realized_profit or "0.0")
            new_realized = current_realized + trade_profit
            strategy.realized_profit = str(new_realized)
            
            # Calculate and update tax reserve (50% of profit)
            if trade_profit > 0:
                tax_reserve = trade_profit * Decimal("0.5")
                current_tax_reserve = Decimal(strategy.tax_reserve or "0.0")
                strategy.tax_reserve = str(current_tax_reserve + tax_reserve)
                
                # Calculate available profit (after tax reserve)
                current_available = Decimal(strategy.available_profit or "0.0")
                strategy.available_profit = str(current_available + (trade_profit - tax_reserve))
            
            self.session.commit()
            
            # Log the profit update
            self.logger.info(
                f"Updated profits for strategy {strategy.name}:\n"
                f"Trade Profit: ${trade_profit:.2f}\n"
                f"Total Profit: ${new_total:.2f}\n"
                f"Tax Reserve: ${strategy.tax_reserve}\n"
                f"Available: ${strategy.available_profit}"
            )
            
        except Exception as e:
            self.logger.error(f"Error updating profits: {str(e)}")
            self.session.rollback()
            raise

    def get_total_profits_summary(self) -> Dict[str, str]:
        """
        Get a summary of total profits across all strategies
        Returns:
            Dict containing total profits, tax reserve, and available profits
        """
        try:
            # Get all strategies using explicit select
            statement = select(TradingStrategy)
            result = self.session.exec(statement)
            strategies = result.all()
            
            # Initialize totals using Decimal for precise calculation
            total_profit = Decimal("0.0")
            total_tax_reserve = Decimal("0.0")
            total_available = Decimal("0.0")
            total_realized = Decimal("0.0")
            
            # Sum up profits from all strategies
            for strategy in strategies:
                total_profit += Decimal(strategy.total_profit)
                total_tax_reserve += Decimal(strategy.tax_reserve)
                total_available += Decimal(strategy.available_profit)
                total_realized += Decimal(strategy.realized_profit)
            
            return {
                "total_profit": f"{total_profit:.2f}",
                "total_realized": f"{total_realized:.2f}",
                "tax_reserve": f"{total_tax_reserve:.2f}",
                "available_profit": f"{total_available:.2f}"
            }
            
        except Exception as e:
            self.logger.error(f"Error getting profit summary: {str(e)}")
            raise

    def get_profits_by_strategy(self):
        """Get detailed profit breakdown by strategy"""
        statement = select(TradingStrategy)
        result = self.session.exec(statement)
        strategies = result.all()
        
        return [{
            'strategy_id': strategy.id,
            'strategy_name': strategy.name,
            'total_profit': strategy.total_profit,
            'realized_profit': strategy.realized_profit,
            'tax_reserve': strategy.tax_reserve,
            'available_profit': strategy.available_profit,
            'symbol': strategy.symbol,
            'type': strategy.type
        } for strategy in strategies]