import asyncio
import logging
from trader.database import init_db, get_engine, get_session, get_strategy_by_name
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol
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
        # Don't raise the error, just log it and continue
        return

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
            "name": "SOL BB Bullish Breakout 12/4/23",
            "type": StrategyType.BREAKOUT,
            "symbol": Symbol.SOLUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "breakout_price": "236.26",    # Middle BB breakout level
                "stop_loss": "230.00",         # Below middle BB
                "amount": "5",                 # Position size
                "take_profit_1": "245.06",     # Upper BB target
                "take_profit_2": "250.00"      # Extended target on strong momentum
                # Risk: $31.30 ((236.26 - 230.00) * 5)
                # Reward T1: $44.00 ((245.06 - 236.26) * 5)
                # Reward T2: $68.70 ((250.00 - 236.26) * 5)
                # Average Reward-to-Risk ratio: ~1.8:1
            }
        },
        {
            "name": "SOL Bullish Breakout Strategy 12/3/24 v2",
            "type": StrategyType.BREAKOUT,
            "symbol": Symbol.SOLUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "breakout_price": "236.50",    # Above current consolidation
                "stop_loss": "232.50",         # Below recent support
                "amount": "5",                 # Position size
                "take_profit_1": "240.50",     # First target at recent high
                "take_profit_2": "242.50"      # Extended target at next resistance
                # Risk: $10.00 ((236.50 - 234.50) * 5)
                # Reward T1: $10.00 ((238.50 - 236.50) * 5)
                # Reward T2: $20.00 ((240.50 - 236.50) * 5)
                # Average Reward-to-Risk: 1.5:1
            }
        },
        {
            "name": "XRP Momentum Continuation pt 2 12/3/24",
            "type": StrategyType.RANGE,
            "symbol": Symbol.XRPUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
                "config": {
                    "support_price": "2.65",
                    "resistance_price": "2.74",
                    "amount": "750",
                    "stop_loss_price": "2.60",
            }
        },
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
            # Don't raise the error, just log it and continue running
        await manager.monitor_strategies()  # Continue monitoring anyway
    finally:
        session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Bot stopped due to critical error: {str(e)}")
        raise
