import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from sqlmodel import Session
from trader.models import TradingStrategy, OrderState
from trader.gemini.client import GeminiClient
from trader.gemini.enums import OrderSide
from .mixins import TrailingStopMixin

class BaseStrategy(ABC, TrailingStopMixin):
    def __init__(self, client: GeminiClient):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute strategy logic"""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration"""
        pass
    
    async def get_current_price(self, strategy: TradingStrategy, service) -> Optional[str]:
        """Get current price and log it"""
        try:
            current_price = await service.get_current_price(strategy.symbol)
            self.logger.info(f"Current price for {strategy.name}: ${current_price}")
            return current_price
        except Exception as e:
            self.logger.error(f"Error getting price: {str(e)}")
            await service.handle_error(strategy, e)
            return None
        
    async def _execute_common(self, strategy: TradingStrategy, service) -> None:
        """Common execution steps for all strategies"""
        try:
            # Update order statuses
            await service.order_service.update_order_statuses(strategy)
            
            # Get filled buy orders
            filled_buys = [o for o in strategy.orders 
                         if o.side == OrderSide.BUY.value 
                         and o.status == OrderState.FILLED]
            
            # Only check trailing stop if we have filled buy orders
            if filled_buys and strategy.config.get('use_trailing_stop', False):
                current_price = await self.get_current_price(strategy, service)
                if current_price:
                    await self.update_trailing_stop(strategy, service, current_price, strategy.config)
            
        except Exception as e:
            self.logger.error(f"Error in common execution: {str(e)}")
            await service.handle_error(strategy, e)
            
    def get_active_orders(self, strategy: TradingStrategy, side: Optional[OrderSide] = None) -> list:
        """Get active orders, optionally filtered by side"""
        orders = strategy.orders
        if side:
            orders = [o for o in orders if o.side == side.value]
        return [o for o in orders if o.status.value not in ["filled", "cancelled"]]
    
    def get_filled_orders(self, strategy: TradingStrategy, side: Optional[OrderSide] = None) -> list:
        """Get filled orders, optionally filtered by side"""
        orders = strategy.orders
        if side:
            orders = [o for o in orders if o.side == side.value]
        return [o for o in orders if o.status == OrderState.FILLED]