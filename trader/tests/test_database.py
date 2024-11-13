import pytest
from sqlmodel import Session, SQLModel, create_engine
from ..models import Order
from database import (
    load_orders,
    get_open_buy_orders,
    save_order,
    update_order,
    get_order_by_id,
    get_orders_by_parent_id,
    delete_order
)
from client import OrderSide, OrderType, Symbol
from datetime import datetime

# Use an in-memory SQLite database for testing
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///test.db", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

@pytest.fixture
def sample_order_data():
    return {
        "order_id": "test123",
        "status": "open",
        "amount": "100",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": Symbol.DOGEUSD.value,
        "order_type": OrderType.EXCHANGE_LIMIT.value
    }

@pytest.fixture
def sample_sell_orders_data(sample_order_data):
    return [
        {
            "order_id": "sell1",
            "status": "open",
            "amount": "50",
            "price": "0.50",
            "side": OrderSide.SELL.value,
            "symbol": Symbol.DOGEUSD.value,
            "order_type": OrderType.EXCHANGE_LIMIT.value,
            "type": "take-profit-1",
            "parent_order_id": sample_order_data["order_id"]
        },
        {
            "order_id": "sell2",
            "status": "open",
            "amount": "50",
            "price": "0.60",
            "side": OrderSide.SELL.value,
            "symbol": Symbol.DOGEUSD.value,
            "order_type": OrderType.EXCHANGE_LIMIT.value,
            "type": "take-profit-2",
            "parent_order_id": sample_order_data["order_id"]
        }
    ]

def test_save_order(session, sample_order_data):
    order = save_order(sample_order_data)
    assert order.order_id == sample_order_data["order_id"]
    assert order.status == sample_order_data["status"]
    assert isinstance(order.created_at, datetime)
    assert isinstance(order.updated_at, datetime)

def test_load_orders(session, sample_order_data, sample_sell_orders_data):
    # Save multiple orders
    save_order(sample_order_data)
    for sell_order in sample_sell_orders_data:
        save_order(sell_order)
    
    orders = load_orders()
    assert len(orders) == 3
    assert any(order.order_id == sample_order_data["order_id"] for order in orders)
    assert any(order.order_id == "sell1" for order in orders)
    assert any(order.order_id == "sell2" for order in orders)

def test_get_open_buy_orders(session, sample_order_data, sample_sell_orders_data):
    # Save buy order
    save_order(sample_order_data)
    # Save sell orders
    for sell_order in sample_sell_orders_data:
        save_order(sell_order)
    
    open_buys = get_open_buy_orders()
    assert len(open_buys) == 1
    assert open_buys[0].order_id == sample_order_data["order_id"]
    assert open_buys[0].side == OrderSide.BUY.value

def test_update_order(session, sample_order_data):
    order = save_order(sample_order_data)
    original_updated_at = order.updated_at
    
    # Wait a moment to ensure updated_at will be different
    import time
    time.sleep(0.1)
    
    updated = update_order(order.order_id, status="filled", sell_orders_placed=True)
    assert updated.status == "filled"
    assert updated.sell_orders_placed is True
    assert updated.updated_at > original_updated_at

def test_get_order_by_id(session, sample_order_data):
    save_order(sample_order_data)
    
    order = get_order_by_id(sample_order_data["order_id"])
    assert order is not None
    assert order.order_id == sample_order_data["order_id"]
    
    # Test non-existent order
    assert get_order_by_id("nonexistent") is None

def test_get_orders_by_parent_id(session, sample_order_data, sample_sell_orders_data):
    # Save parent order
    save_order(sample_order_data)
    # Save child orders
    for sell_order in sample_sell_orders_data:
        save_order(sell_order)
    
    children = get_orders_by_parent_id(sample_order_data["order_id"])
    assert len(children) == 2
    assert all(child.parent_order_id == sample_order_data["order_id"] for child in children)

def test_delete_order(session, sample_order_data):
    save_order(sample_order_data)
    
    # Verify order exists
    assert get_order_by_id(sample_order_data["order_id"]) is not None
    
    # Delete order
    success = delete_order(sample_order_data["order_id"])
    assert success is True
    
    # Verify order was deleted
    assert get_order_by_id(sample_order_data["order_id"]) is None
    
    # Try to delete non-existent order
    assert delete_order("nonexistent") is False

def test_order_timestamps(session, sample_order_data):
    order = save_order(sample_order_data)
    assert order.created_at is not None
    assert order.updated_at is not None
    assert isinstance(order.created_at, datetime)
    assert isinstance(order.updated_at, datetime)
    assert order.created_at == order.updated_at

def test_order_relationships(session, sample_order_data, sample_sell_orders_data):
    # Save parent order
    parent = save_order(sample_order_data)
    
    # Save child orders
    children = []
    for sell_order in sample_sell_orders_data:
        child = save_order(sell_order)
        children.append(child)
    
    # Verify relationships
    assert all(child.parent_order_id == parent.order_id for child in children)
    db_children = get_orders_by_parent_id(parent.order_id)
    assert len(db_children) == len(children) 