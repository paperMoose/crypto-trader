from typing import Dict, Any
from sqlmodel import Session
from trader.services import StrategyService
from trader.gemini.enums import OrderSide
from trader.models import OrderType, TradingStrategy
from .base import BaseStrategy

class TakeProfitStrategy(BaseStrategy):
    def validate_config(self, config: Dict[str, Any]) -> bool:
        required = {'current_position', 'entry_price', 'take_profit_price', 'stop_loss_price'}
        optional = {'use_trailing_stop', 'trail_percent'}
        return all(k in config for k in required)
    
    async def execute(self, strategy: TradingStrategy, session: Session) -> None:
        """Execute take profit strategy for existing position"""
        service = StrategyService(self.client, session)
        
        # Get current price first
        current_price = await self.get_current_price(strategy, service)
        if not current_price:
            return
            
        # Execute common strategy steps
        await self._execute_common(strategy, service)
        
        config = strategy.config
        filled_sells = self.get_filled_orders(strategy, OrderSide.SELL)
        
        # Check if strategy is complete (sell order filled)
        if filled_sells:
            service.complete_strategy(strategy)
            return
        
        # Place take profit order if none exists
        active_sells = self.get_active_orders(strategy, OrderSide.SELL)
        if not active_sells:
            self.logger.info(f"Placing take profit order at {config['take_profit_price']}")
            await service.order_service.place_order(
                strategy=strategy,
                amount=config['current_position'],
                price=config['take_profit_price'],
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
            
            # Track potential profit
            service.update_strategy_profits(
                strategy,
                config['entry_price'],
                config['take_profit_price'],
                config['current_position']
            ) 