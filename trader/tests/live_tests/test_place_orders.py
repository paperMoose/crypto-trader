import pytest
import logging
from trader.client import GeminiClient, Symbol, OrderSide, OrderType

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.fixture
def order_configs():
    return [
        {'amount': '1', 'price': '0.35'},
        {'amount': '1', 'price': '0.30'}
    ]

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
        
        assert 'order_id' in response, f"Failed to place order: {response}"
        placed_orders.append(response['order_id'])
        logger.info(f"Order placed successfully. Order ID: {response['order_id']}")
    
    # Verify orders were placed
    active_orders = client.get_active_orders()
    placed_order_ids = [order['order_id'] for order in active_orders]
    
    for order_id in placed_orders:
        assert order_id in placed_order_ids, f"Order {order_id} not found in active orders"
    
    logger.info(f"Successfully placed and verified {len(placed_orders)} orders") 