from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import JSON
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class StrategyType(str, Enum):
    RANGE = "range"
    BREAKOUT = "breakout"

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

class OrderState(str, Enum):
    ACCEPTED = "accepted"
    LIVE = "live"
    CANCELLED = "cancelled"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    REJECTED = "rejected"

class TradingStrategy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    type: StrategyType
    symbol: str
    config: Dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    state: StrategyState = Field(default=StrategyState.INIT)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_checked_at: datetime = Field(default_factory=datetime.utcnow)
    check_interval: int = Field(default=1)
    
    orders: List["Order"] = Relationship(back_populates="strategy")

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True, unique=True)
    status: OrderState
    amount: str
    price: str
    side: str
    symbol: str
    order_type: OrderType
    stop_price: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    parent_order_id: Optional[str] = Field(
        default=None, 
        foreign_key="order.order_id", 
        index=True
    )
    
    strategy_id: Optional[int] = Field(default=None, foreign_key="tradingstrategy.id")
    strategy: Optional[TradingStrategy] = Relationship(back_populates="orders")
 