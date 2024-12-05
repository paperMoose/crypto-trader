from datetime import datetime
from trader.models import OrderState
from trader.gemini.enums import OrderSide

def create_mock_order_response(order_id, status="accepted", **kwargs):
    """Create a mock order response with all required fields"""
    # Convert status string to OrderState if it isn't already
    if isinstance(status, str):
        status = OrderState(status)
    
    return type('Response', (), {
        'order_id': order_id,
        'status': status,
        'original_amount': kwargs.get('amount', '1000'),
        'price': kwargs.get('price', '0.35'),
        'side': kwargs.get('side', OrderSide.BUY.value),
        'symbol': kwargs.get('symbol', 'dogeusd'),
        'stop_price': kwargs.get('stop_price', None),
        'get_total_fees': lambda: kwargs.get('fees', '0.00'),
        'is_live': kwargs.get('is_live', True),
        'is_cancelled': kwargs.get('is_cancelled', False)
    }) 