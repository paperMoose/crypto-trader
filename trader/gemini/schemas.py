from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    ACCEPTED = "accepted"
    LIVE = "live"
    CANCELLED = "cancelled"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    REJECTED = "rejected"

class OrderResponse(BaseModel):
    order_id: str
    id: str
    symbol: str
    exchange: str
    avg_execution_price: str = "0"
    side: str
    type: str
    timestamp: datetime
    timestampms: int
    is_live: bool
    is_cancelled: bool
    is_hidden: bool
    was_forced: bool
    executed_amount: str
    remaining_amount: str | None = None
    original_amount: str
    price: str
    stop_price: Optional[str] = None
    client_order_id: Optional[str] = None
    options: List[str]
    status: OrderStatus | None = None

    def model_post_init(self, __context) -> None:
        """Calculate remaining_amount and set status based on order state"""
        # Calculate remaining amount if not provided
        if self.remaining_amount is None:
            executed = float(self.executed_amount)
            original = float(self.original_amount)
            self.remaining_amount = str(original - executed)

        # Set status based on order state
        if self.is_cancelled:
            self.status = OrderStatus.CANCELLED
        elif float(self.executed_amount) == float(self.original_amount):
            self.status = OrderStatus.FILLED
        elif float(self.executed_amount) > 0:
            # Has some executions but not fully filled
            self.status = OrderStatus.PARTIAL_FILL
        elif self.is_live:
            # Order is live but no executions yet
            self.status = OrderStatus.LIVE
        else:
            # No executions, not live, not cancelled - must be accepted
            self.status = OrderStatus.ACCEPTED

class OrderStatusResponse(OrderResponse):
    trades: Optional[List[dict]] = None

class ActiveOrdersResponse(BaseModel):
    orders: List[OrderResponse]

    @classmethod
    def from_response(cls, response: List[dict]):
        return cls(orders=[OrderResponse(**order) for order in response])

class CancelOrderResponse(BaseModel):
    order_id: str
    cancelled: bool = True
    original_amount: str
    executed_amount: str
    remaining_amount: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled

class ErrorResponse(BaseModel):
    result: str
    reason: str
    message: str

class GeminiAPIError(Exception):
    """Exception raised for Gemini API errors"""
    def __init__(self, response: 'ErrorResponse'):
        self.response = response
        super().__init__(f"Gemini API Error: {response.message} (Reason: {response.reason})")

def parse_response(response_data: dict, response_type: type[BaseModel]) -> BaseModel:
    """
    Parse API response into appropriate Pydantic model
    
    Args:
        response_data: Raw API response dictionary
        response_type: Pydantic model class to parse into
        
    Returns:
        Parsed Pydantic model instance
        
    Raises:
        GeminiAPIError: If the API returns an error response
    """
    if "result" in response_data and response_data["result"] == "error":
        error_response = ErrorResponse(**response_data)
        raise GeminiAPIError(error_response)
    
    return response_type(**response_data) 

class OrderHistoryResponse(BaseModel):
    orders: List[OrderResponse]

    @classmethod
    def from_response(cls, response: List[dict]):
        # Convert each order dict to an OrderResponse object
        orders = [OrderResponse(**order) for order in response]
        return cls(orders=orders) 