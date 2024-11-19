from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    ACCEPTED = "accepted"
    LIVE = "live"
    CANCELLED = "cancelled"
    FILLED = "filled"
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
        """Calculate remaining_amount if not provided"""
        if self.remaining_amount is None:
            # Convert to float for calculation, then back to string
            executed = float(self.executed_amount)
            original = float(self.original_amount)
            self.remaining_amount = str(original - executed)

class OrderStatusResponse(OrderResponse):
    trades: Optional[List[dict]] = None

class ActiveOrdersResponse(BaseModel):
    orders: List[OrderResponse]

    @classmethod
    def from_response(cls, response: List[dict]):
        return cls(orders=[OrderResponse(**order) for order in response])

class CancelOrderResponse(OrderResponse):
    cancelled: bool
    reason: Optional[str] = None

class ErrorResponse(BaseModel):
    result: str
    reason: str
    message: str

def parse_response(response_data: dict, response_type: type[BaseModel]) -> BaseModel:
    """
    Parse API response into appropriate Pydantic model
    
    Args:
        response_data: Raw API response dictionary
        response_type: Pydantic model class to parse into
        
    Returns:
        Parsed Pydantic model instance
    """
    if "result" in response_data and response_data["result"] == "error":
        return ErrorResponse(**response_data)
    
    return response_type(**response_data) 