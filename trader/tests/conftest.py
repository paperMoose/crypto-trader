import pytest
import os
from unittest.mock import AsyncMock
from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine
from trader.gemini.enums import Symbol
from sqlalchemy.pool import StaticPool
from trader.models import StrategyType
from sqlalchemy.engine import create_engine
from sqlalchemy_utils import database_exists, create_database, drop_database
from trader.database import init_db
import trader.config as config

TEST_DATABASE_URL = "postgresql://gemini_bot:gemini_bot_password@localhost:5433/gemini_bot_test"

@pytest.fixture(scope="session", autouse=True)
def override_database_url():
    """Override the database URL for tests"""
    original_url = config.DATABASE_URL
    config.DATABASE_URL = TEST_DATABASE_URL
    yield
    config.DATABASE_URL = original_url

@pytest.fixture(scope="session")
def engine():
    """Create a test database and return the engine"""
    if database_exists(TEST_DATABASE_URL):
        drop_database(TEST_DATABASE_URL)
    
    create_database(TEST_DATABASE_URL)
    
    engine = init_db(TEST_DATABASE_URL)
    
    yield engine
    
    drop_database(TEST_DATABASE_URL)

@pytest.fixture
def session(engine):
    """Create a new database session for a test"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

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