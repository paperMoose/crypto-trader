import aiohttp
import json
import hmac
import hashlib
import base64
from trader.config import API_KEY, API_SECRET, BASE_URL, get_nonce
from .schemas import (
    OrderResponse,
    OrderStatusResponse,
    ActiveOrdersResponse,
    CancelOrderResponse,
    OrderHistoryResponse,
    parse_response
)
from .enums import OrderSide, OrderType, Symbol, OrderOption
from .decorators import with_retry
from typing import Optional, List

class GeminiClient:
    def __init__(self):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.base_url = BASE_URL
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_signature(self, payload):
        b64 = base64.b64encode(json.dumps(payload).encode())
        signature = hmac.new(self.api_secret, b64, hashlib.sha384).hexdigest()
        return b64, signature

    @with_retry(max_retries=3, base_delay=1.0)
    async def _make_request(self, endpoint, payload):
        if not self.session:
            self.session = aiohttp.ClientSession()

        b64_payload, signature = self._generate_signature(payload)
        
        headers = {
            "Content-Type": "text/plain",
            "X-GEMINI-APIKEY": self.api_key,
            "X-GEMINI-PAYLOAD": b64_payload.decode('utf-8'),
            "X-GEMINI-SIGNATURE": signature
        }
        url = f"{self.base_url}{endpoint}"
        
        async with self.session.post(url, headers=headers) as response:
            return await response.json()

    @with_retry(max_retries=3, base_delay=1.0)
    async def place_order(
        self,
        symbol: Symbol,
        amount: str,
        price: str,
        side: OrderSide,
        order_type: OrderType,
        stop_price: Optional[str] = None,
        client_order_id: str = None,
        options: list[OrderOption] = None,
        account: str = None
    ) -> OrderStatusResponse:
        """Place an order and return response with trade info"""
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
        
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        if client_order_id is not None:
            payload["client_order_id"] = client_order_id
        if options is not None:
            payload["options"] = options
        if account is not None:
            payload["account"] = account

        response = await self._make_request(endpoint, payload)
        return parse_response(response, OrderStatusResponse)

    @with_retry(max_retries=3, base_delay=1.0)
    async def check_order_status(self, order_id: str) -> OrderStatusResponse:
        """Get status of an order including trade info"""
        endpoint = "/v1/order/status"
        payload = {
            "request": endpoint,
            "nonce": get_nonce(),
            "order_id": order_id
        }
        response = await self._make_request(endpoint, payload)
        return parse_response(response, OrderStatusResponse)

    @with_retry(max_retries=3, base_delay=1.0)
    async def get_active_orders(self) -> ActiveOrdersResponse:
        """Get all active orders"""
        endpoint = "/v1/orders"
        payload = {
            "request": endpoint,
            "nonce": get_nonce()
        }
        response = await self._make_request(endpoint, payload)
        return ActiveOrdersResponse.from_response(response)

    @with_retry(max_retries=3, base_delay=1.0)
    async def cancel_order(self, order_id: str) -> CancelOrderResponse:
        """Cancel an order"""
        endpoint = "/v1/order/cancel"
        payload = {
            "request": endpoint,
            "nonce": get_nonce(),
            "order_id": order_id
        }
        response = await self._make_request(endpoint, payload)
        return parse_response(response, CancelOrderResponse)

    @with_retry(max_retries=3, base_delay=1.0)
    async def get_order_history(self) -> OrderHistoryResponse:
        endpoint = "/v1/orders/history"
        payload = {
            "request": endpoint,
            "nonce": get_nonce()
        }
        response = await self._make_request(endpoint, payload)
        return OrderHistoryResponse.from_response(response)

    @with_retry(max_retries=3, base_delay=1.0)
    async def get_price(self, symbol: Symbol) -> str:
        """Get current price for a symbol"""
        endpoint = f"/v1/pubticker/{symbol.value}"
        
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        url = f"{self.base_url}{endpoint}"
        async with self.session.get(url) as response:
            data = await response.json()
            return data['last']  # Returns last traded price