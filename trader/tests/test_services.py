import pytest
from unittest.mock import Mock, AsyncMock
from trader.services import OrderService, StrategyService
from trader.models import Order, OrderState, OrderType, StrategyType, StrategyState, TradingStrategy
from trader.gemini.enums import OrderSide, Symbol
from trader.gemini.schemas import GeminiAPIError
from datetime import datetime, timedelta

# Test Data Fixtures
@pytest.fixture
def mock_strategy(session):
    """Create a mock strategy for testing"""
    strategy_data = {
        "id": 1,
        "name": "Test Strategy",
        "type": StrategyType.RANGE,
        "symbol": "dogeusd",
        "state": StrategyState.ACTIVE,
        "check_interval": 60,
        "config": {
            "support_price": "0.30",
            "resistance_price": "0.35",
            "stop_loss_price": "0.29",
            "amount": "1000"
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_checked_at": datetime.utcnow(),
        "is_active": True,
        "total_profit": "0",
        "realized_profit": "0",
        "tax_reserve": "0",
        "available_profit": "0"
    }
    
    strategy = TradingStrategy.model_validate(strategy_data)
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return strategy

@pytest.fixture
def mock_order(mock_strategy):
    """Create a mock order for testing"""
    order_data = {
        "id": 1,
        "order_id": "test_123",
        "status": OrderState.ACCEPTED,
        "amount": "1000",
        "price": "0.35",
        "side": OrderSide.BUY.value,
        "symbol": "dogeusd",
        "order_type": OrderType.LIMIT_BUY,
        "strategy_id": mock_strategy.id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    return Order.model_validate(order_data)

# OrderService Tests
class TestOrderService:
    @pytest.mark.asyncio
    async def test_place_order_success(self, session, mock_gemini_client, mock_strategy):
        """Test successful order placement"""
        service = OrderService(mock_gemini_client, session)
        
        mock_gemini_client.place_order.return_value = Mock(order_id="test_123")
        
        order = await service.place_order(
            strategy=mock_strategy,
            amount="1000",
            price="0.35",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT_BUY
        )
        
        assert order.order_id == "test_123"
        assert order.status == OrderState.ACCEPTED
        assert order.strategy_id == mock_strategy.id

    @pytest.mark.asyncio
    async def test_place_order_api_error(self, session, mock_gemini_client, mock_strategy):
        """Test order placement with API error"""
        service = OrderService(mock_gemini_client, session)
        
        mock_gemini_client.place_order.side_effect = GeminiAPIError(Mock(reason="InsufficientFunds"))
        
        with pytest.raises(GeminiAPIError):
            await service.place_order(
                strategy=mock_strategy,
                amount="1000",
                price="0.35",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT_BUY
            )

    @pytest.mark.asyncio
    async def test_cancel_orders(self, session, mock_gemini_client, mock_order):
        """Test order cancellation"""
        service = OrderService(mock_gemini_client, session)
        
        await service.cancel_orders([mock_order])
        
        mock_gemini_client.cancel_order.assert_called_once_with(mock_order.order_id)

    @pytest.mark.asyncio
    async def test_update_order_statuses(self, session, mock_gemini_client, mock_strategy, mock_order):
        """Test order status updates"""
        service = OrderService(mock_gemini_client, session)
        
        # Add order to session and commit
        session.add(mock_order)
        session.commit()
        
        # Add order to strategy's orders
        mock_strategy.orders = [mock_order]
        
        mock_gemini_client.check_order_status.return_value = Mock(
            status=OrderState.FILLED,
            order_id=mock_order.order_id
        )
        
        await service.update_order_statuses(mock_strategy)
        session.refresh(mock_order)
        
        assert mock_order.status == OrderState.FILLED

# StrategyService Tests
class TestStrategyService:
    @pytest.mark.asyncio
    async def test_get_current_price(self, session, mock_gemini_client):
        """Test getting current price"""
        service = StrategyService(mock_gemini_client, session)
        mock_gemini_client.get_price.return_value = "0.35"
        
        price = await service.get_current_price("dogeusd")
        assert price == "0.35"

    def test_strategy_state_transitions(self, session, mock_gemini_client, mock_strategy):
        """Test strategy state transitions"""
        service = StrategyService(mock_gemini_client, session)
        
        # Test activation
        service.activate_strategy(mock_strategy)
        assert mock_strategy.state == StrategyState.ACTIVE
        assert mock_strategy.is_active is True
        
        # Test pause
        service.pause_strategy(mock_strategy)
        assert mock_strategy.state == StrategyState.PAUSED
        assert mock_strategy.is_active is False
        
        # Test completion
        service.complete_strategy(mock_strategy)
        assert mock_strategy.state == StrategyState.COMPLETED
        assert mock_strategy.is_active is False

    @pytest.mark.asyncio
    async def test_execute_stop_loss(self, session, mock_gemini_client, mock_strategy):
        """Test stop loss execution"""
        service = StrategyService(mock_gemini_client, session)
        
        mock_gemini_client.place_order.return_value = Mock(order_id="stop_loss_123")
        
        active_orders = [Mock(order_id="existing_123")]
        
        order = await service.execute_stop_loss(
            strategy=mock_strategy,
            current_price="0.28",
            stop_price="0.29",
            amount="1000",
            active_orders=active_orders
        )
        
        assert order.order_id == "stop_loss_123"
        assert mock_strategy.state == StrategyState.COMPLETED
        mock_gemini_client.cancel_order.assert_called_once_with("existing_123")

    @pytest.mark.asyncio
    async def test_place_take_profit_orders(self, session, mock_gemini_client, mock_strategy):
        """Test placing take profit orders"""
        service = StrategyService(mock_gemini_client, session)
        
        mock_gemini_client.place_order.side_effect = [
            Mock(order_id=f"tp_{i}") for i in range(2)
        ]
        
        orders = await service.place_take_profit_orders(
            strategy=mock_strategy,
            prices=["0.37", "0.40"],
            amount="1000"
        )
        
        assert len(orders) == 2
        assert all(o.side == OrderSide.SELL.value for o in orders)
        assert mock_gemini_client.place_order.call_count == 2

    @pytest.mark.asyncio
    async def test_should_execute_strategy(self, session, mock_gemini_client, mock_strategy):
        """Test strategy execution interval check"""
        service = StrategyService(mock_gemini_client, session)
        
        # Test when interval has not elapsed
        mock_strategy.last_checked_at = datetime.utcnow()
        assert await service.should_execute_strategy(mock_strategy) is False
        
        # Test when interval has elapsed
        mock_strategy.last_checked_at = datetime.utcnow() - timedelta(seconds=61)
        assert await service.should_execute_strategy(mock_strategy) is True

    @pytest.mark.asyncio
    async def test_update_strategy_orders(self, session, mock_gemini_client, mock_strategy):
        """Test strategy order updates"""
        strategies = {StrategyType.RANGE: Mock()}
        service = StrategyService(mock_gemini_client, session, strategies)
        
        strategy_data = {
            "name": mock_strategy.name,
            "type": StrategyType.RANGE,
            "symbol": "dogeusd",
            "state": StrategyState.ACTIVE,
            "config": {"new": "config"}
        }
        
        # Mock strategy validation
        strategies[StrategyType.RANGE].validate_config.return_value = True
        
        updated = await service.update_strategy_orders(strategy_data)
        assert updated.config == {"new": "config"}

    @pytest.mark.asyncio
    async def test_error_handling(self, session, mock_gemini_client, mock_strategy):
        """Test error handling in service"""
        service = StrategyService(mock_gemini_client, session)
        
        error = Exception("Test error")
        await service.handle_error(mock_strategy, error)
        
        assert mock_strategy.state == StrategyState.FAILED
        assert mock_strategy.is_active is False

    @pytest.mark.asyncio
    async def test_get_total_profits_summary(self, session, mock_gemini_client):
        """Test getting total profits summary across strategies"""
        service = StrategyService(mock_gemini_client, session)
        
        # Create test strategies with known profits
        strategies = []
        for i in range(1, 4):  # Create 3 strategies
            strategy = TradingStrategy(
                name=f"Test Strategy {i}",
                type=StrategyType.RANGE,
                symbol="btcusd",
                total_profit=str(100.0 * i),
                realized_profit=str(90.0 * i),
                tax_reserve=str(50.0 * i),
                available_profit=str(50.0 * i),
                state=StrategyState.ACTIVE,
                is_active=True,
                check_interval=60,
                config={},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_checked_at=datetime.utcnow()
            )
            strategies.append(strategy)
            session.add(strategy)
        session.commit()
        
        # Get profits summary
        summary = service.get_total_profits_summary()
        
        # Verify totals
        assert float(summary['total_profit']) == 600.0  # 100 + 200 + 300
        assert float(summary['total_realized']) == 540.0  # 90 + 180 + 270
        assert float(summary['tax_reserve']) == 300.0  # 50 + 100 + 150
        assert float(summary['available_profit']) == 300.0  # 50 + 100 + 150

    @pytest.mark.asyncio
    async def test_get_profits_by_strategy(self, session, mock_gemini_client):
        """Test getting detailed profit breakdown by strategy"""
        service = StrategyService(mock_gemini_client, session)
        
        # Create test strategy with known profits
        strategy_data = {
            "name": "Test Strategy",
            "type": StrategyType.RANGE,
            "symbol": "btcusd",
            "total_profit": "100.0",
            "realized_profit": "90.0",
            "tax_reserve": "50.0",
            "available_profit": "50.0",
            "state": StrategyState.ACTIVE,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_checked_at": datetime.utcnow(),
            "config": {}
        }
        strategy = TradingStrategy.model_validate(strategy_data)
        session.add(strategy)
        session.commit()
        
        # Get strategy profits
        results = service.get_profits_by_strategy()
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result['strategy_id'] == strategy.id
        assert result['strategy_name'] == strategy.name
        assert float(result['total_profit']) == 100.0
        assert float(result['realized_profit']) == 90.0
        assert float(result['tax_reserve']) == 50.0
        assert float(result['available_profit']) == 50.0
        assert result['symbol'] == 'btcusd'
        assert result['type'] == StrategyType.RANGE 