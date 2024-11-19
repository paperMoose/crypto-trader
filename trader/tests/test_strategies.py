import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from trader.strategies import RangeStrategy, BreakoutStrategy, StrategyManager, BaseStrategy
from trader.models import Order, OrderState, OrderType, StrategyType, StrategyState, TradingStrategy
from trader.gemini.enums import Symbol, OrderSide, OrderType as GeminiOrderType
from trader.database import get_active_strategies, save_strategy, save_order

# Test Data Fixtures
@pytest.fixture
def range_strategy_data():
    return {
        "name": "Test Range Strategy",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE.value,
        "check_interval": 60,
        "config": {
            "support_price": "0.30",
            "resistance_price": "0.35",
            "stop_loss_price": "0.29",
            "amount": "1000"
        }
    }

@pytest.fixture
def breakout_strategy_data():
    return {
        "name": "Test Breakout Strategy",
        "type": StrategyType.BREAKOUT,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE.value,
        "check_interval": 60,
        "config": {
            "breakout_price": "0.35",
            "amount": "1000",
            "take_profit_1": "0.37",
            "take_profit_2": "0.40",
            "stop_loss": "0.33"
        }
    }


# Base Strategy Tests
def test_base_strategy_abstract():
    """Test that BaseStrategy cannot be instantiated directly"""
    with pytest.raises(TypeError):
        BaseStrategy(Mock())

# Range Strategy Tests
def test_range_strategy_validate_config():
    """Test range strategy configuration validation"""
    strategy = RangeStrategy(Mock())
    
    valid_config = {
        "support_price": "0.30",
        "resistance_price": "0.35",
        "stop_loss_price": "0.29",
        "amount": "1000"
    }
    assert strategy.validate_config(valid_config) is True
    
    invalid_config = {
        "support_price": "0.30",
        "resistance_price": "0.35"
    }
    assert strategy.validate_config(invalid_config) is False

@pytest.mark.asyncio
async def test_range_strategy_initial_orders(session, mock_gemini_client, range_strategy_data):
    """Test that range strategy places initial buy and sell orders correctly"""
    mock_gemini_client.place_order.side_effect = [
        type('Response', (), {'order_id': 'test_buy_123'}),
        type('Response', (), {'order_id': 'test_sell_123'})
    ]
    
    strategy = TradingStrategy(**range_strategy_data)
    session.add(strategy)
    session.commit()
    
    range_strategy = RangeStrategy(mock_gemini_client)
    await range_strategy.execute(strategy, session)
    
    assert mock_gemini_client.place_order.call_count == 2
    
    buy_call = mock_gemini_client.place_order.call_args_list[0][1]
    assert buy_call["side"] == OrderSide.BUY
    assert buy_call["price"] == "0.30"
    assert buy_call["amount"] == "1000"
    
    sell_call = mock_gemini_client.place_order.call_args_list[1][1]
    assert sell_call["side"] == OrderSide.SELL
    assert sell_call["price"] == "0.35"
    assert sell_call["amount"] == "1000"

@pytest.mark.asyncio
async def test_range_strategy_existing_orders(session, mock_gemini_client, range_strategy_data):
    """Test that range strategy doesn't place duplicate orders when valid orders exist"""
    # Use save_strategy with the data dictionary directly
    strategy = save_strategy(range_strategy_data, session)
    
    # Add existing ACTIVE orders using save_order
    existing_orders_data = [
        {
            "order_id": "existing_buy_123",
            "status": OrderState.ACTIVE,
            "amount": "1000",
            "price": "0.30",
            "side": OrderSide.BUY.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_BUY,
            "strategy_id": strategy.id
        },
        {
            "order_id": "existing_sell_123",
            "status": OrderState.ACTIVE,
            "amount": "1000",
            "price": "0.35",
            "side": OrderSide.SELL.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_SELL,
            "strategy_id": strategy.id
        }
    ]
    
    for order_data in existing_orders_data:
        save_order(order_data, session)
    
    # Mock get_orders to return the existing orders
    mock_gemini_client.get_orders.return_value = [
        type('Response', (), {'order_id': 'existing_buy_123', 'is_live': True}),
        type('Response', (), {'order_id': 'existing_sell_123', 'is_live': True})
    ]
    
    range_strategy = RangeStrategy(mock_gemini_client)
    await range_strategy.execute(strategy, session)
    
    # Verify no new orders were placed since active orders exist
    assert mock_gemini_client.place_order.call_count == 0

# Breakout Strategy Tests
def test_breakout_strategy_validate_config():
    """Test breakout strategy configuration validation"""
    strategy = BreakoutStrategy(Mock())
    
    valid_config = {
        "breakout_price": "0.35",
        "amount": "1000",
        "take_profit_1": "0.37",
        "take_profit_2": "0.40",
        "stop_loss": "0.33"
    }
    assert strategy.validate_config(valid_config) is True
    
    invalid_config = {
        "breakout_price": "0.35",
        "amount": "1000"
    }
    assert strategy.validate_config(invalid_config) is False

@pytest.mark.asyncio
async def test_breakout_strategy_initial_order(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy places initial stop order correctly"""
    mock_gemini_client.place_order.return_value = type('Response', (), {'order_id': 'test_buy_123'})
    
    strategy = TradingStrategy(**breakout_strategy_data)
    session.add(strategy)
    session.commit()
    
    breakout_strategy = BreakoutStrategy(mock_gemini_client)
    await breakout_strategy.execute(strategy, session)
    
    mock_gemini_client.place_order.assert_called_once()
    call_args = mock_gemini_client.place_order.call_args[1]
    assert call_args["side"] == OrderSide.BUY
    assert call_args["price"] == "0.35"
    assert call_args["amount"] == "1000"
    assert call_args["order_type"] == GeminiOrderType.EXCHANGE_STOP_LIMIT
    assert float(call_args["stop_price"]) < float(call_args["price"])

@pytest.mark.asyncio
async def test_breakout_strategy_take_profit_orders(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy places take profit orders after initial order fills"""
    # Create strategy using save_strategy
    strategy = save_strategy(breakout_strategy_data, session)
    
    # Create filled buy order using save_order
    buy_order_data = {
        "order_id": "test_buy_123",
        "status": OrderState.FILLED,
        "amount": "1000",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": "dogeusd",
        "order_type": OrderType.STOP_LIMIT_BUY,
        "strategy_id": strategy.id
    }
    buy_order = save_order(buy_order_data, session)
    
    # Mock get_orders to return empty list (no existing orders)
    mock_gemini_client.get_orders.return_value = []
    
    # Configure mock responses with unique order IDs
    mock_responses = [
        type('Response', (), {'order_id': f'test_tp{i}_123'})
        for i in range(1, 4)
    ]
    mock_gemini_client.place_order.side_effect = mock_responses
    
    breakout_strategy = BreakoutStrategy(mock_gemini_client)
    await breakout_strategy.execute(strategy, session)
    
    # Verify take profit and stop loss orders were placed
    assert mock_gemini_client.place_order.call_count == 3
    
    calls = mock_gemini_client.place_order.call_args_list
    assert len(calls) == 3
    
    # Verify order parameters
    tp1_call = calls[0][1]
    assert tp1_call['price'] == breakout_strategy_data['config']['take_profit_1']
    assert tp1_call['amount'] == str(float(breakout_strategy_data['config']['amount']) / 2)
    
    tp2_call = calls[1][1]
    assert tp2_call['price'] == breakout_strategy_data['config']['take_profit_2']
    assert tp2_call['amount'] == str(float(breakout_strategy_data['config']['amount']) / 2)
    
    sl_call = calls[2][1]
    assert sl_call['price'] == breakout_strategy_data['config']['stop_loss']
    assert sl_call['amount'] == breakout_strategy_data['config']['amount']

# Strategy Manager Tests
@pytest.mark.asyncio
async def test_strategy_manager_create_strategy(session, mock_gemini_client, range_strategy_data):
    """Test strategy creation through manager"""
    manager = StrategyManager(session, mock_gemini_client)
    strategy = await manager.create_strategy(range_strategy_data)
    
    assert strategy.id is not None
    assert strategy.type == StrategyType.RANGE
    assert strategy.name == range_strategy_data["name"]

@pytest.mark.asyncio
async def test_strategy_manager_update_orders(session, mock_gemini_client):
    """Test order status updates through manager"""
    manager = StrategyManager(session, mock_gemini_client)
    
    strategy = TradingStrategy(
        name="Test Strategy",
        type=StrategyType.RANGE,
        symbol="dogeusd",
        state=StrategyState.ACTIVE.value,
        check_interval=60
    )
    session.add(strategy)
    session.commit()
    
    order = Order(
        order_id="test_order_123",
        status=OrderState.PLACED,
        amount="1000",
        price="0.35",
        side=OrderSide.BUY.value,
        symbol="dogeusd",
        order_type=OrderType.LIMIT_BUY,
        strategy_id=strategy.id
    )
    session.add(order)
    session.commit()
    
    # Mock the order status response
    mock_gemini_client.check_order_status.return_value = type(
        'Response', (), {'status': 'filled'}  # Use string value instead of enum
    )
    
    await manager.update_orders(strategy)
    session.refresh(order)  # Refresh from DB
    
    assert order.status == OrderState.FILLED

@pytest.mark.asyncio
async def test_strategy_manager_monitor_strategies(session, mock_gemini_client, range_strategy_data):
    """Test strategy monitoring"""
    manager = StrategyManager(session, mock_gemini_client)
    strategy = await manager.create_strategy(range_strategy_data)
    
    # Mock the infinite loop to run once
    async def mock_monitor(self):  # Add self parameter
        strategies = [strategy]
        for s in strategies:
            await manager.update_orders(s)
            await manager.strategies[s.type].execute(s, session)
    
    # Configure place_order mock
    mock_gemini_client.place_order.side_effect = [
        type('Response', (), {'order_id': 'test_buy_123'}),
        type('Response', (), {'order_id': 'test_sell_123'})
    ]
    
    with patch.object(StrategyManager, 'monitor_strategies', mock_monitor):
        await manager.monitor_strategies()
        assert mock_gemini_client.place_order.call_count == 2