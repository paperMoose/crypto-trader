import pytest
import logging
from trader.gemini.client import GeminiClient
from trader.gemini.enums import Symbol, OrderSide, OrderType
from trader.gemini.schemas import OrderResponse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.fixture
def order_configs():
    return [
        {'amount': '1', 'price': '0.35'},
        {'amount': '1', 'price': '0.30'}
    ]

@pytest.fixture
def stop_limit_configs():
    return {
        'buy': {
            'amount': '1',
            'price': '0.41',    # Limit price to buy at
            'stop_price': '0.40'  # Trigger when price rises above this (breakout)
        },
        'sell': {
            'amount': '1',
            'price': '0.37',    # Minimum price willing to accept
            'stop_price': '0.38'  # Trigger when price falls below this (stop loss)
        }
    }

@pytest.mark.skip(reason="Live test skipped")
@pytest.mark.live
def test_place_buy_orders(order_configs):
    """Test placing multiple buy orders"""
    client = GeminiClient()
    placed_orders = []
    
    # Place each order
    for order in order_configs:
        logger.info(f"Placing buy order: {order['amount']} DOGE at ${order['price']}")
        
        response = client.place_order(
            symbol=Symbol.DOGEUSD,
            amount=order['amount'],
            price=order['price'],
            side=OrderSide.BUY,
            order_type=OrderType.EXCHANGE_LIMIT
        )
        
        assert isinstance(response, OrderResponse)
        assert response.order_id is not None
        placed_orders.append(response.order_id)
        logger.info(f"Order placed successfully. Order ID: {response.order_id}")
    
    # Verify orders were placed
    active_orders = client.get_active_orders()
    placed_order_ids = [order.order_id for order in active_orders.orders]
    
    for order_id in placed_orders:
        assert order_id in placed_order_ids, f"Order {order_id} not found in active orders"
    
    logger.info(f"Successfully placed and verified {len(placed_orders)} orders")

@pytest.mark.skip(reason="Live test skipped")
@pytest.mark.live
def test_place_stop_limit_buy_order(stop_limit_configs):
    """Test placing stop limit buy order"""
    client = GeminiClient()
    
    # Test stop limit buy order
    logger.info(
        f"Placing stop limit buy order: {stop_limit_configs['buy']['amount']} DOGE at "
        f"${stop_limit_configs['buy']['price']} with stop price ${stop_limit_configs['buy']['stop_price']}"
    )
    
    buy_response = client.place_order(
        symbol=Symbol.DOGEUSD,
        amount=stop_limit_configs['buy']['amount'],
        price=stop_limit_configs['buy']['price'],
        stop_price=stop_limit_configs['buy']['stop_price'],
        side=OrderSide.BUY,
        order_type=OrderType.EXCHANGE_STOP_LIMIT
    )
    
    assert isinstance(buy_response, OrderResponse)
    assert buy_response.order_id is not None
    assert buy_response.stop_price == stop_limit_configs['buy']['stop_price']
    logger.info(f"Stop limit buy order placed successfully. Order ID: {buy_response.order_id}")
    
    # Verify order was placed
    active_orders = client.get_active_orders()
    placed_order_ids = [order.order_id for order in active_orders.orders]
    
    assert buy_response.order_id in placed_order_ids, f"Order {buy_response.order_id} not found in active orders"
    order_status = client.check_order_status(buy_response.order_id)
    assert order_status.type == OrderType.EXCHANGE_STOP_LIMIT.value
    
    logger.info(f"Successfully placed and verified stop limit buy order")

@pytest.mark.skip(reason="Live test skipped")
@pytest.mark.live
def test_place_stop_limit_sell_order(stop_limit_configs):
    """Test placing stop limit sell order"""
    client = GeminiClient()
    
    # Test stop limit sell order
    logger.info(
        f"Placing stop limit sell order: {stop_limit_configs['sell']['amount']} DOGE at "
        f"${stop_limit_configs['sell']['price']} with stop price ${stop_limit_configs['sell']['stop_price']}"
    )
    
    sell_response = client.place_order(
        symbol=Symbol.DOGEUSD,
        amount=stop_limit_configs['sell']['amount'],
        price=stop_limit_configs['sell']['price'],
        stop_price=stop_limit_configs['sell']['stop_price'],
        side=OrderSide.SELL,
        order_type=OrderType.EXCHANGE_STOP_LIMIT
    )
    
    assert isinstance(sell_response, OrderResponse)
    assert sell_response.order_id is not None
    assert sell_response.stop_price == stop_limit_configs['sell']['stop_price']
    logger.info(f"Stop limit sell order placed successfully. Order ID: {sell_response.order_id}")
    
    # Verify order was placed
    active_orders = client.get_active_orders()
    placed_order_ids = [order.order_id for order in active_orders.orders]
    
    assert sell_response.order_id in placed_order_ids, f"Order {sell_response.order_id} not found in active orders"
    order_status = client.check_order_status(sell_response.order_id)
    assert order_status.type == "stop-limit" # return type value is not the same as payload
    
    logger.info(f"Successfully placed and verified stop limit sell order")