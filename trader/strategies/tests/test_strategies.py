import logging
import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlmodel import Session
from trader.models import (
    TradingStrategy, Order, OrderState, OrderType, 
    StrategyType, StrategyState
)
from trader.gemini.enums import OrderSide
from trader.strategies import RangeStrategy, BreakoutStrategy, TakeProfitStrategy, BaseStrategy
from trader.services import StrategyService, OrderService

# Configure logging for tests
logging.basicConfig(level=logging.INFO)

# Helper function to create mock orders
def create_mock_order(
    order_id: str,
    side: OrderSide,
    status: OrderState = OrderState.LIVE,
    price: str = "0.35",
    amount: str = "1000"
) -> Order:
    return Order(
        order_id=order_id,
        status=status,
        amount=amount,
        price=price,
        side=side.value,
        symbol="dogeusd",
        order_type=OrderType.LIMIT_BUY if side == OrderSide.BUY else OrderType.LIMIT_SELL,
        strategy_id=1
    )

@pytest.fixture
def mock_order_service():
    service = Mock(spec=OrderService)
    service.update_order_statuses = AsyncMock()
    service.place_order = AsyncMock()
    service.cancel_order = AsyncMock()
    service.place_stop_order = AsyncMock()
    return service

@pytest.fixture
def mock_service(mock_order_service):
    service = Mock(spec=StrategyService)
    service.get_current_price = AsyncMock(return_value="0.35000")
    service.order_service = mock_order_service
    service.handle_error = AsyncMock()
    service.complete_strategy = Mock()
    service.update_strategy_profits = Mock()
    service.execute_stop_loss = AsyncMock()
    return service

@pytest.fixture
def mock_session():
    return Mock(spec=Session)

class TestRangeStrategy:
    @pytest.fixture
    def strategy(self):
        return RangeStrategy(Mock())
    
    @pytest.fixture
    def range_config(self):
        return {
            "support_price": "0.30",
            "resistance_price": "0.35",
            "amount": "1000",
            "stop_loss_price": "0.29",
            "use_trailing_stop": True,
            "trail_percent": "0.01"
        }
    
    @pytest.fixture
    def db_strategy(self, range_config):
        return TradingStrategy(
            id=1,
            name="Test Range Strategy",
            type=StrategyType.RANGE,
            symbol="dogeusd",
            config=range_config,
            state=StrategyState.ACTIVE,
            is_active=True
        )
    
    def test_validate_config(self, strategy, range_config):
        assert strategy.validate_config(range_config) is True
        
        invalid_config = {"support_price": "0.30"}
        assert strategy.validate_config(invalid_config) is False
    
    @pytest.mark.asyncio
    async def test_execute_initial_buy(self, strategy, db_strategy, mock_service, mock_session):
        with patch('trader.strategies.range_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            
            mock_service.order_service.place_order.assert_called_once_with(
                strategy=db_strategy,
                amount="1000",
                price="0.30",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT_BUY
            )
    
    @pytest.mark.asyncio
    async def test_execute_place_sell_after_buy_filled(self, strategy, db_strategy, mock_service, mock_session):
        # Add filled buy order
        buy_order = create_mock_order("buy_123", OrderSide.BUY, OrderState.FILLED, "0.30")
        db_strategy.orders = [buy_order]
        
        with patch('trader.strategies.range_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            
            mock_service.order_service.place_order.assert_called_once_with(
                strategy=db_strategy,
                amount="1000",
                price="0.35",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )

class TestBreakoutStrategy:
    @pytest.fixture
    def strategy(self):
        return BreakoutStrategy(Mock())
    
    @pytest.fixture
    def breakout_config(self):
        return {
            "breakout_price": "0.35",
            "amount": "1000",
            "take_profit_1": "0.37",
            "take_profit_2": "0.40",
            "stop_loss": "0.33",
            "use_trailing_stop": True,
            "trail_percent": "0.01"
        }
    
    @pytest.fixture
    def db_strategy(self, breakout_config):
        return TradingStrategy(
            id=1,
            name="Test Breakout Strategy",
            type=StrategyType.BREAKOUT,
            symbol="dogeusd",
            config=breakout_config,
            state=StrategyState.ACTIVE,
            is_active=True
        )
    
    @pytest.mark.asyncio
    async def test_execute_breakout_buy(self, strategy, db_strategy, mock_service, mock_session):
        # Set price near breakout level
        mock_service.get_current_price.return_value = "0.349"
        
        with patch('trader.strategies.breakout_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            
            mock_service.order_service.place_order.assert_called_once_with(
                strategy=db_strategy,
                amount="1000",
                price="0.35",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT_BUY
            )
    
    @pytest.mark.asyncio
    async def test_execute_take_profits(self, strategy, db_strategy, mock_service, mock_session):
        # Add filled buy order
        buy_order = create_mock_order("buy_123", OrderSide.BUY, OrderState.FILLED, "0.35")
        db_strategy.orders = [buy_order]
        
        with patch('trader.strategies.breakout_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            
            assert mock_service.order_service.place_order.call_count == 2
            calls = mock_service.order_service.place_order.call_args_list
            
            # Verify first take profit order
            assert calls[0][1]["price"] == "0.37"
            assert calls[0][1]["amount"] == "500"
            
            # Verify second take profit order
            assert calls[1][1]["price"] == "0.40"
            assert calls[1][1]["amount"] == "500"

class TestTakeProfitStrategy:
    @pytest.fixture
    def strategy(self):
        return TakeProfitStrategy(Mock())
    
    @pytest.fixture
    def take_profit_config(self):
        return {
            "current_position": "1000",
            "entry_price": "0.30",
            "take_profit_price": "0.35",
            "stop_loss_price": "0.29",
            "use_trailing_stop": True,
            "trail_percent": "0.01"
        }
    
    @pytest.fixture
    def db_strategy(self, take_profit_config):
        return TradingStrategy(
            id=1,
            name="Test Take Profit Strategy",
            type=StrategyType.TAKE_PROFIT,
            symbol="dogeusd",
            config=take_profit_config,
            state=StrategyState.ACTIVE,
            is_active=True
        )
    
    @pytest.mark.asyncio
    async def test_execute_take_profit_order(self, strategy, db_strategy, mock_service, mock_session):
        with patch('trader.strategies.take_profit_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            
            mock_service.order_service.place_order.assert_called_once_with(
                strategy=db_strategy,
                amount="1000",
                price="0.35",
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_SELL
            )
    
    @pytest.mark.asyncio
    async def test_execute_complete_on_filled(self, strategy, db_strategy, mock_service, mock_session):
        # Add filled sell order
        sell_order = create_mock_order("sell_123", OrderSide.SELL, OrderState.FILLED, "0.35")
        db_strategy.orders = [sell_order]
        
        with patch('trader.strategies.take_profit_strategy.StrategyService', return_value=mock_service):
            await strategy.execute(db_strategy, mock_session)
            mock_service.complete_strategy.assert_called_once_with(db_strategy) 

# Base Strategy Tests
def test_base_strategy_abstract():
    """Test that BaseStrategy cannot be instantiated directly"""
    with pytest.raises(TypeError):
        BaseStrategy(Mock()) 