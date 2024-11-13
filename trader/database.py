from sqlmodel import Session, select, create_engine
from trader.models import Order
from trader.config import SQLITE_DATABASE_URL
from datetime import datetime
from typing import List, Optional, Dict, Any

# Initialize default database engine
default_engine = create_engine(SQLITE_DATABASE_URL, echo=False)

def get_engine():
    """Get the current database engine"""
    return default_engine

def init_db(engine=None):
    """Initialize the database by creating all tables if they don't exist"""
    from trader.models import SQLModel  # Import here to avoid circular imports
    engine = engine or default_engine
    SQLModel.metadata.create_all(engine, checkfirst=True)

def load_orders(engine=None) -> List[Order]:
    """Get all orders from the database"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order)
        return session.exec(statement).all()

def get_open_buy_orders(engine=None) -> List[Order]:
    """Get all open buy orders that don't have sell orders placed"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order).where(
            Order.side == "buy",
            Order.status == "open",
            Order.sell_orders_placed == False
        )
        return session.exec(statement).all()

def save_order(order_data, session: Session = None, engine=None):
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        should_close = True
    else:
        should_close = False

    try:
        order = Order(**order_data)
        session.add(order)
        session.commit()
        session.refresh(order)
        return order
    finally:
        if should_close:
            session.close()

def update_order(order_id: str, engine=None, **updates) -> Optional[Order]:
    """Update an existing order in the database"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order).where(Order.order_id == order_id)
        order = session.exec(statement).first()
        if order:
            for key, value in updates.items():
                setattr(order, key, value)
            order.updated_at = datetime.utcnow()
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
    return None

def get_order_by_id(order_id: str, engine=None) -> Optional[Order]:
    """Get a specific order by its order_id"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order).where(Order.order_id == order_id)
        return session.exec(statement).first()

def get_orders_by_parent_id(parent_order_id: str, engine=None) -> List[Order]:
    """Get all orders associated with a parent order"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order).where(Order.parent_order_id == parent_order_id)
        return session.exec(statement).all()

def delete_order(order_id: str, engine=None) -> bool:
    """Delete an order from the database"""
    engine = engine or default_engine
    with Session(engine) as session:
        statement = select(Order).where(Order.order_id == order_id)
        order = session.exec(statement).first()
        if order:
            session.delete(order)
            session.commit()
            return True
    return False 