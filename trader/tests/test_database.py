import pytest
import sqlalchemy
from datetime import datetime
from sqlmodel import Session
from trader.database import (
    load_orders,
    get_open_buy_orders,
    save_order,
    update_order,
    get_order_by_id,
    get_orders_by_parent_id,
    delete_order,
    save_strategy,
    get_active_strategies,
    get_strategy_by_id,
    update_strategy
)
from trader.gemini.enums import OrderSide, Symbol
from trader.models import OrderState, StrategyType, StrategyState

@pytest.fixture
def sample_order_data():
    return {
        "order_id": "test123",
        "status": OrderState.ACCEPTED.value,
        "amount": "100",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": Symbol.DOGEUSD.value,
        "order_type": "limit_buy"
    }

@pytest.fixture
def sample_sell_orders_data(sample_order_data):
    return [
        {
            "order_id": "sell1",
            "status": OrderState.ACCEPTED.value,
            "amount": "50",
            "price": "0.50",
            "side": OrderSide.SELL.value,
            "symbol": Symbol.DOGEUSD.value,
            "order_type": "limit_sell",
            "type": "take-profit-1",
            "parent_order_id": sample_order_data["order_id"]
        },
        {
            "order_id": "sell2",
            "status": OrderState.ACCEPTED.value,
            "amount": "50",
            "price": "0.60",
            "side": OrderSide.SELL.value,
            "symbol": Symbol.DOGEUSD.value,
            "order_type": "limit_sell",
            "type": "take-profit-2",
            "parent_order_id": sample_order_data["order_id"]
        }
    ]

@pytest.fixture
def sample_strategy_data():
    return {
        "name": "Test Range Strategy",
        "type": StrategyType.RANGE,
        "symbol": Symbol.DOGEUSD.value,
        "config": {
            "support_price": "0.30",
            "resistance_price": "0.35",
            "amount": "1000",
            "stop_loss_price": "0.29"
        },
        "check_interval": 60
    }

@pytest.fixture
def sample_strategy_with_orders(engine, session, sample_strategy_data, sample_order_data, sample_sell_orders_data):
    strategy = save_strategy(sample_strategy_data, engine=engine)
    
    # Link orders to strategy
    sample_order_data["strategy_id"] = strategy.id
    parent_order = save_order(sample_order_data, engine=engine)
    
    for sell_order in sample_sell_orders_data:
        sell_order["strategy_id"] = strategy.id
        save_order(sell_order, engine=engine)
    
    return strategy

def test_save_order(session):
    # Your test code here
    # Uses the session fixture which automatically handles cleanup
    pass

def test_get_orders(session):
    # Your test code here
    pass 