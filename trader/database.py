from sqlmodel import Session, select
from trader.models import Order, engine
from datetime import datetime
from typing import List, Optional, Dict, Any

def load_orders() -> List[Order]:
    """Get all orders from the database"""
    with Session(engine) as session:
        statement = select(Order)
        return session.exec(statement).all()

def get_open_buy_orders() -> List[Order]:
    """Get all open buy orders that don't have sell orders placed"""
    with Session(engine) as session:
        statement = select(Order).where(
            Order.side == "buy",
            Order.status == "open",
            Order.sell_orders_placed == False
        )
        return session.exec(statement).all()

def save_order(order_data, session: Session = None):
    if session is None:
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

def update_order(order_id: str, **updates) -> Optional[Order]:
    """Update an existing order in the database"""
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

def get_order_by_id(order_id: str) -> Optional[Order]:
    """Get a specific order by its order_id"""
    with Session(engine) as session:
        statement = select(Order).where(Order.order_id == order_id)
        return session.exec(statement).first()

def get_orders_by_parent_id(parent_order_id: str) -> List[Order]:
    """Get all orders associated with a parent order"""
    with Session(engine) as session:
        statement = select(Order).where(Order.parent_order_id == parent_order_id)
        return session.exec(statement).all()

def delete_order(order_id: str) -> bool:
    """Delete an order from the database"""
    with Session(engine) as session:
        statement = select(Order).where(Order.order_id == order_id)
        order = session.exec(statement).first()
        if order:
            session.delete(order)
            session.commit()
            return True
    return False 