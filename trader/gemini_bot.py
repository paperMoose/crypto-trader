import asyncio
import logging
from trader.database import init_db, get_engine, get_session, get_strategy_by_name
from trader.gemini.client import GeminiClient
from trader.models import StrategyState, StrategyType
from trader.strategies import StrategyManager
from sqlmodel import select
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
                strategy.state = StrategyState.CANCELED
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
    init_db()
    session = get_session(engine)
    client = GeminiClient()
    
    # Initialize strategy manager
    manager = StrategyManager(session, client)
    
    # Define strategies
    strategies = [
        {
            "name": "DOGE Range Strategy 11/29/24",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 5,  # Longer interval to avoid noise
            "config": {
                "support_price": "0.40000",    # Major psychological support
                "resistance_price": "0.43000",  # Wider range for better R:R
                "amount": "2000",              # Single position size
                "stop_loss_price": "0.38500"   # More room for price movement
                # Risk: $30 ((0.40 - 0.385) * 2000)
                # Reward: $60 ((0.43 - 0.40) * 2000)
                # Better 2:1 reward-to-risk ratio
            }
        }
    ]
    
    try:
        # Get current strategy names
        current_strategy_names = {s["name"] for s in strategies}
        
        if strategies:  # Only log if we have strategies
            # Deactivate removed strategies
            await deactivate_removed_strategies(manager, session, current_strategy_names)
            
            # Process each strategy
            for strategy_data in strategies:
                await update_or_create_strategy(manager, strategy_data)
            
            logger.info("Starting strategy monitor...")
        else:
            logger.info("No strategies defined. Starting monitor in passive mode...")
            
        # Start monitoring - this will run indefinitely
        await manager.monitor_strategies()
        
    except Exception as e:
        if strategies:  # Only log error if we had strategies
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
