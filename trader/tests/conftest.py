import pytest
import os
from unittest.mock import AsyncMock
from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine
from trader.gemini.enums import Symbol
from sqlalchemy.pool import StaticPool
from trader.models import StrategyType


@pytest.fixture(autouse=True)
def check_credentials():
    """Skip live tests if credentials are not available"""
    load_dotenv()
    if not (os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_SECRET")):
        pytest.skip("Gemini API credentials not found in environment") 

@pytest.fixture
def engine():
    """Create a new in-memory database for each test"""
    from trader.models import SQLModel, Order, TradingStrategy
    
    engine = create_engine(
        "sqlite://",  # In-memory database
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine

@pytest.fixture
def session(engine):
    """Create a new database session for each test"""
    with Session(engine) as session:
        yield session
        session.rollback() 

@pytest.fixture(scope="function")
def mock_gemini_client():
    """Create a mock Gemini client with async methods"""
    client = AsyncMock()
    client.place_order = AsyncMock()
    client.check_order_status = AsyncMock()
    return client

@pytest.fixture
def range_strategy_data():
    """Sample range strategy configuration"""
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
def breakout_strategy_data():
    """Sample breakout strategy configuration"""
    return {
        "name": "Test Breakout Strategy",
        "type": StrategyType.BREAKOUT,
        "symbol": Symbol.DOGEUSD.value,
        "config": {
            "breakout_price": "0.35",
            "amount": "1000",
            "take_profit_1": "0.37",
            "take_profit_2": "0.40",
            "stop_loss": "0.33"
        },
        "check_interval": 60
    } 