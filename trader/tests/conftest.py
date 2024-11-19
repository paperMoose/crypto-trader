import pytest
import os
from unittest.mock import Mock, AsyncMock
from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine
from trader.gemini.client import GeminiClient
from trader.models import OrderState
from trader.gemini.enums import Symbol
from trader.models import StrategyType
from sqlalchemy.pool import StaticPool
from sqlalchemy import event

TEST_DB = "test.db"

def remove_test_db():
    """Remove the test database file if it exists"""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Setup test database before any tests run and cleanup after"""
    remove_test_db()
    yield
    remove_test_db()

@pytest.fixture(scope="session")
def engine():
    """Create a test database engine that persists across all tests"""
    # Use file-based SQLite for better debugging
    engine = create_engine(
        f"sqlite:///{TEST_DB}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine

@pytest.fixture(scope="function")
def connection(engine):
    """Create a test connection with transaction rollback"""
    connection = engine.connect()
    # Begin a non-ORM transaction
    trans = connection.begin()
    
    yield connection
    
    # Rollback the transaction after the test
    trans.rollback()
    connection.close()

@pytest.fixture(scope="function")
def session(connection):
    """Create a new session for a test with automatic rollback"""
    # Begin a nested transaction
    transaction = connection.begin_nested()
    
    # Create session bound to the connection
    session = Session(bind=connection)
    
    yield session
    
    # Close and rollback the session after the test
    session.close()
    transaction.rollback()

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