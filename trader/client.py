import requests
import json
import hmac
import hashlib
import base64
from trader.config import API_KEY, API_SECRET, BASE_URL, get_nonce
from enum import Enum, auto

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    EXCHANGE_LIMIT = "exchange limit"
    EXCHANGE_STOP_LIMIT = "exchange stop limit"

class Symbol(str, Enum):
    DOGEUSD = "dogeusd"
    BTCUSD = "btcusd"
    # Add other symbols as needed

class OrderOption(str, Enum):
    MAKER_OR_CANCEL = "maker-or-cancel"
    IMMEDIATE_OR_CANCEL = "immediate-or-cancel"
    FILL_OR_KILL = "fill-or-kill"
    AUCTION_ONLY = "auction-only"
    INDICATION_OF_INTEREST = "indication-of-interest"

class GeminiClient:
    def __init__(self):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.base_url = BASE_URL

    def _generate_signature(self, payload):
        b64 = base64.b64encode(json.dumps(payload).encode())
        signature = hmac.new(self.api_secret, b64, hashlib.sha384).hexdigest()
        return b64, signature

    def _make_request(self, endpoint, payload):
        b64_payload, signature = self._generate_signature(payload)
        headers = {
            "Content-Type": "text/plain",
            "X-GEMINI-APIKEY": self.api_key,
            "X-GEMINI-PAYLOAD": b64_payload,
            "X-GEMINI-SIGNATURE": signature
        }
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, headers=headers)
        return response.json()

    def place_order(
        self,
        symbol: Symbol,
        amount: str,
        price: str,
        side: OrderSide,
        order_type: OrderType,
        stop_price: str = None,
        client_order_id: str = None,
        options: list[OrderOption] = None,
        account: str = None
    ):
        """
        Place an order on Gemini exchange.
        
        Args:
            symbol: Trading pair symbol
            amount: Quantity to trade
            price: Price per unit
            side: Buy or sell
            order_type: Type of order (limit or stop-limit)
            stop_price: Optional trigger price for stop-limit orders
            client_order_id: Optional client-specified order ID
            options: Optional list of order execution options
            account: Optional account name for master API keys
        """
        endpoint = "/v1/order/new"
        payload = {
            "request": endpoint,
            "nonce": get_nonce(),
            "symbol": symbol,
            "amount": str(amount),
            "price": str(price),
            "side": side,
            "type": order_type
        }
        return self._make_request(endpoint, payload)

    def check_order_status(self, order_id):
        endpoint = "/v1/order/status"
        payload = {
            "request": endpoint,
            "nonce": get_nonce(),
            "order_id": order_id
        }
        return self._make_request(endpoint, payload)

    def get_active_orders(self):
        endpoint = "/v1/orders"
        payload = {
            "request": endpoint,
            "nonce": get_nonce()
        }
        return self._make_request(endpoint, payload)

    def cancel_order(self, order_id):
        endpoint = "/v1/order/cancel"
        payload = {
            "request": endpoint,
            "nonce": get_nonce(),
            "order_id": order_id
        }
        return self._make_request(endpoint, payload) 