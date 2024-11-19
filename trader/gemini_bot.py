import logging
from trader.gemini.client import GeminiClient, Symbol, OrderSide, OrderType
from trader.database import (
    get_open_buy_orders,
    save_order,
    update_order,
    init_db,
    get_engine
)
from sqlmodel import Session
import asyncio

from trader.strategies import StrategyManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

async def place_order(symbol, amount, price, side, order_type, stop_price=None):
    async with GeminiClient() as client:
        return await client.place_order(
            symbol=symbol,
            amount=amount,
            price=price,
            side=side,
            order_type=order_type,
            stop_price=stop_price
        )

async def check_order_status(order_id):
    async with GeminiClient() as client:
        return await client.check_order_status(order_id)

async def main():
    # Initialize database
    engine = get_engine()
    init_db(engine)
    
    # Create database session
    with Session(engine) as session:
        async with GeminiClient() as client:
            strategy_manager = StrategyManager(session, client)
            await strategy_manager.monitor_strategies()

if __name__ == "__main__":
    asyncio.run(main())
