import logging
import asyncio
from typing import Dict, Any
from sqlmodel import Session
from trader.gemini.client import GeminiClient
from trader.models import TradingStrategy
from trader.services import StrategyService
from . import STRATEGY_MAP

class StrategyManager:
    def __init__(self, session: Session, client: GeminiClient):
        self.session = session
        self.client = client
        self.logger = logging.getLogger("StrategyManager")
        self.strategies = STRATEGY_MAP
        self.service = StrategyService(client, session, self.strategies)
        self.logger.info("Strategy Manager initialized")

    async def monitor_strategies(self):
        """Monitor and execute all active strategies"""
        self.logger.info("Starting strategy monitor loop\n")
        
        while True:
            try:
                strategies = await self.service.get_active_strategies()
                self.logger.info(f"Found {len(strategies)} active strategies\n")
                
                for strategy in strategies:
                    self.logger.debug(f"Checking strategy: {strategy.name}")
                    
                    if await self.service.should_execute_strategy(strategy):
                        self.logger.info(f"Executing strategy: {strategy.name} (Type: {strategy.type})")
                        await self.strategies[strategy.type](self.client).execute(strategy, self.session)
                        await self.service.update_strategy_timestamp(strategy)
                        self.logger.info(f"Strategy execution completed: {strategy.name}\n")

                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error monitoring strategies: {str(e)}\n", exc_info=True)
                await asyncio.sleep(5)

    async def create_strategy(self, strategy_data: Dict[str, Any]) -> TradingStrategy:
        """Create and save a new trading strategy"""
        self.logger.info(f"Creating strategy: {strategy_data['name']}")
        try:
            return await self.service.update_strategy_orders(strategy_data)
        except Exception as e:
            self.logger.error(f"Error creating strategy: {str(e)}")
            raise

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

    async def get_active_strategies(self):
        return await self.service.get_active_strategies() 