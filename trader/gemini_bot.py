import asyncio
import logging
from trader.database import init_db, get_engine, get_session, get_strategy_by_name
from trader.gemini.client import GeminiClient
from trader.models import StrategyState
from trader.strategies import StrategyManager, StrategyType

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
    
    # Update breakout strategy
    breakout_strategy = {
        "name": "DOGE Breakout $0.40",
        "type": StrategyType.BREAKOUT,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 3,
        "config": {
            "breakout_price": "0.40000",
            "amount": "1250",
            "take_profit_1": "0.42500",  # Expected profit: 6.25% ($31.25)
            "take_profit_2": "0.44000",  # Expected profit: 10% ($50.00)
            "stop_loss": "0.41000"       # Expected loss: 2.5% ($12.50)
        }
    }
    
    # Update range strategy
    range_strategy = {
        "name": "DOGE Range 0.385-0.398",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 3,
        "config": {
            "support_price": "0.38500",   # Expected buy price
            "resistance_price": "0.39800",  # Expected sell price, profit: 3.38% ($51.80)
            "stop_loss_price": "0.38200",   # Expected loss: 0.78% ($12.00)
            "amount": "4000"
        }
    }
    
    try:
        # Update both strategies with new orders if config changed
        await manager.update_strategy_orders(breakout_strategy)
        await manager.update_strategy_orders(range_strategy)
        
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
