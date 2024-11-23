from decimal import Decimal
from typing import Optional
from trader.models import Order, OrderState
from trader.gemini.enums import OrderSide

class TrailingStopMixin:
    """Mixin class providing trailing stop loss functionality"""
    
    async def update_trailing_stop(self, strategy, service, current_price: str, config: dict) -> None:
        """Update trailing stop loss based on current price"""
        current_price = Decimal(current_price)
        initial_stop = Decimal(config['stop_loss_price'])
        trail_percent = Decimal(config.get('trail_percent', '0.01'))  # Default 1%
        
        # Get filled buy orders to determine entry price
        buy_order = next((o for o in strategy.orders 
                         if o.side == OrderSide.BUY.value 
                         and o.status == OrderState.FILLED), None)
        
        if not buy_order:
            return
            
        entry_price = Decimal(buy_order.price)
        
        # Calculate trailing stop price
        price_increase = current_price - entry_price
        if price_increase > 0:
            # Move stop up by the same amount, minus the trail percentage
            new_stop = max(
                initial_stop,
                current_price * (1 - trail_percent)
            )
            
            # Update stop loss order if needed
            await self._update_stop_order(strategy, service, str(new_stop))
    
    async def _update_stop_order(self, strategy, service, new_stop: str) -> None:
        """Update or place stop loss order"""
        stop_order = next((o for o in strategy.orders 
                          if o.order_type == 'STOP_LIMIT_SELL' 
                          and o.status != OrderState.FILLED), None)
        
        if stop_order and Decimal(stop_order.price) != Decimal(new_stop):
            # Cancel existing stop order
            await service.order_service.cancel_order(stop_order)
            stop_order = None
            
        if not stop_order:
            # Place new stop order
            position_size = self._get_position_size(strategy)
            if position_size:
                await service.order_service.place_stop_order(
                    strategy=strategy,
                    amount=position_size,
                    stop_price=new_stop,
                    limit_price=str(Decimal(new_stop) * Decimal('0.99'))  # 1% below stop for limit
                )
    
    def _get_position_size(self, strategy) -> Optional[str]:
        """Get current position size from filled buy orders"""
        buy_orders = [o for o in strategy.orders if o.side == OrderSide.BUY.value 
                     and o.status == OrderState.FILLED]
        sell_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value 
                      and o.status == OrderState.FILLED]
        
        if not buy_orders:
            return None
            
        total_bought = sum(Decimal(o.amount) for o in buy_orders)
        total_sold = sum(Decimal(o.amount) for o in sell_orders)
        
        current_position = total_bought - total_sold
        return str(current_position) if current_position > 0 else None 