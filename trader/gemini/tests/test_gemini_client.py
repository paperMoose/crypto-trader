import pytest
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType
from trader.gemini.schemas import ErrorResponse, GeminiAPIError, OrderResponse, OrderStatus, OrderStatusResponse, ActiveOrdersResponse, CancelOrderResponse, OrderHistoryResponse
import logging
import datetime
from datetime import timezone

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
@pytest.mark.skip(reason="relies on funds")
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
        with pytest.raises(GeminiAPIError) as exc_info:
            await client.check_order_status("nonexistent-order-id")
        
        # Verify the error details
        assert "Missing or invalid order_id" in str(exc_info.value)
        assert "MissingOrderField" in str(exc_info.value)

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

@pytest.mark.asyncio
async def test_get_order_history():
    """Test getting order history"""
    async with GeminiClient() as client:
        response = await client.get_order_history()
        
        assert isinstance(response, OrderHistoryResponse)
        assert hasattr(response, 'orders')
        assert isinstance(response.orders, list)
        
        # Verify we can get up to 50 orders
        assert len(response.orders) <= 50
        
        # If there are orders, verify their structure
        for order in response.orders:
            assert isinstance(order, OrderResponse)
            assert order.order_id is not None
            assert order.symbol is not None
            assert order.price is not None
            assert order.side is not None
            assert order.type is not None
            assert order.timestamp is not None
            assert order.executed_amount is not None
            assert order.original_amount is not None
            # remaining_amount is calculated in OrderResponse.model_post_init
            assert order.remaining_amount is not None

@pytest.mark.asyncio
async def test_order_status_mapping():
    """Test that order status is correctly mapped based on order state"""
    # Test filled order
    filled_order = OrderResponse(
        order_id='73771231901973185',
        id='73771231901973185',
        symbol='dogeusd',
        exchange='gemini',
        avg_execution_price='0.396',
        side='buy',
        type='stop-limit',
        timestamp=datetime.datetime(2024, 11, 19, 13, 8, 15, tzinfo=timezone.utc),
        timestampms=1732021695557,
        is_live=False,
        is_cancelled=False,
        is_hidden=False,
        was_forced=False,
        executed_amount='2500',
        original_amount='2500',
        price='0.40',
        stop_price='0.396',
        options=[]
    )
    assert filled_order.status == OrderStatus.FILLED

    # Test cancelled order
    cancelled_order = OrderResponse(
        order_id='73771231901973186',
        id='73771231901973186',
        symbol='dogeusd',
        exchange='gemini',
        avg_execution_price='0',
        side='buy',
        type='exchange limit',
        timestamp=datetime.datetime(2024, 11, 19, 13, 8, 15, tzinfo=timezone.utc),
        timestampms=1732021695557,
        is_live=False,
        is_cancelled=True,
        is_hidden=False,
        was_forced=False,
        executed_amount='0',
        original_amount='2500',
        price='0.40',
        options=[]
    )
    assert cancelled_order.status == OrderStatus.CANCELLED

    # Test live order
    live_order = OrderResponse(
        order_id='73771231901973187',
        id='73771231901973187',
        symbol='dogeusd',
        exchange='gemini',
        avg_execution_price='0',
        side='buy',
        type='exchange limit',
        timestamp=datetime.datetime(2024, 11, 19, 13, 8, 15, tzinfo=timezone.utc),
        timestampms=1732021695557,
        is_live=True,
        is_cancelled=False,
        is_hidden=False,
        was_forced=False,
        executed_amount='0',
        original_amount='2500',
        price='0.40',
        options=[]
    )
    assert live_order.status == OrderStatus.LIVE

    # Test partially filled order
    partially_filled_order = OrderResponse(
        order_id='73771231901973188',
        id='73771231901973188',
        symbol='dogeusd',
        exchange='gemini',
        avg_execution_price='0.396',
        side='buy',
        type='exchange limit',
        timestamp=datetime.datetime(2024, 11, 19, 13, 8, 15, tzinfo=timezone.utc),
        timestampms=1732021695557,
        is_live=True,
        is_cancelled=False,
        is_hidden=False,
        was_forced=False,
        executed_amount='1000',
        original_amount='2500',
        price='0.40',
        options=[]
    )
    assert partially_filled_order.status == OrderStatus.PARTIAL_FILL

    # Test accepted but not yet live order
    accepted_order = OrderResponse(
        order_id='73771231901973189',
        id='73771231901973189',
        symbol='dogeusd',
        exchange='gemini',
        avg_execution_price='0',
        side='buy',
        type='exchange limit',
        timestamp=datetime.datetime(2024, 11, 19, 13, 8, 15, tzinfo=timezone.utc),
        timestampms=1732021695557,
        is_live=False,
        is_cancelled=False,
        is_hidden=False,
        was_forced=False,
        executed_amount='0',
        original_amount='2500',
        price='0.40',
        options=[]
    )
    assert accepted_order.status == OrderStatus.ACCEPTED