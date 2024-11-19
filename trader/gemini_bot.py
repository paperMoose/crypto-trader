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
            "name": "DOGE Range Trade 0.38-0.42",
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "0.38000",    # Buy zone
                "resistance_price": "0.42000",  # Sell zone
                "amount": "5000",              # 5000 DOGE position
                "stop_loss_price": "0.37000"   # Stop loss below support
                # Max Gain: $200 ((0.42 - 0.38) * 5000 = $200 or 10.5%)
                # Max Loss: $50 ((0.38 - 0.37) * 5000 = $50 or 2.6%)
                # Risk:Reward Ratio = 1:4
            }
        },
        {
            "name": "DOGE Breakout Above 0.42",
            "type": StrategyType.BREAKOUT,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "breakout_price": "0.42100",   # Entry above resistance
                "amount": "5000",              # 5000 DOGE position
                "take_profit_1": "0.45000",    # First target (50% of position)
                "take_profit_2": "0.48000",    # Second target (50% of position)
                "stop_loss": "0.41000"         # Tighter stop loss
                # Max Gain: $295 (Average of both targets: (0.45 + 0.48)/2 - 0.421) * 5000 = $295 or 14%
                # Max Loss: $55 ((0.421 - 0.41) * 5000 = $55 or 2.6%)
                # Risk:Reward Ratio = 1:5.4
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
