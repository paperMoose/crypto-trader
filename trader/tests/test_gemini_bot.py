import pytest
import os
import json
from trader.gemini.schemas import ActiveOrdersResponse, OrderResponse
from trader.gemini_bot import check_order_status
from trader.gemini.client import GeminiClient
from trader.gemini.enums import OrderSide, OrderType, Symbol
import logging

# Fixture for mock data
@pytest.fixture
def mock_order_data():
    return {
        "123": {
            "status": "open",
            "amount": 100,
            "side": OrderSide.BUY,
            "symbol": Symbol.DOGEUSD,
            "type": OrderType.EXCHANGE_LIMIT
        }
    }

# Fixture for mock client
@pytest.fixture
def mock_client(monkeypatch):
    def mock_check_order_status(*args, **kwargs):
        return {"is_live": True, "order_id": "123"}
    
    monkeypatch.setattr(GeminiClient, "check_order_status", mock_check_order_status)

# Fixture for mocking environment variables
@pytest.fixture(autouse=True)
def mock_env_vars():
    original_api_key = os.getenv("GEMINI_API_KEY")
    original_api_secret = os.getenv("GEMINI_API_SECRET")
    
    os.environ["GEMINI_API_SECRET"] = "dummy_secret"
    os.environ["GEMINI_API_KEY"] = "dummy_key"
    yield
    
    # Restore original values if they existed
    if original_api_key:
        os.environ["GEMINI_API_KEY"] = original_api_key
    if original_api_secret:
        os.environ["GEMINI_API_SECRET"] = original_api_secret

# Test checking order status with mock
def test_check_order_status(mock_client):
    order_id = "123"
    response = check_order_status(order_id)
    assert isinstance(response, dict)
    assert "is_live" in response

# Integration test with real Gemini API
@pytest.mark.integration
def test_gemini_client_integration():
    """
    This test requires valid Gemini API credentials in environment variables.
    Run with: pytest -m integration
    """
    if not (os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_SECRET")):
        pytest.skip("Gemini API credentials not found in environment")
    
    client = GeminiClient()
    
    try:
        response = client.get_active_orders()
        
        assert isinstance(response, ActiveOrdersResponse)
        
        # If there are any orders, verify their structure
        for order in response.orders:
            assert isinstance(order, OrderResponse)
            assert order.order_id is not None
            assert order.symbol is not None
            assert order.executed_amount is not None
            assert order.original_amount is not None
            assert order.price is not None
            assert order.side in [side.value for side in OrderSide]
            
        logging.info(f"Found {len(response.orders)} active orders")
            
    except Exception as e:
        pytest.fail(f"Integration test failed: {str(e)}")
