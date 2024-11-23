from typing import Dict, Any
from sqlmodel import Session
from trader.services import StrategyService
from trader.gemini.enums import OrderSide
from trader.models import OrderType, TradingStrategy
from decimal import Decimal
from .base import BaseStrategy

class BreakoutStrategy(BaseStrategy):
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'breakout_price', 'amount', 'take_profit_1', 'take_profit_2', 'stop_loss'}
        optional = {'use_trailing_stop', 'trail_percent'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute breakout strategy"""
        service = StrategyService(self.client, session)
        
        # Get current price first
        current_price = await self.get_current_price(strategy, service)
        if not current_price:
            return
            
        # Execute common strategy steps
        await self._execute_common(strategy, service)
        
        config = strategy.config
        
        # Check if initial buy order exists
        buy_order = next((o for o in strategy.orders if o.side == OrderSide.BUY.value), None)
        filled_sells = self.get_filled_orders(strategy, OrderSide.SELL)
        
        # Check if both take profit orders are filled
        if len(filled_sells) == 2:
            service.complete_strategy(strategy)
            return
        
        if not buy_order:
            # Only place breakout order if price is near breakout level
            if float(current_price) >= float(config['breakout_price']) * 0.995:  # Within 0.5%
                self.logger.info(f"Placing breakout buy order at ${config['breakout_price']}")
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=config['amount'],
                    price=config['breakout_price'],
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT_BUY
                )
            else:
                self.logger.info(f"Price ${current_price} too far from breakout level ${config['breakout_price']}")
            return
        
        # If buy order is filled, manage take profit orders
        if buy_order.status.value == "filled":
            self.logger.info(f"Buy order {buy_order.order_id} is filled, managing orders")
            active_sells = self.get_active_orders(strategy, OrderSide.SELL)
            
            # Place take profit orders if none exist
            if not active_sells:
                self.logger.info(f"Placing take profit orders (Current Price: ${current_price})")
                half_amount = str(Decimal(config['amount']) / 2)
                
                # Place first take profit order
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=half_amount,
                    price=config['take_profit_1'],
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT_SELL
                )
                
                # Place second take profit order
                await service.order_service.place_order(
                    strategy=strategy,
                    amount=half_amount,
                    price=config['take_profit_2'],
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT_SELL
                )
                
                # Track potential profits
                service.update_strategy_profits(
                    strategy,
                    buy_order.price,
                    config['take_profit_1'],
                    half_amount
                )
                service.update_strategy_profits(
                    strategy,
                    buy_order.price,
                    config['take_profit_2'],
                    half_amount
                ) 