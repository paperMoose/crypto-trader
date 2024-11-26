from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import JSON
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from decimal import Decimal

class StrategyType(str, Enum):
    RANGE = "range"
    BREAKOUT = "breakout"
    TAKE_PROFIT = "take_profit"

class OrderType(str, Enum):
    LIMIT_BUY = "limit_buy"
    LIMIT_SELL = "limit_sell"
    STOP_LIMIT_BUY = "stop_limit_buy"
    STOP_LIMIT_SELL = "stop_limit_sell"

class StrategyState(str, Enum):
    INIT = "init"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class OrderState(str, Enum):
    ACCEPTED = "accepted"
    LIVE = "live"
    CANCELLED = "cancelled"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    REJECTED = "rejected"

class TradingStrategy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    type: StrategyType
    symbol: str
    # For JSON fields, provide an empty dict directly instead of using default_factory
    config: Dict[str, Any] = Field(default={}, sa_type=JSON)
    state: StrategyState = Field(default=StrategyState.INIT)
    is_active: bool = Field(default=True)
    # For datetime fields, use default instead of default_factory
    created_at: datetime = Field(default=datetime.utcnow())
    updated_at: datetime = Field(default=datetime.utcnow())
    last_checked_at: datetime = Field(default=datetime.utcnow())
    check_interval: int = Field(default=1)
    total_profit: str = Field(default="0.0")
    realized_profit: str = Field(default="0.0")
    tax_reserve: str = Field(default="0.0")
    available_profit: str = Field(default="0.0")
    
    orders: List["Order"] = Relationship(back_populates="strategy")

class Order(SQLModel, table=True):
    __tablename__ = "order"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(unique=True)
    status: OrderState
    amount: str
    price: str
    side: str
    symbol: str
    order_type: OrderType
    stop_price: Optional[str] = None
    # For datetime fields, use default instead of default_factory
    created_at: datetime = Field(default=datetime.utcnow())
    updated_at: datetime = Field(default=datetime.utcnow())
    parent_order_id: Optional[str] = Field(default=None, foreign_key="order.order_id")
    strategy_id: Optional[int] = Field(default=None, foreign_key="tradingstrategy.id")
    
    strategy: Optional[TradingStrategy] = Relationship(back_populates="orders")