import pytest
from unittest.mock import Mock, patch
from sqlmodel import Session, select
from trader.strategies import RangeStrategy, BreakoutStrategy, StrategyManager, BaseStrategy
from trader.models import Order, OrderState, OrderType, StrategyType, StrategyState, TradingStrategy
from trader.gemini.enums import OrderSide, OrderType as GeminiOrderType
from trader.database import save_strategy, save_order, update_order
from datetime import datetime, timedelta


# Test Data Fixtures
@pytest.fixture
def range_strategy_data():
    return {
        "name": "Test Range Strategy",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
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
        "state": StrategyState.ACTIVE,
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
    """Test that range strategy places initial buy order correctly"""
    mock_gemini_client.place_order.return_value = type('Response', (), {'order_id': 'test_buy_123'})
    
    strategy = TradingStrategy(**range_strategy_data)
    session.add(strategy)
    session.commit()
    
    range_strategy = RangeStrategy(mock_gemini_client)
    await range_strategy.execute(strategy, session)
    
    # Should only place buy order initially
    assert mock_gemini_client.place_order.call_count == 1
    
    buy_call = mock_gemini_client.place_order.call_args[1]
    assert buy_call["side"] == OrderSide.BUY
    assert buy_call["price"] == "0.30"
    assert buy_call["amount"] == "1000"

@pytest.mark.asyncio
async def test_range_strategy_filled_buy_order(session, mock_gemini_client, range_strategy_data):
    """Test that range strategy places sell orders after buy order fills"""
    strategy = TradingStrategy(**range_strategy_data)
    session.add(strategy)
    session.commit()
    
    # Create filled buy order
    buy_order = Order(
        order_id="test_buy_123",
        status=OrderState.FILLED,
        amount="1000",
        price="0.30",
        side=OrderSide.BUY.value,
        symbol=strategy.symbol,
        order_type=OrderType.LIMIT_BUY,
        strategy_id=strategy.id
    )
    session.add(buy_order)
    session.commit()
    
    # Configure mock for current price check
    mock_gemini_client.get_price.return_value = "0.32"  # Price above stop loss
    
    # Configure mock for sell order
    mock_gemini_client.place_order.return_value = create_mock_order_response(
        'test_sell_123',
        price=strategy.config['resistance_price']
    )
    
    range_strategy = RangeStrategy(mock_gemini_client)
    await range_strategy.execute(strategy, session)
    
    # Should place sell order at resistance
    assert mock_gemini_client.place_order.call_count == 1
    call_args = mock_gemini_client.place_order.call_args[1]
    assert call_args["side"] == OrderSide.SELL
    assert call_args["price"] == strategy.config['resistance_price']

@pytest.mark.asyncio
async def test_range_strategy_existing_orders(session, mock_gemini_client, range_strategy_data):
    """Test that range strategy doesn't place duplicate orders when valid orders exist"""
    # Use save_strategy with the data dictionary directly
    strategy = save_strategy(range_strategy_data, session)
    
    # Add existing LIVE orders using save_order
    existing_orders_data = [
        {
            "order_id": "existing_buy_123",
            "status": OrderState.LIVE.value,
            "amount": "1000",
            "price": "0.30",
            "side": OrderSide.BUY.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_BUY,
            "strategy_id": strategy.id
        },
        {
            "order_id": "existing_sell_123",
            "status": OrderState.LIVE.value,
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
    mock_gemini_client.place_order.return_value = create_mock_order_response('test_buy_123')
    
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
    assert call_args["order_type"] == GeminiOrderType.EXCHANGE_LIMIT

@pytest.mark.asyncio
async def test_breakout_strategy_take_profit_orders(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy places take profit orders after initial order fills"""
    strategy = save_strategy(breakout_strategy_data, session)
    
    # Create filled buy order using save_order
    buy_order_data = {
        "order_id": "test_buy_123",
        "status": OrderState.FILLED,
        "amount": "1000",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": "dogeusd",
        "order_type": OrderType.LIMIT_BUY,
        "strategy_id": strategy.id
    }
    buy_order = save_order(buy_order_data, session)
    
    # Mock get_orders to return empty list (no existing orders)
    mock_gemini_client.get_orders.return_value = []
    
    # Configure mock responses with proper fields
    mock_responses = [
        create_mock_order_response(f'test_tp{i}_123', 
            amount=str(float(breakout_strategy_data['config']['amount'])/2),
            side=OrderSide.SELL.value)
        for i in range(1, 3)
    ]
    mock_gemini_client.place_order.side_effect = mock_responses
    
    # Mock current price above stop loss
    mock_gemini_client.get_price.return_value = "0.34"
    
    breakout_strategy = BreakoutStrategy(mock_gemini_client)
    await breakout_strategy.execute(strategy, session)
    
    # Verify take profit orders were placed
    assert mock_gemini_client.place_order.call_count == 2  # Only 2 take profit orders
    
    calls = mock_gemini_client.place_order.call_args_list
    assert len(calls) == 2
    
    # Verify order parameters
    tp1_call = calls[0][1]
    assert tp1_call['price'] == breakout_strategy_data['config']['take_profit_1']
    assert tp1_call['amount'] == str(float(breakout_strategy_data['config']['amount']) / 2)
    
    tp2_call = calls[1][1]
    assert tp2_call['price'] == breakout_strategy_data['config']['take_profit_2']
    assert tp2_call['amount'] == str(float(breakout_strategy_data['config']['amount']) / 2)

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
        state=StrategyState.ACTIVE,
        check_interval=10
    )
    strategy = save_strategy(strategy.model_dump(), session)
    
    # Create initial order
    order = Order(
        order_id="test_order_123",
        status=OrderState.ACCEPTED,
        amount="1000",
        price="0.35",
        side=OrderSide.BUY.value,
        symbol="dogeusd",
        order_type=OrderType.LIMIT_BUY,
        strategy_id=strategy.id
    )
    order = save_order(order.model_dump(), session)
    
    # Mock the order status response
    mock_gemini_client.check_order_status.return_value = create_mock_order_response(
        'test_order_123',
        status=OrderState.FILLED,
        amount="1000",
        price="0.35"
    )
    
    # Use service directly instead of manager
    await manager.service.order_service.update_order_statuses(strategy)
    session.refresh(order)
    
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
            # Use service instead of manager.update_orders
            await self.service.order_service.update_order_statuses(s)
            await self.strategies[s.type].execute(s, session)
    
    # Configure place_order mock
    mock_gemini_client.place_order.side_effect = [
        type('Response', (), {'order_id': 'test_buy_123'}),
        type('Response', (), {'order_id': 'test_sell_123'})
    ]
    
    with patch.object(StrategyManager, 'monitor_strategies', mock_monitor):
        await manager.monitor_strategies()
        assert mock_gemini_client.place_order.call_count == 1

@pytest.mark.asyncio
async def test_strategy_manager_basic_cycle(session, mock_gemini_client, range_strategy_data):
    """Test basic strategy execution cycle"""
    manager = StrategyManager(session, mock_gemini_client)
    
    # Create strategy
    strategy = await manager.create_strategy(range_strategy_data)
    
    # Configure mock for initial buy order
    mock_gemini_client.place_order.return_value = create_mock_order_response(
        'buy_123',
        amount=range_strategy_data['config']['amount'],
        price=range_strategy_data['config']['support_price']
    )
    
    # First execution to place buy order
    mock_gemini_client.get_orders.return_value = []
    await manager.strategies[strategy.type].execute(strategy, session)
    
    # Update order status to filled
    mock_gemini_client.check_order_status.return_value = create_mock_order_response(
        'buy_123',
        status=OrderState.FILLED,
        amount=range_strategy_data['config']['amount'],
        price=range_strategy_data['config']['support_price']
    )
    
    # Use service instead of manager.update_orders
    await manager.service.order_service.update_order_statuses(strategy)
    
    # Mock current price
    mock_gemini_client.get_price.return_value = "0.32"
    
    # Configure mock for sell order
    mock_gemini_client.place_order.side_effect = [
        create_mock_order_response(
            'sell_123',
            side=OrderSide.SELL.value,
            price=range_strategy_data['config']['resistance_price']
        )
    ]
    
    # Execute again to place sell orders
    await manager.strategies[strategy.type].execute(strategy, session)
    
    # Verify orders
    session.refresh(strategy)
    assert len(strategy.orders) == 2  # Buy + Sell
    
    sell_order = next((o for o in strategy.orders if o.side == OrderSide.SELL.value), None)
    assert sell_order is not None
    assert sell_order.price == range_strategy_data['config']['resistance_price']

@pytest.mark.asyncio
async def test_breakout_strategy_order_flow(session, mock_gemini_client, breakout_strategy_data):
    """Test breakout strategy order placement flow"""
    manager = StrategyManager(session, mock_gemini_client)
    strategy = await manager.create_strategy(breakout_strategy_data)
    
    # Mock initial order placement
    mock_gemini_client.place_order.return_value = create_mock_order_response(
        'stop_123',
        amount=breakout_strategy_data['config']['amount'],
        price=breakout_strategy_data['config']['breakout_price']
    )
    
    # Execute initial cycle to place first order
    await manager.strategies[strategy.type].execute(strategy, session)
    
    # Verify initial order
    session.refresh(strategy)
    assert len(strategy.orders) == 1
    initial_order = strategy.orders[0]
    assert initial_order.order_type == OrderType.LIMIT_BUY
    
    # Mock order status as filled
    mock_gemini_client.check_order_status.return_value = create_mock_order_response(
        'stop_123',
        status=OrderState.FILLED,
        amount=breakout_strategy_data['config']['amount'],
        price=breakout_strategy_data['config']['breakout_price']
    )
    
    # Use service instead of manager.update_orders
    await manager.service.order_service.update_order_statuses(strategy)
    session.refresh(strategy)
    assert strategy.orders[0].status == OrderState.FILLED
    
    # Configure mock for take profit orders
    mock_responses = [
        create_mock_order_response(
            f'tp{i}_123',
            side=OrderSide.SELL.value,
            amount=str(float(breakout_strategy_data['config']['amount'])/2),
            price=breakout_strategy_data['config'][f'take_profit_{i}']
        )
        for i in range(1, 3)
    ]
    mock_gemini_client.place_order.side_effect = mock_responses
    
    # Mock current price above stop loss
    mock_gemini_client.get_price.return_value = "0.36"  # Above stop loss
    
    # Execute second cycle to place take profit orders
    await manager.strategies[strategy.type].execute(strategy, session)
    
    # Verify all orders
    session.refresh(strategy)
    assert len(strategy.orders) == 3  # Initial buy + 2 take profits
    
    # Verify take profit orders
    tp_orders = [o for o in strategy.orders if o.side == OrderSide.SELL.value]
    assert len(tp_orders) == 2
    
    # Verify take profit prices
    tp_prices = {o.price for o in tp_orders}
    expected_prices = {
        breakout_strategy_data['config']['take_profit_1'],
        breakout_strategy_data['config']['take_profit_2']
    }
    assert tp_prices == expected_prices

# Helper function to create mock order responses
def create_mock_order_response(order_id, status="accepted", **kwargs):
    """Create a mock order response with all required fields"""
    # Convert status string to OrderState if it isn't already
    if isinstance(status, str):
        status = OrderState(status)
    
    return type('Response', (), {
        'order_id': order_id,
        'status': status,  # This will be an OrderState enum
        'original_amount': kwargs.get('amount', '1000'),
        'price': kwargs.get('price', '0.35'),
        'side': kwargs.get('side', 'buy'),
        'symbol': kwargs.get('symbol', 'dogeusd'),
        'stop_price': kwargs.get('stop_price', None)
    })