import pytest
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType
from trader.gemini.schemas import ErrorResponse, OrderResponse, OrderStatusResponse, ActiveOrdersResponse, CancelOrderResponse
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.fixture
def order_config():
    return {
        'symbol': Symbol.DOGEUSD,
        'amount': '2',
        'price': '0.10',
        'side': OrderSide.BUY,
        'order_type': OrderType.EXCHANGE_LIMIT
    }

@pytest.fixture
def stop_limit_config():
    return {
        'symbol': Symbol.DOGEUSD,
        'amount': '2',
        'price': '0.28',
        'stop_price': '0.30',
        'side': OrderSide.SELL,
        'order_type': OrderType.EXCHANGE_STOP_LIMIT
    }

@pytest.mark.asyncio
async def test_place_order(order_config):
    """Test placing a limit order"""
    async with GeminiClient() as client:
        response = await client.place_order(
            symbol=order_config['symbol'],
            amount=order_config['amount'],
            price=order_config['price'],
            side=order_config['side'],
            order_type=order_config['order_type']
        )
        
        assert isinstance(response, OrderResponse)
        assert response.order_id is not None
        assert response.symbol == order_config['symbol']
        assert response.original_amount == order_config['amount']
        assert response.price == order_config['price']
        assert response.side == order_config['side'].value
        
        return response.order_id  # For use in other tests

@pytest.mark.asyncio
async def test_place_stop_limit_order(stop_limit_config):
    """Test placing a stop limit order"""
    async with GeminiClient() as client:
        response = await client.place_order(
            symbol=stop_limit_config['symbol'],
            amount=stop_limit_config['amount'],
            price=stop_limit_config['price'],
            stop_price=stop_limit_config['stop_price'],
            side=stop_limit_config['side'],
            order_type=stop_limit_config['order_type']
        )
        
        assert isinstance(response, OrderResponse)
        assert response.order_id is not None
        assert response.symbol == stop_limit_config['symbol']
        assert response.original_amount == stop_limit_config['amount']
        assert response.price == stop_limit_config['price']
        assert response.stop_price == stop_limit_config['stop_price']
        assert response.side == stop_limit_config['side'].value
        
        return response.order_id

@pytest.mark.asyncio
async def test_check_order_status(order_config):
    """Test checking order status"""
    async with GeminiClient() as client:
        # Place an order first to get a valid order_id
        order = await client.place_order(
            symbol=order_config['symbol'],
            amount=order_config['amount'],
            price=order_config['price'],
            side=order_config['side'],
            order_type=order_config['order_type']
        )
        status = await client.check_order_status(order.order_id)
        assert isinstance(status, OrderStatusResponse)

@pytest.mark.asyncio
async def test_get_active_orders():
    """Test getting all active orders"""
    async with GeminiClient() as client:
        response = await client.get_active_orders()
        
        assert isinstance(response, ActiveOrdersResponse)
        assert hasattr(response, 'orders')
        assert isinstance(response.orders, list)
        
        # If there are orders, verify their structure
        for order in response.orders:
            assert isinstance(order, OrderResponse)
            assert order.order_id is not None
            assert order.symbol is not None
            assert order.price is not None
            assert order.side in [side.value for side in OrderSide]

@pytest.mark.asyncio
async def test_cancel_order(order_config):
    """Test canceling an order"""
    async with GeminiClient() as client:
        # Place an order first
        order = await client.place_order(
            symbol=order_config['symbol'],
            amount=order_config['amount'],
            price=order_config['price'],
            side=order_config['side'],
            order_type=order_config['order_type']
        )
        response = await client.cancel_order(order.order_id)
        assert isinstance(response, CancelOrderResponse)

@pytest.mark.asyncio
async def test_full_order_lifecycle():
    """Test complete order lifecycle: place, check, cancel"""
    async with GeminiClient() as client:
        # Place order
        place_response = await client.place_order(
            symbol=Symbol.DOGEUSD,
            amount='100',
            price='0.10',
            side=OrderSide.BUY,
            order_type=OrderType.EXCHANGE_LIMIT
        )
        
        assert isinstance(place_response, OrderResponse)
        order_id = place_response.order_id
        
        # Check status
        status_response = await client.check_order_status(order_id)
        assert isinstance(status_response, OrderStatusResponse)
        assert status_response.is_live is True
        
        # Cancel order
        cancel_response = await client.cancel_order(order_id)
        assert isinstance(cancel_response, CancelOrderResponse)
        assert cancel_response.is_cancelled is True
        
        # Verify cancellation
        final_status = await client.check_order_status(order_id)
        assert final_status.is_live is False
        assert final_status.is_cancelled is True

@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for invalid requests"""
    async with GeminiClient() as client:
        # Check non-existent order
        response = await client.check_order_status("nonexistent-order-id")
        assert isinstance(response, ErrorResponse)
        assert "missing or invalid order_id" in response.message.lower()

        # Test invalid order parameters
        response = await client.place_order(
            symbol=Symbol.DOGEUSD,
            amount='-1',  # Invalid amount
            price='0.10',
            side=OrderSide.BUY,
            order_type=OrderType.EXCHANGE_LIMIT
        )
        assert isinstance(response, ErrorResponse)
        assert "invalid" in response.message.lower()  # More generic error check

@pytest.mark.asyncio
async def test_cancel_orders_by_amount():
    """Test canceling all existing orders with amounts of 2 or 100"""
    async with GeminiClient() as client:
        # Get all active orders
        active_orders = await client.get_active_orders()
        
        # Cancel orders with amount 100 or 2
        target_amounts = {'100', '2'}
        cancelled_orders = []
        
        for order in active_orders.orders:
            if order.original_amount in target_amounts:
                response = await client.cancel_order(order.order_id)
                if isinstance(response, CancelOrderResponse):
                    cancelled_orders.append(response)
                    print(f"Cancelled order {order.order_id} with amount {order.original_amount}")

        # Verify remaining orders don't have target amounts
        remaining_orders = await client.get_active_orders()
        for order in remaining_orders.orders:
            assert order.original_amount not in target_amounts, \
                f"Order with amount {order.original_amount} should have been cancelled"