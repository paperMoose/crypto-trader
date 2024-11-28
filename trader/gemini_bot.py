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
            "name": "DOGE Reversal Hunt 11-28-24",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.38000",    # Strong support level after 10% drop
                "resistance_price": "0.41000",  # Previous support becomes resistance
                "amount": "2000",              # Reduced size for initial position
                "stop_loss_price": "0.36100"   # 5% below entry
                # Risk: $38 ((0.38 - 0.361) * 2000)
                # Reward: $60 ((0.41 - 0.38) * 2000)
                # Capital required: ~$760
            }
        },
        {
            "name": "DOGE Deep Reversal 11-28-24",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.36500",    # Major support if we get bigger drop
                "resistance_price": "0.39500",  # Previous support becomes resistance
                "amount": "2500",              # Larger size for better level
                "stop_loss_price": "0.34675"   # 5% below entry
                # Risk: $45.62 ((0.365 - 0.34675) * 2500)
                # Reward: $75 ((0.395 - 0.365) * 2500)
                # Capital required: ~$912
            }
        },
        {
            "name": "DOGE Extreme Drop 11-28-24",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.35000",    # Major psychological support
                "resistance_price": "0.38000",  # Previous support becomes resistance
                "amount": "3000",              # Largest size for best level
                "stop_loss_price": "0.33250"   # 5% below entry
                # Risk: $52.5 ((0.35 - 0.3325) * 3000)
                # Reward: $90 ((0.38 - 0.35) * 3000)
                # Capital required: ~$1,050
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
