import pytest
from unittest.mock import Mock
from datetime import datetime
from trader.models import TradingStrategy, StrategyType, StrategyState
from trader.strategies import TakeProfitStrategy

@pytest.fixture
def mock_gemini_client():
    client = Mock()
    client.get_price = Mock(return_value="0.35000")
    client.place_order = Mock()
    client.get_orders = Mock(return_value=[])
    client.check_order_status = Mock()
    return client

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