import pytest
import os
import json
from gemini_bot import load_orders, save_orders, check_order_status, ORDER_FILE
from client import GeminiClient
import logging

# Fixture for mock data
@pytest.fixture
def mock_order_data():
    return {"123": {"status": "open", "amount": 100}}

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

# Fixture to handle temporary order file
@pytest.fixture
def temp_order_file(monkeypatch, tmp_path):
    test_order_file = tmp_path / "orders.json"
    monkeypatch.setattr('gemini_bot.ORDER_FILE', str(test_order_file))
    return test_order_file

# Test loading orders from JSON file
def test_load_orders(temp_order_file):
    # Create a temporary orders.json file with empty dict
    temp_order_file.write_text("{}")
    
    orders = load_orders()
    assert isinstance(orders, dict)
    assert orders == {}

# Test saving orders to JSON file
def test_save_orders(mock_order_data, temp_order_file):
    save_orders(mock_order_data)
    loaded_data = load_orders()
    assert loaded_data == mock_order_data

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
        
        assert isinstance(response, list), "Response should be a list of orders"
        
        # If there are any orders, verify their structure
        for order in response:
            assert "order_id" in order
            assert "symbol" in order
            assert "executed_amount" in order
            assert "original_amount" in order
            assert "price" in order
            assert "side" in order
            
        logging.info(f"Found {len(response)} active orders")
            
    except Exception as e:
        pytest.fail(f"Integration test failed: {str(e)}")
