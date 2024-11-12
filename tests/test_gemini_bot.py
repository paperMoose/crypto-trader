import pytest
import os
from gemini_bot import load_orders, save_orders, place_order, check_order_status

# Fixture for mock data
@pytest.fixture
def mock_order_data():
    return {"123": {"status": "open", "amount": 100}}

# Fixture for mocking environment variables
@pytest.fixture(autouse=True)
def mock_env_vars():
    os.environ["GEMINI_API_SECRET"] = "dummy_secret"
    os.environ["GEMINI_API_KEY"] = "dummy_key"
    yield
    del os.environ["GEMINI_API_SECRET"]
    del os.environ["GEMINI_API_KEY"]

# Test loading orders from JSON file
def test_load_orders(mock_order_data, tmp_path):
    # Create a temporary orders.json file
    orders_file = tmp_path / "orders.json"
    orders_file.write_text("{}")

    # Load orders and check the type
    orders = load_orders()
    assert isinstance(orders, dict)
    assert orders == {}

# Test saving orders to JSON file
def test_save_orders(mock_order_data, tmp_path):
    # Save mock data to the temporary orders.json file
    save_orders(mock_order_data)
    loaded_data = load_orders()

    # Assert that the loaded data matches the mock data
    assert loaded_data == mock_order_data

# Parameterized test for placing an order
@pytest.mark.parametrize("symbol, amount, price, side, order_type", [
    ("dogeusd", 100, 0.35, "buy", "exchange limit")
])
def test_place_order(symbol, amount, price, side, order_type):
    # Mock response for order placement
    response = place_order(symbol, amount, price, side, order_type)

    # Assert that the response contains an order_id
    assert "order_id" in response
    assert isinstance(response, dict)

# Test checking order status
def test_check_order_status():
    # Mock order_id for testing
    order_id = "123"
    response = check_order_status(order_id)

    # Assert that the response contains the expected keys
    assert isinstance(response, dict)
    assert "is_live" in response
