import asyncio
import logging
from trader.database import init_db, get_engine, get_session, get_strategy_by_name
from trader.gemini.client import GeminiClient
from trader.models import StrategyState, StrategyType
from trader.strategies import StrategyManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        # Breakout strategy
        {
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
        },
        # Range strategy
        {
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
    ]
    
    try:
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
