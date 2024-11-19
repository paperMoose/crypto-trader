import asyncio
import logging
from datetime import datetime
from trader.database import init_db, get_engine, get_session
from trader.gemini.client import GeminiClient
from trader.strategies import StrategyManager, StrategyType, StrategyState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Initialize database and clients
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    client = GeminiClient()
    
    # Initialize strategy manager
    manager = StrategyManager(session, client)
    
    # Define breakout strategy
    breakout_strategy = {
        "name": "DOGE Breakout $0.40",
        "type": StrategyType.BREAKOUT,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 60,
        "config": {
            "breakout_price": "0.40000",
            "amount": "2500",
            "take_profit_1": "0.41000",
            "take_profit_2": "0.42500",
            "stop_loss": "0.38200"
        }
    }
    
    # Define range strategy
    range_strategy = {
        "name": "DOGE Range 0.35-0.39",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 60,
        "config": {
            "support_price": "0.35500",    # Strong support level
            "resistance_price": "0.38800",  # Just below breakout level
            "stop_loss_price": "0.35000",   # Below support
            "amount": "2800"               # ~$1000 position
        }
    }
    
    try:
        # Create both strategies
        logger.info("Creating breakout strategy...")
        await manager.create_strategy(breakout_strategy)
        
        logger.info("Creating range strategy...")
        await manager.create_strategy(range_strategy)
        
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
