import asyncio
import logging
from trader.database import init_db, get_engine, get_session, get_strategy_by_name
from trader.gemini.client import GeminiClient
from trader.models import StrategyState, StrategyType, Status
from trader.strategies import StrategyManager
from sqlalchemy import select
from trader.models import TradingStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def deactivate_removed_strategies(manager: StrategyManager, session, current_strategy_names: set) -> None:
    """Deactivate strategies that are no longer in the configuration"""
    try:
        # Get all active strategies from database
        stmt = select(TradingStrategy).where(TradingStrategy.is_active == True)
        active_strategies = session.exec(stmt).all()
        
        # Find strategies to deactivate
        for strategy in active_strategies:
            if strategy.name not in current_strategy_names:
                logger.info(f"Deactivating removed strategy: {strategy.name}")
                await manager.deactivate_strategy(strategy.name)
                
                # Update strategy status
                strategy.is_active = False
                strategy.status = Status.CANCELLED
                session.add(strategy)
                
        session.commit()
        
    except Exception as e:
        logger.error(f"Error deactivating removed strategies: {str(e)}")
        raise

async def update_or_create_strategy(manager: StrategyManager, strategy_data: dict) -> None:
    """Update existing strategy or create new one"""
    try:
        strategy_name = strategy_data["name"]
        logger.info(f"Processing strategy: {strategy_name}")
        
        # Update or create strategy
        strategy = await manager.create_strategy(strategy_data)
        logger.info(f"Strategy {strategy_name} {'updated' if strategy else 'created'}")
        
    except Exception as e:
        logger.error(f"Error processing strategy {strategy_data['name']}: {str(e)}")
        raise

async def main():
    # Initialize database and clients
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    client = GeminiClient()
    
    # Initialize strategy manager
    manager = StrategyManager(session, client)
    
    # Define strategies
    strategies = [
        # Range strategy
        {
            "name": "DOGE Range 0.408-0.420 (Position 1)",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.40800",
                "resistance_price": "0.42000",
                "stop_loss_price": "0.40400",
                "amount": "5000"              # First 5000 DOGE position
            }
        }
    ]
    
    try:
        # Get current strategy names
        current_strategy_names = {s["name"] for s in strategies}
        
        # Deactivate removed strategies
        await deactivate_removed_strategies(manager, session, current_strategy_names)
        
        # Process each strategy
        for strategy_data in strategies:
            await update_or_create_strategy(manager, strategy_data)
        
        logger.info("Starting strategy monitor...")
        # Start monitoring - this will run indefinitely
        await manager.monitor_strategies()
        
    except Exception as e:
        logger.error(f"Error running strategies: {str(e)}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {str(e)}")
