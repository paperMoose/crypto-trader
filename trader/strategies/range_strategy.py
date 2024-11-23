from typing import Dict, Any
from sqlmodel import Session
from trader.services import StrategyService
from trader.gemini.enums import OrderSide
from trader.models import OrderType, TradingStrategy
from .base import BaseStrategy

class RangeStrategy(BaseStrategy):
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'support_price', 'resistance_price', 'amount', 'stop_loss_price'}
        optional = {'use_trailing_stop', 'trail_percent'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute range trading strategy"""
        service = StrategyService(self.client, session)
        
        # Get current price first
        current_price = await self.get_current_price(strategy, service)
        if not current_price:
            return
            
        # Execute common strategy steps
        await self._execute_common(strategy, service)
            
        config = strategy.config
        
        # Check existing orders
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        filled_sells = self.get_filled_orders(strategy, OrderSide.SELL)
        
        # Check if strategy is complete
        if filled_sells:
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
            active_sells = self.get_active_orders(strategy, OrderSide.SELL)
            
            # Place sell order at resistance if none exists
            if not active_sells:
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