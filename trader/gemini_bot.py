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
        # {
        #     "name": "SOL Range Strategy take 2 12/1/24",
        #     "type": StrategyType.RANGE,
        #     "symbol": Symbol.SOLUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 5,
        #     "config": {
        #         "support_price": "233.50",    
        #         "resistance_price": "239.50",  
        #         "amount": "5",                 
        #         "stop_loss_price": "231.50",   
        #         # Risk: $10.00 ((233.50 - 231.50) * 5)
        #         # Reward: $30.00 ((239.50 - 233.50) * 5)
        #         # 3:1 reward-to-risk ratio
        #     }
        # },
        # {
        #     "name": "SOL Take Profit Strategy 12/1/24",
        #     "type": StrategyType.TAKE_PROFIT,
        #     "symbol": Symbol.SOLUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 5,
        #     "config": {
        #         "current_position": "5.000937",  # Your existing position
        #         "entry_price": "241.02",        # Approximate entry price
        #         "take_profit_price": "242.50",  # About 3.85% gain target
        #         "stop_loss_price": "231.50"     # About 0.85% risk
        #         # Risk: $10.00 ((233.50 - 231.50) * 5.000937)
        #         # Reward: $45.00 ((242.50 - 233.50) * 5.000937)
        #         # 4.5:1 reward-to-risk ratio
        #     }
        # },
        # {
        #     "name": "DOGE BB Pullback Strategy 12/1/24",
        #     "type": StrategyType.RANGE,
        #     "symbol": Symbol.DOGEUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 5,
        #     "config": {
        #         "support_price": "0.43700",    # Strong support from order book
        #         "resistance_price": "0.44500",  # Recent resistance level
        #         "amount": "2500",              # Keep same position size
        #         "stop_loss_price": "0.43200"   # Below current consolidation
        #         # Risk: $12.50 ((0.43700 - 0.43200) * 2500)
        #         # Reward: $20.00 ((0.44500 - 0.43700) * 2500)
        #         # Improved Reward-to-Risk Ratio: 1.6:1
        #     }
        # }, failed
        # {
        #     "name": "DOGE BB Breakout Strategy 12/1/24",
        #     "type": StrategyType.BREAKOUT,
        #     "symbol": Symbol.DOGEUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 3,
        #     "config": {
        #         "breakout_price": "0.46100",   # Breakout confirmation
        #         "stop_loss_price": "0.45500",  # Below middle BB
        #         "amount": "1000",              # Position size
        #         "take_profit_1": "0.46800",    # First target
        #         "take_profit_2": "0.47000"     # Extended target
        #         # Risk: $30 ((0.46100 - 0.45500) * 5000)
        #         # Reward T1: $35 ((0.46800 - 0.46100) * 5000)
        #         # Reward T2: $45 ((0.47000 - 0.46100) * 5000)
        #         # Average Reward-to-Risk: 1.33:1
        #     }
        # }, failed 
        {
            "name": "DOGE BB Reversal Strategy take 2 12/1/24",
            "type": StrategyType.RANGE,
            "symbol": Symbol.DOGEUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 5,
            "config": {
                "support_price": "0.39000",    # Just above lower BB
                "resistance_price": "0.42000", # Middle BB target
                "amount": "2500",             # Position size
                "stop_loss_price": "0.37000"  # Below lower BB
                # Risk: $50 ((0.39000 - 0.38000) * 5000)
                # Reward: $150 ((0.42000 - 0.39000) * 5000)
                # Reward-to-Risk Ratio: 3:1
            }
        },
        # {
        #     "name": "XRP BB Bounce Strategy 12/1/24",
        #     "type": StrategyType.RANGE,
        #     "symbol": Symbol.XRPUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 5,
        #     "config": {
        #         "support_price": "2.2838",    # Middle BB as strong support
        #         "resistance_price": "2.4200", # Near upper BB resistance
        #         "amount": "250",             # Position size
        #         "stop_loss_price": "2.2600"  # Below middle BB
        #     } success
        # },
        # {
        #     "name": "XRP BB Breakout Strategy take 2 12/1/24",
        #     "type": StrategyType.BREAKOUT,
        #     "symbol": Symbol.XRPUSD,
        #     "state": StrategyState.ACTIVE,
        #     "check_interval": 3,
        #     "config": {
        #         "breakout_price": "2.4200",   # Entry above current consolidation
        #         "stop_loss_price": "2.3600",  # Middle BB as strong support
        #         "amount": "250",              # Position size
        #         "take_profit_1": "2.475",    # First target at resistance cluster
        #         "take_profit_2": "2.535"     # Extended target with momentum
        #     }
        # } failed
        {
            "name": "XRP Momentum Continuation 2 12/2/24",
            "type": StrategyType.BREAKOUT,
            "symbol": Symbol.XRPUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "breakout_price": "2.4600",    # Confirmation above current resistance
                "stop_loss_price": "2.4200",   # Below recent support
                "amount": "250",               # Conservative position size
                "take_profit_1": "2.5000",     # First target at psychological level
                "take_profit_2": "2.5700"      # Second target at upper BB
                # Risk: 8 ((2.4600 - 2.4200) * 100)
                # Reward T1: $8 ((2.5000 - 2.4600) * 100)
                # Reward T2: $22 ((2.5700 - 2.4600) * 100)
                # Average Reward-to-Risk: 1.875:1
            }
        },
        {
            "name": "SOL Range Strategy take 3 12/2/24",
            "type": StrategyType.RANGE,
            "symbol": Symbol.SOLUSD,
            "state": StrategyState.ACTIVE,
            "check_interval": 3,
            "config": {
                "support_price": "228.00",     # Strong order book support
                "resistance_price": "229.50",   # Near-term resistance
                "amount": "5",                  # Increased position size for better profit potential
                "stop_loss_price": "227.50"     # Below BB lower band
                # Risk: $2.50 ((228.00 - 227.50) * 5)
                # Reward: $7.50 ((229.50 - 228.00) * 5)
                # 3:1 reward-to-risk ratio with higher position size
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
