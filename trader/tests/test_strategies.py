import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlmodel import Session, select
from trader.services import StrategyService
from trader.strategies import RangeStrategy, BreakoutStrategy, StrategyManager, BaseStrategy, TakeProfitStrategy
from trader.models import Order, OrderState, OrderType, StrategyType, StrategyState, TradingStrategy
from trader.gemini.enums import OrderSide, OrderType as GeminiOrderType
from trader.database import save_strategy, save_order, update_order
from datetime import datetime, timedelta
from asyncio import Future
from sqlalchemy import and_
from trader.tests.utils import create_mock_order_response


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

@pytest.fixture
def take_profit_strategy():
    client = Mock()
    return TakeProfitStrategy(client)

@pytest.fixture
def take_profit_config():
    return {
        "current_position": "10000",
        "entry_price": "0.40800",
        "take_profit_price": "0.42000",
        "stop_loss_price": "0.40400"
    }

@pytest.fixture
def take_profit_db_strategy(take_profit_config):
    return TradingStrategy(
        id=1,
        name="Test Take Profit Strategy",
        type=StrategyType.TAKE_PROFIT,
        symbol="dogeusd",
        config=take_profit_config,
        state=StrategyState.ACTIVE,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_checked_at=datetime.utcnow(),
        check_interval=1
    )


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
    mock_gemini_client.place_order.return_value = create_mock_order_response('test_buy_123')
    mock_gemini_client.get_price.return_value = "0.31"  # Price above stop loss
    
    strategy = TradingStrategy.model_validate(range_strategy_data)
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    
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
    session.refresh(strategy)
    
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
        price=strategy.config['resistance_price'],
        side=OrderSide.SELL.value
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
    strategy = save_strategy(range_strategy_data, session)
    session.refresh(strategy)
    
    # Add existing LIVE orders to the database
    order_data = [
        {
            "order_id": "existing_buy_123",
            "status": OrderState.LIVE,
            "amount": "1000",
            "price": "0.30",
            "side": OrderSide.BUY.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_BUY,
            "strategy_id": strategy.id
        },
        {
            "order_id": "existing_sell_123",
            "status": OrderState.LIVE,
            "amount": "1000",
            "price": "0.35",
            "side": OrderSide.SELL.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_SELL,
            "strategy_id": strategy.id
        }
    ]
    
    for data in order_data:
        order = Order(**data)
        session.add(order)
    session.commit()
    session.refresh(strategy)
    
    # Mock get_orders to return mock responses for API calls
    mock_responses = [
        create_mock_order_response('existing_buy_123', side=OrderSide.BUY.value, price="0.30"),
        create_mock_order_response('existing_sell_123', side=OrderSide.SELL.value, price="0.35")
    ]
    mock_gemini_client.get_orders.return_value = mock_responses
    
    # Mock get_price to avoid potential issues
    mock_gemini_client.get_price.return_value = "0.32"  # Some price above stop loss
    
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

@pytest.mark.asyncio
async def test_breakout_strategy_price_validation(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy validates price levels before placing orders"""
    strategy = BreakoutStrategy(mock_gemini_client)
    
    # Create strategy instance
    db_strategy = save_strategy(breakout_strategy_data, session)
    session.refresh(db_strategy)
    
    breakout_price = float(breakout_strategy_data['config']['breakout_price'])
    test_cases = [
        {
            "current_price": str(breakout_price * 0.996),  # Within 0.5% below breakout
            "should_place_order": True,
            "description": "Price near breakout level",
            "order_id": "test_order_1"
        },
        {
            "current_price": str(breakout_price * 0.99),  # Too far below breakout
            "should_place_order": False,
            "description": "Price too far below breakout",
            "order_id": "test_order_2"
        },
        {
            "current_price": str(breakout_price * 1.001),  # Just above breakout
            "should_place_order": True,
            "description": "Price above breakout",
            "order_id": "test_order_3"
        }
    ]
    
    for case in test_cases:
        # Reset database state
        statement = select(Order).where(Order.strategy_id == db_strategy.id)
        orders = session.exec(statement).all()
        for order in orders:
            session.delete(order)
        session.commit()
        session.refresh(db_strategy)
        
        # Reset mock and set current price
        mock_gemini_client.reset_mock()
        mock_gemini_client.get_price.return_value = case["current_price"]
        
        # Configure mock response for order placement using create_mock_order_response
        mock_gemini_client.place_order.return_value = create_mock_order_response(
            case["order_id"],
            status=OrderState.ACCEPTED
        )
        
        # Execute strategy
        await strategy.execute(db_strategy, session)
        session.refresh(db_strategy)  # Refresh after execution
        
        # Verify order placement behavior
        if case["should_place_order"]:
            assert mock_gemini_client.place_order.called, f"Failed on: {case['description']}"
            call_args = mock_gemini_client.place_order.call_args[1]
            assert call_args['price'] == breakout_strategy_data['config']['breakout_price']
            
            # Verify order was saved
            statement = select(Order).where(
                and_(
                    Order.strategy_id == db_strategy.id,
                    Order.order_id == case["order_id"]
                )
            )
            orders = session.exec(statement).all()
            assert len(orders) == 1
            order = orders[0]
            assert order.side == OrderSide.BUY.value
            assert order.price == breakout_strategy_data['config']['breakout_price']
        else:
            assert not mock_gemini_client.place_order.called, f"Should not place order: {case['description']}"
            statement = select(Order).where(Order.strategy_id == db_strategy.id)
            orders = session.exec(statement).all()
            assert len(orders) == 0

@pytest.mark.asyncio
async def test_breakout_strategy_prevents_premature_execution(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy doesn't execute prematurely"""
    strategy = BreakoutStrategy(mock_gemini_client)
    db_strategy = save_strategy(breakout_strategy_data, session)
    session.refresh(db_strategy)  # Ensure strategy is attached to session
    
    # Set current price well below breakout level
    mock_gemini_client.get_price.return_value = "0.30000"  # Well below breakout price
    
    # Configure mock response for order status check
    mock_status_response = Mock()
    mock_status_response.status = OrderState.ACCEPTED
    mock_gemini_client.check_order_status.return_value = mock_status_response
    
    # Execute strategy
    await strategy.execute(db_strategy, session)
    session.refresh(db_strategy)  # Refresh after execution
    
    # Verify no orders were placed
    assert not mock_gemini_client.place_order.called
    assert len(db_strategy.orders) == 0

@pytest.mark.asyncio
async def test_breakout_strategy_price_monitoring(session, mock_gemini_client, breakout_strategy_data):
    """Test that breakout strategy properly monitors price levels"""
    strategy = BreakoutStrategy(mock_gemini_client)
    db_strategy = save_strategy(breakout_strategy_data, session)
    session.refresh(db_strategy)
    
    # Simulate price approaching breakout level
    price_sequence = [
        "0.30000",  # Too far - no order
        "0.34800",  # Within range - should place order
        "0.35500",  # Above breakout - should maintain order
    ]
    
    for current_price in price_sequence:
        # Reset database state
        statement = select(Order).where(Order.strategy_id == db_strategy.id)
        orders = session.exec(statement).all()
        for order in orders:
            session.delete(order)
        session.commit()
        session.refresh(db_strategy)
        
        # Reset mock and set current price
        mock_gemini_client.reset_mock()
        mock_gemini_client.get_price.return_value = current_price
        
        # Configure mock response for order placement using create_mock_order_response
        mock_gemini_client.place_order.return_value = create_mock_order_response(
            "test_order_123",
            status=OrderState.ACCEPTED
        )
        
        # Execute strategy
        await strategy.execute(db_strategy, session)
        session.refresh(db_strategy)
        
        # Verify behavior based on price
        breakout_threshold = float(breakout_strategy_data['config']['breakout_price']) * 0.995
        if float(current_price) >= breakout_threshold:
            assert mock_gemini_client.place_order.called or len(db_strategy.orders) > 0
            if mock_gemini_client.place_order.called:
                call_args = mock_gemini_client.place_order.call_args[1]
                assert call_args['price'] == breakout_strategy_data['config']['breakout_price']
        else:
            assert not mock_gemini_client.place_order.called
            assert len(db_strategy.orders) == 0

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
    
    strategy_data = {
        "name": "Test Strategy",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 10,
        "config": {}  # Add minimal required config
    }
    strategy = TradingStrategy.model_validate(strategy_data)
    strategy = save_strategy(strategy.model_dump(), session)
    
    # Create initial order
    order_data = {
        "order_id": "test_order_123",
        "status": OrderState.ACCEPTED,
        "amount": "1000",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": "dogeusd",
        "order_type": OrderType.LIMIT_BUY,
        "strategy_id": strategy.id
    }
    order = Order.model_validate(order_data)
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
    session.refresh(strategy)  # Ensure strategy stays attached to session
    
    # Mock the infinite loop to run once
    async def mock_monitor(self):
        strategies = [strategy]
        for s in strategies:
            await self.service.order_service.update_order_statuses(s)
            await self.strategies[s.type].execute(s, session)
    
    # Configure place_order mock using create_mock_order_response
    mock_gemini_client.place_order.side_effect = [
        create_mock_order_response('test_buy_123'),
        create_mock_order_response('test_sell_123', side=OrderSide.SELL.value)
    ]
    
    # Mock get_price to avoid potential issues
    mock_gemini_client.get_price.return_value = "0.31"  # Price above stop loss
    
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
    session.refresh(strategy)
    
    # Mock initial order placement
    mock_gemini_client.place_order.return_value = create_mock_order_response(
        'stop_123',
        amount=breakout_strategy_data['config']['amount'],
        price=breakout_strategy_data['config']['breakout_price']
    )
    
    # Mock current price near breakout level
    mock_gemini_client.get_price.return_value = "0.349"  # Just below breakout
    
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

class TestTakeProfitStrategy:
    def test_validate_config_valid(self, take_profit_strategy, take_profit_config):
        """Test that a valid config passes validation"""
        assert take_profit_strategy.validate_config(take_profit_config) is True

    def test_validate_config_invalid(self, take_profit_strategy):
        """Test that invalid configs fail validation"""
        invalid_configs = [
            {},  # Empty config
            {"current_position": "10000"},  # Missing fields
            {  # Missing stop_loss_price
                "current_position": "10000",
                "entry_price": "0.40800",
                "take_profit_price": "0.42000"
            }
        ]
        for config in invalid_configs:
            assert take_profit_strategy.validate_config(config) is False

    @pytest.mark.asyncio
    async def test_execute_place_take_profit_order(self, take_profit_strategy, take_profit_db_strategy):
        """Test that strategy places take profit order when no orders exist"""
        mock_service = Mock()
        mock_service.get_current_price = AsyncMock(return_value="0.41000")
        mock_service.order_service.update_order_statuses = AsyncMock()
        mock_service.order_service.place_order = AsyncMock(return_value=create_mock_order_response(
            "test_order",
            status=OrderState.ACCEPTED
        ))
        mock_service.handle_error = AsyncMock()
        
        session = Mock()
        
        with patch('trader.strategies.StrategyService', return_value=mock_service):
            await take_profit_strategy.execute(take_profit_db_strategy, session)
            
            mock_service.order_service.place_order.assert_called_once_with(
                strategy=take_profit_db_strategy,
                amount="10000",
                price="0.42000",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )

    @pytest.mark.asyncio
    async def test_execute_stop_loss_trigger(self, take_profit_strategy, take_profit_db_strategy):
        """Test that strategy executes stop loss when price drops below threshold"""
        # Mock service and client responses
        mock_service = Mock()
        mock_service.get_current_price = AsyncMock(return_value="0.40300")  # Price below stop loss
        mock_service.order_service.update_order_statuses = AsyncMock()
        mock_service.execute_stop_loss = AsyncMock()
        mock_service.handle_error = AsyncMock()
        
        # Create session mock
        session = Mock()
        
        # Patch StrategyService to return our mock
        with patch('trader.strategies.StrategyService', return_value=mock_service):
            await take_profit_strategy.execute(take_profit_db_strategy, session)
            
            # Verify stop loss was executed
            mock_service.execute_stop_loss.assert_called_once_with(
                strategy=take_profit_db_strategy,
                current_price="0.40300",
                stop_price="0.40400",
                amount="10000",
                active_orders=[]
            )

    @pytest.mark.asyncio
    async def test_execute_complete_on_filled(self, take_profit_strategy, take_profit_db_strategy):
        """Test that strategy completes when sell order is filled"""
        # Mock service and client responses
        mock_service = Mock()
        mock_service.get_current_price = AsyncMock(return_value="0.42000")
        mock_service.order_service.update_order_statuses = AsyncMock()
        mock_service.handle_error = AsyncMock()
        
        # Add a filled sell order to the strategy
        order_data = {
            "order_id": "test_order",
            "status": OrderState.FILLED,
            "amount": "10000",
            "price": "0.42000",
            "side": OrderSide.SELL.value,
            "symbol": "dogeusd",
            "order_type": OrderType.LIMIT_SELL,
            "strategy_id": take_profit_db_strategy.id
        }
        filled_order = Order.model_validate(order_data)
        take_profit_db_strategy.orders = [filled_order]
        
        # Create session mock
        session = Mock()
        
        # Patch StrategyService to return our mock
        with patch('trader.strategies.StrategyService', return_value=mock_service):
            await take_profit_strategy.execute(take_profit_db_strategy, session)
            
            # Verify strategy was completed
            mock_service.complete_strategy.assert_called_once_with(take_profit_db_strategy)

    @pytest.mark.asyncio
    async def test_execute_maintain_existing_orders(self, take_profit_strategy, take_profit_db_strategy):
        """Test that strategy maintains existing active orders"""
        # Mock service and client responses
        mock_service = Mock()
        mock_service.get_current_price = AsyncMock(return_value="0.41000")
        mock_service.order_service.update_order_statuses = AsyncMock()
        mock_service.order_service.place_order = AsyncMock()
        mock_service.handle_error = AsyncMock()
        
        # Add an active sell order to the strategy
        active_order = Order(
            order_id="test_order",
            status=OrderState.LIVE,
            amount="10000",
            price="0.42000",
            side=OrderSide.SELL.value,
            symbol="dogeusd",
            order_type=OrderType.LIMIT_SELL,
            strategy_id=take_profit_db_strategy.id
        )
        take_profit_db_strategy.orders = [active_order]
        
        # Create session mock
        session = Mock()
        
        # Patch StrategyService to return our mock
        with patch('trader.strategies.StrategyService', return_value=mock_service):
            await take_profit_strategy.execute(take_profit_db_strategy, session)
            
            # Verify no new orders were placed
            mock_service.order_service.place_order.assert_not_called()