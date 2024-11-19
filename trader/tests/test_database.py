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
        "status": OrderState.PLACED.value,
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
            "status": OrderState.PLACED.value,
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
            "status": OrderState.PLACED.value,
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

def test_save_strategy(engine, session, sample_strategy_data):
    strategy = save_strategy(sample_strategy_data, engine=engine)
    assert strategy.id is not None
    assert strategy.name == sample_strategy_data["name"]
    assert strategy.type == sample_strategy_data["type"]
    assert strategy.state == StrategyState.INIT
    assert strategy.is_active is True
    assert isinstance(strategy.created_at, datetime)
    assert isinstance(strategy.updated_at, datetime)
    assert isinstance(strategy.last_checked_at, datetime)

def test_get_active_strategies(engine, session, sample_strategy_data):
    # Save active strategy
    strategy1 = save_strategy(sample_strategy_data, engine=engine)
    
    # Save inactive strategy
    inactive_strategy_data = sample_strategy_data.copy()
    inactive_strategy_data["name"] = "Inactive Strategy"
    inactive_strategy_data["is_active"] = False
    strategy2 = save_strategy(inactive_strategy_data, engine=engine)
    
    # Save completed strategy
    completed_strategy_data = sample_strategy_data.copy()
    completed_strategy_data["name"] = "Completed Strategy"
    completed_strategy_data["state"] = StrategyState.COMPLETED
    strategy3 = save_strategy(completed_strategy_data, engine=engine)
    
    active_strategies = get_active_strategies(engine=engine)
    assert len(active_strategies) == 1
    assert active_strategies[0].id == strategy1.id

def test_update_strategy(engine, session, sample_strategy_data):
    strategy = save_strategy(sample_strategy_data, engine=engine)
    original_updated_at = strategy.updated_at
    
    import time
    time.sleep(0.1)
    
    # Update strategy state and config
    updated = update_strategy(
        strategy.id, 
        engine=engine, 
        state=StrategyState.ACTIVE,
        config={"new_param": "value"}
    )
    
    assert updated.state == StrategyState.ACTIVE
    assert updated.config["new_param"] == "value"
    assert updated.updated_at > original_updated_at

def test_get_strategy_by_id(engine, session, sample_strategy_data):
    strategy = save_strategy(sample_strategy_data, engine=engine)
    
    retrieved = get_strategy_by_id(strategy.id, engine=engine)
    assert retrieved is not None
    assert retrieved.id == strategy.id
    assert retrieved.name == strategy.name
    
    assert get_strategy_by_id(999, engine=engine) is None

def test_strategy_order_relationship(engine, session, sample_strategy_data, sample_order_data, sample_sell_orders_data):
    """Test strategy-order relationships"""
    # Create everything within the same session
    with Session(engine) as session:
        # Save strategy
        strategy = save_strategy(sample_strategy_data, session=session)
        
        # Create and link orders
        sample_order_data["strategy_id"] = strategy.id
        parent_order = save_order(sample_order_data, session=session)
        
        for sell_order in sample_sell_orders_data:
            sell_order["strategy_id"] = strategy.id
            save_order(sell_order, session=session)
        
        # Refresh strategy to load relationships
        session.refresh(strategy)
        
        # Test relationship from strategy to orders
        assert len(strategy.orders) > 0
        assert all(order.strategy_id == strategy.id for order in strategy.orders)
        
        # Test relationship from order to strategy
        for order in strategy.orders:
            assert order.strategy is not None
            assert order.strategy.id == strategy.id

def test_strategy_state_transitions(engine, session, sample_strategy_data):
    strategy = save_strategy(sample_strategy_data, engine=engine)
    
    # Test state transitions
    states = [
        StrategyState.ACTIVE,
        StrategyState.PAUSED,
        StrategyState.ACTIVE,
        StrategyState.COMPLETED
    ]
    
    for state in states:
        updated = update_strategy(strategy.id, engine=engine, state=state)
        assert updated.state == state

def test_strategy_validation(engine, session, sample_strategy_data):
    """Test strategy validation"""
    # Test required fields
    invalid_data = sample_strategy_data.copy()
    del invalid_data["name"]
    
    # Should raise IntegrityError, not ValueError
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        save_strategy(invalid_data, engine=engine)
    
    # Test enum validation
    invalid_data = sample_strategy_data.copy()
    invalid_data["type"] = "invalid_type"
    
    # This should raise ValueError due to invalid enum
    with pytest.raises(ValueError):
        save_strategy(invalid_data, engine=engine) 