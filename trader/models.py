from sqlmodel import SQLModel, Field, create_engine
from typing import Optional
from datetime import datetime
from trader.client import OrderSide, OrderType, Symbol

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True)
    status: str
    amount: str
    price: str
    side: str
    symbol: str
    order_type: str
    parent_order_id: Optional[str] = Field(default=None, index=True)
    type: Optional[str] = None  # For stop-loss, take-profit-1, take-profit-2
    sell_orders_placed: bool = Field(default=False)
    stop_price: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# Create SQLite database engine
DATABASE_URL = "sqlite:///orders.db"
engine = create_engine(DATABASE_URL)

# Create all tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine) 