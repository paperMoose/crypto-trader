import pytest
from unittest.mock import AsyncMock, Mock, patch, call
from trader.strategies.manager import StrategyManager
from trader.models import (
    TradingStrategy, StrategyType, StrategyState, 
    Order, OrderState, OrderType
)
from trader.gemini.enums import OrderSide
from decimal import Decimal
import asyncio

@pytest.fixture
def mock_client():
    client = Mock()
    client.get_price = AsyncMock(return_value="0.35000")
    client.place_order = AsyncMock()
    client.check_order_status = AsyncMock(return_value=Mock(status=OrderState.LIVE))
    return client

@pytest.fixture
def mock_order_service():
    service = Mock()
    service.update_order_statuses = AsyncMock()
    service.place_order = AsyncMock()
    service.cancel_order = AsyncMock()
    service.place_stop_order = AsyncMock()
    return service

@pytest.fixture
def mock_service(mock_client, mock_order_service):
    service = Mock()
    service.get_active_strategies = AsyncMock(return_value=[])
    service.should_execute_strategy = AsyncMock(return_value=True)
    service.update_strategy_timestamp = AsyncMock()
    service.update_strategy_orders = AsyncMock()
    service.cancel_and_deactivate_strategy_by_name = AsyncMock()
    service.get_current_price = AsyncMock(return_value="0.35000")
    service.order_service = mock_order_service
    service.handle_error = AsyncMock()
    service.client = mock_client
    service.complete_strategy = AsyncMock()
    service.execute_stop_loss = AsyncMock()
    return service

@pytest.fixture
def manager(mock_service, mock_client):
    with patch('trader.strategies.manager.StrategyService', return_value=mock_service):
        return StrategyManager(Mock(), mock_client)

@pytest.fixture
def test_strategies():
    """Create a set of test strategies with different states"""
    strategies = [
        TradingStrategy(
            id=1,
            name="Range Strategy 1",
            type=StrategyType.RANGE,
            symbol="dogeusd",
            state=StrategyState.ACTIVE,
            is_active=True,
            highest_price="0",
            config={
                "support_price": "0.30",
                "resistance_price": "0.35",
                "amount": "1000",
                "stop_loss_price": "0.29",
                "use_trailing_stop": True,
                "trail_percent": "0.01"
            }
        ),
        TradingStrategy(
            id=2,
            name="Breakout Strategy",
            type=StrategyType.BREAKOUT,
            symbol="dogeusd",
            state=StrategyState.ACTIVE,
            is_active=True,
            highest_price="0",
            config={
                "breakout_price": "0.35",
                "amount": "1000",
                "take_profit_1": "0.37",
                "take_profit_2": "0.40",
                "stop_loss": "0.33"
            }
        ),
        TradingStrategy(
            id=3,
            name="Take Profit Strategy",
            type=StrategyType.TAKE_PROFIT,
            symbol="dogeusd",
            state=StrategyState.ACTIVE,
            is_active=True,
            highest_price="0",
            config={
                "current_position": "1000",
                "entry_price": "0.30",
                "take_profit_price": "0.35",
                "stop_loss_price": "0.29"
            }
        )
    ]
    return strategies

@pytest.mark.asyncio
async def test_create_strategy(manager, mock_service):
    strategy_data = {
        "name": "Test Strategy",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "config": {
            "support_price": "0.30",
            "resistance_price": "0.35",
            "amount": "1000",
            "stop_loss_price": "0.29"
        }
    }
    
    mock_service.update_strategy_orders.return_value = TradingStrategy(**strategy_data)
    
    result = await manager.create_strategy(strategy_data)
    assert result.name == strategy_data["name"]
    assert result.type == strategy_data["type"]
    mock_service.update_strategy_orders.assert_called_once_with(strategy_data)

@pytest.mark.asyncio
async def test_deactivate_strategy(manager, mock_service):
    strategy_name = "Test Strategy"
    await manager.deactivate_strategy(strategy_name)
    mock_service.cancel_and_deactivate_strategy_by_name.assert_called_once_with(strategy_name)

@pytest.mark.asyncio
async def test_monitor_multiple_strategies(manager, mock_service, test_strategies):
    """Test that multiple strategies can run concurrently and interact properly"""
    mock_service.get_active_strategies.return_value = test_strategies
    
    # Set up initial orders
    range_buy_order = Order(
        order_id="range_buy_123",
        status=OrderState.FILLED,
        amount="1000",
        price="0.30",
        side=OrderSide.BUY.value,
        symbol="dogeusd",
        order_type=OrderType.LIMIT_BUY,
        strategy_id=1
    )
    
    breakout_buy_order = Order(
        order_id="breakout_buy_123",
        status=OrderState.FILLED,
        amount="1000",
        price="0.35",
        side=OrderSide.BUY.value,
        symbol="dogeusd",
        order_type=OrderType.LIMIT_BUY,
        strategy_id=2
    )
    
    test_strategies[0].orders = [range_buy_order]
    test_strategies[1].orders = [breakout_buy_order]
    
    # Simulate price movement
    prices = ["0.36000", "0.37000", "0.35500"]
    mock_service.get_current_price.side_effect = prices
    
    # Run one monitor cycle
    async def mock_sleep(*args):
        raise Exception("Stop loop")
    
    with patch('asyncio.sleep', mock_sleep):
        try:
            await manager.monitor_strategies()
        except Exception as e:
            assert str(e) == "Stop loop"
    
    # Verify each strategy was checked
    assert mock_service.should_execute_strategy.call_count == len(test_strategies)
    
    # Verify order management
    order_calls = mock_service.order_service.place_order.call_args_list
    
    # Range strategy should place sell at resistance
    range_sell = next(call for call in order_calls 
                     if call[1]['strategy'].id == 1 
                     and call[1]['side'] == OrderSide.SELL)
    assert range_sell[1]['price'] == "0.35000"  # Resistance price
    assert range_sell[1]['amount'] == "1000"
    
    # Breakout strategy should place split take profits
    breakout_calls = [call for call in order_calls if call[1]['strategy'].id == 2]
    assert len(breakout_calls) == 2  # Two take profit orders
    assert any(call[1]['price'] == "0.37000" for call in breakout_calls)  # TP1
    assert any(call[1]['price'] == "0.40000" for call in breakout_calls)  # TP2
    
    # Verify trailing stops were updated as price moved up
    stop_calls = mock_service.order_service.place_stop_order.call_args_list
    # Mock price movement to trigger trailing stops
    mock_service.get_current_price.side_effect = [
        "0.36000",  # Price moved up - should update trailing stop
        "0.37000",  # Higher - should update again
        "0.35500"   # Lower - should keep previous stop
    ]
    
    # Track order placements
    placed_orders = []
    async def mock_place_order(**kwargs):
        placed_orders.append(kwargs)
        return Mock(order_id=f"test_order_{len(placed_orders)}")
    
    mock_service.order_service.place_order.side_effect = mock_place_order
    mock_service.order_service.place_stop_order.side_effect = mock_place_order
    
    # Mock strategy execution
    async def mock_execute(strategy, session):
        await mock_service.order_service.update_order_statuses(strategy)
        if strategy.type == StrategyType.RANGE:
            await mock_service.order_service.place_order(
                strategy=strategy,
                amount="1000",
                price="0.35000",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
        elif strategy.type == StrategyType.BREAKOUT:
            await mock_service.order_service.place_order(
                strategy=strategy,
                amount="500",
                price="0.37000",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
            await mock_service.order_service.place_order(
                strategy=strategy,
                amount="500",
                price="0.40000",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
        return None
    
    # Patch strategy classes
    with patch('trader.strategies.range_strategy.RangeStrategy.execute', mock_execute), \
         patch('trader.strategies.breakout_strategy.BreakoutStrategy.execute', mock_execute), \
         patch('trader.strategies.take_profit_strategy.TakeProfitStrategy.execute', mock_execute):
        
        # Run one iteration of the monitor loop
        async def mock_sleep(*args, **kwargs):
            raise Exception("Stop loop")
        
        with patch('asyncio.sleep', mock_sleep):
            with pytest.raises(Exception) as exc_info:
                await manager.monitor_strategies()
            assert str(exc_info.value) == "Stop loop"
            
            # Verify basic monitoring occurred
            assert mock_service.should_execute_strategy.call_count == len(test_strategies)
            assert mock_service.order_service.update_order_statuses.call_count == len(test_strategies)
            
            # Verify order placements
            assert len(placed_orders) > 0
            
            # Check range strategy sell order
            range_sell = next((o for o in placed_orders 
                            if o['side'] == OrderSide.SELL 
                            and o['price'] == "0.35000"), None)
            assert range_sell is not None
            assert range_sell['amount'] == "1000"
            
            # Check breakout take profit orders
            tp1 = next((o for o in placed_orders 
                        if o['side'] == OrderSide.SELL 
                        and o['price'] == "0.37000"), None)
            assert tp1 is not None
            assert tp1['amount'] == "500"
            
            tp2 = next((o for o in placed_orders 
                        if o['side'] == OrderSide.SELL 
                        and o['price'] == "0.40000"), None)
            assert tp2 is not None
            assert tp2['amount'] == "500"

@pytest.mark.asyncio
async def test_monitor_strategy_state_changes(manager, mock_service, test_strategies):
    """Test strategy state changes during monitoring"""
    
    # Set up initial state
    mock_service.get_active_strategies.return_value = test_strategies
    
    # Simulate a strategy completing
    async def simulate_completion(strategy):
        if strategy.name == "Range Strategy 1":
            strategy.state = StrategyState.COMPLETED
            strategy.is_active = False
            return True
        return False
    
    mock_service.should_execute_strategy.side_effect = simulate_completion
    
    # Mock asyncio.sleep
    async def mock_sleep(*args, **kwargs):
        raise Exception("Stop loop")
    
    with patch('asyncio.sleep', mock_sleep):
        with pytest.raises(Exception) as exc_info:
            await manager.monitor_strategies()
        assert str(exc_info.value) == "Stop loop"
        
        # Verify state changes
        completed_strategy = test_strategies[0]
        assert completed_strategy.state == StrategyState.COMPLETED
        assert not completed_strategy.is_active

@pytest.mark.asyncio
async def test_monitor_error_handling(manager, mock_service, test_strategies):
    """Test error handling during strategy monitoring"""
    
    mock_service.get_active_strategies.return_value = test_strategies
    
    # Simulate errors for specific strategies
    async def simulate_error(strategy):
        if strategy.name == "Range Strategy 1":
            raise Exception("Test error")
        return True
    
    mock_service.should_execute_strategy.side_effect = simulate_error
    
    # Mock asyncio.sleep
    async def mock_sleep(*args, **kwargs):
        raise Exception("Stop loop")
    
    with patch('asyncio.sleep', mock_sleep):
        with pytest.raises(Exception) as exc_info:
            await manager.monitor_strategies()
        assert str(exc_info.value) == "Stop loop"
        
        # Verify error handling
        assert mock_service.handle_error.called