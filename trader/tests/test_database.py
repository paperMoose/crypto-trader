import pytest
from sqlmodel import Session, SQLModel, create_engine
from ..models import Order
from trader.database import (
    load_orders,
    get_open_buy_orders,
    save_order,
    update_order,
    get_order_by_id,
    get_orders_by_parent_id,
    delete_order,
    init_db
)
from trader.gemini.client import OrderSide, OrderType, Symbol
from datetime import datetime
from trader.models import OrderState, OrderType

@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session

@pytest.fixture
def sample_order_data():
    return {
        "order_id": "test123",
        "status": OrderState.PENDING.value,
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
            "status": OrderState.PENDING.value,
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
            "status": OrderState.PENDING.value,
            "amount": "50",
            "price": "0.60",
            "side": OrderSide.SELL.value,
            "symbol": Symbol.DOGEUSD.value,
            "order_type": "limit_sell",
            "type": "take-profit-2",
            "parent_order_id": sample_order_data["order_id"]
        }
    ]

def test_save_order(engine, session, sample_order_data):
    order = save_order(sample_order_data, engine=engine)
    assert order.order_id == sample_order_data["order_id"]
    assert order.status == sample_order_data["status"]
    assert isinstance(order.created_at, datetime)
    assert isinstance(order.updated_at, datetime)

def test_load_orders(engine, session, sample_order_data, sample_sell_orders_data):
    save_order(sample_order_data, engine=engine)
    for sell_order in sample_sell_orders_data:
        save_order(sell_order, engine=engine)
    
    orders = load_orders(engine=engine)
    assert len(orders) == 3
    assert any(order.order_id == sample_order_data["order_id"] for order in orders)
    assert any(order.order_id == "sell1" for order in orders)
    assert any(order.order_id == "sell2" for order in orders)

def test_get_open_buy_orders(engine, session, sample_order_data, sample_sell_orders_data):
    save_order(sample_order_data, engine=engine)
    for sell_order in sample_sell_orders_data:
        save_order(sell_order, engine=engine)
    
    open_buys = get_open_buy_orders(engine=engine)
    assert len(open_buys) == 1
    assert open_buys[0].order_id == sample_order_data["order_id"]
    assert open_buys[0].side == OrderSide.BUY.value

def test_update_order(engine, session, sample_order_data):
    order = save_order(sample_order_data, engine=engine)
    original_updated_at = order.updated_at
    
    import time
    time.sleep(0.1)
    
    updated = update_order(order.order_id, engine=engine, status="filled")
    assert updated.status == "filled"
    assert updated.updated_at > original_updated_at

def test_get_order_by_id(engine, session, sample_order_data):
    save_order(sample_order_data, engine=engine)
    
    order = get_order_by_id(sample_order_data["order_id"], engine=engine)
    assert order is not None
    assert order.order_id == sample_order_data["order_id"]
    
    assert get_order_by_id("nonexistent", engine=engine) is None

def test_get_orders_by_parent_id(engine, session, sample_order_data, sample_sell_orders_data):
    save_order(sample_order_data, engine=engine)
    for sell_order in sample_sell_orders_data:
        save_order(sell_order, engine=engine)
    
    children = get_orders_by_parent_id(sample_order_data["order_id"], engine=engine)
    assert len(children) == 2
    assert all(child.parent_order_id == sample_order_data["order_id"] for child in children)

def test_delete_order(engine, session, sample_order_data):
    save_order(sample_order_data, engine=engine)
    
    assert get_order_by_id(sample_order_data["order_id"], engine=engine) is not None
    
    success = delete_order(sample_order_data["order_id"], engine=engine)
    assert success is True
    
    assert get_order_by_id(sample_order_data["order_id"], engine=engine) is None
    
    assert delete_order("nonexistent", engine=engine) is False

def test_order_timestamps(engine, session, sample_order_data):
    order = save_order(sample_order_data, engine=engine)
    assert order.created_at is not None
    assert order.updated_at is not None
    assert isinstance(order.created_at, datetime)
    assert isinstance(order.updated_at, datetime)
    assert abs((order.created_at - order.updated_at).total_seconds()) < 0.1

def test_order_relationships(engine, session, sample_order_data, sample_sell_orders_data):
    parent = save_order(sample_order_data, engine=engine)
    
    children = []
    for sell_order in sample_sell_orders_data:
        child = save_order(sell_order, engine=engine)
        children.append(child)
    
    assert all(child.parent_order_id == parent.order_id for child in children)
    db_children = get_orders_by_parent_id(parent.order_id, engine=engine)
    assert len(db_children) == len(children) 