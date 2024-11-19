import pytest
import logging
from trader.gemini.client import GeminiClient, OrderSide

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.mark.skip(reason="Live test skipped")
@pytest.mark.live
def test_cancel_all_buy_orders():
    """Test canceling all open buy orders"""
    client = GeminiClient()
    
    # Get all active orders
    active_orders = client.get_active_orders()
    logger.info(f"Found {len(active_orders)} active orders")
    
    # Filter for buy orders
    buy_orders = [order for order in active_orders if order['side'] == OrderSide.BUY]
    logger.info(f"Found {len(buy_orders)} buy orders to cancel")
    
    # Cancel each buy order and verify
    for order in buy_orders:
        order_id = order['order_id']
        symbol = order['symbol']
        price = order['price']
        
        logger.info(f"Canceling buy order {order_id} for {symbol} at {price}")
        response = client.cancel_order(order_id)
        
        assert response.get('is_cancelled', False), f"Failed to cancel order {order_id}: {response}"
        logger.info(f"Successfully cancelled order {order_id}")
    
    # Verify all buy orders are cancelled
    remaining_orders = client.get_active_orders()
    remaining_buy_orders = [order for order in remaining_orders if order['side'] == OrderSide.BUY]
    assert len(remaining_buy_orders) == 0, "Some buy orders remain uncancelled"
    
    logger.info("Successfully cancelled all buy orders") 