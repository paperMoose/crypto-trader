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
            "name": "DOGE Range 11-22-24 (0.44-0.47)",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "config": {
                "support_price": "0.44500",    # New support at previous resistance
                "resistance_price": "0.47000",  # New resistance level
                "amount": "3000",              # ~$1,335 position
                "stop_loss_price": "0.43500"   # Below support
                # Risk: $30 ((0.445 - 0.435) * 3000)
                # Reward: $75 ((0.47 - 0.445) * 3000)
                # Capital required: ~$1,335
            }
        },
        {
            "name": "DOGE Range 11-22-24 (0.43-0.45)",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.43000",    # Strong technical support
                "resistance_price": "0.45000",  # Previous support becomes resistance
                "amount": "3500",              # ~$1,505 position
                "stop_loss_price": "0.42000"   # Below major support
                # Risk: $35 ((0.43 - 0.42) * 3500)
                # Reward: $70 ((0.45 - 0.43) * 3500)
                # Capital required: ~$1,505
            }
        },
        {
            "name": "DOGE Range 11-22-24 (0.41-0.43)",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.41000",    # Previous resistance turned support
                "resistance_price": "0.43000",  # Previous support becomes resistance
                "amount": "3500",              # ~$1,435 position
                "stop_loss_price": "0.40000"   # Below major support
                # Risk: $35 ((0.41 - 0.40) * 3500)
                # Reward: $70 ((0.43 - 0.41) * 3500)
                # Capital required: ~$1,435
            }
        },
        {
            "name": "DOGE Breakout 11-23-24 (Above 0.47)",
            "type": StrategyType.BREAKOUT,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "config": {
                "breakout_price": "0.47100",   # Entry above recent high
                "amount": "3000",              # ~$1,413 position
                "take_profit_1": "0.50000",    # First target at psychological level
                "take_profit_2": "0.52000",    # Second target at next resistance
                "stop_loss": "0.46000"         # Below recent support
                # Risk: $33 ((0.471 - 0.46) * 3000)
                # Reward 1: $87 ((0.50 - 0.471) * 3000)
                # Reward 2: $147 ((0.52 - 0.471) * 3000)
                # Capital required: ~$1,413
            }
        },
        {
            "name": "DOGE Range 11-23-24 (0.425-0.445)",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.42500",    # Current consolidation support
                "resistance_price": "0.44500",  # Previous support now resistance
                "amount": "3500",              # ~$1,487 position
                "stop_loss_price": "0.41500"   # Below recent support structure
                # Risk: $35 ((0.425 - 0.415) * 3500)
                # Reward: $70 ((0.445 - 0.425) * 3500)
                # Capital required: ~$1,487
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
