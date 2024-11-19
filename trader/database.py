from sqlmodel import Session, select, create_engine
from trader.models import Order, OrderState, OrderType, TradingStrategy, StrategyType, StrategyState
from trader.config import SQLITE_DATABASE_URL
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import and_
from sqlalchemy.engine.base import Engine

# Initialize default database engine
default_engine = create_engine(SQLITE_DATABASE_URL, echo=False)

def get_engine():
    """Get the current database engine"""
    return default_engine

def get_session(engine=None):
    """Get a new session for the database"""
    engine = engine or default_engine
    return Session(engine)

def init_db(engine=None):
    """Initialize the database by creating all tables if they don't exist"""
    from trader.models import SQLModel  # Import here to avoid circular imports
    engine = engine or default_engine
    SQLModel.metadata.create_all(engine, checkfirst=True)

def load_orders(session: Optional[Session] = None, engine=None) -> List[Order]:
    """Get all orders from the database"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order)
        return session.exec(statement).all()
    finally:
        if local_session:
            session.close()

def get_open_buy_orders(session: Optional[Session] = None, engine=None) -> List[Order]:
    """Get all open buy orders that don't have sell orders placed"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order).where(
            and_(
                Order.side == "buy",
                Order.status.in_([OrderState.PLACED.value])
            )
        )
        return session.exec(statement).all()
    finally:
        if local_session:
            session.close()

def save_order(order_data: Dict[str, Any], session: Optional[Session] = None, engine: Optional[Engine] = None) -> Order:
    """
    Save a new order to the database.
    
    Args:
        order_data: Dictionary containing order data
        session: Optional existing session to use
        engine: Optional engine to use if no session provided
        
    Returns:
        Order: The saved order instance
    """
    # Session management
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        # Convert string values to enum values if needed
        if isinstance(order_data.get('status'), str):
            order_data['status'] = OrderState(order_data['status'])
        if isinstance(order_data.get('order_type'), str):
            order_data['order_type'] = OrderType(order_data['order_type'])

        order = Order(**order_data)
        session.add(order)
        session.commit()
        session.refresh(order)
        return order
    finally:
        if local_session:
            session.close()

def update_order(order_id: str, session: Optional[Session] = None, engine: Optional[Engine] = None, **updates) -> Optional[Order]:
    """Update an existing order in the database"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order).where(Order.order_id == order_id)
        order = session.exec(statement).first()
        if order:
            for key, value in updates.items():
                setattr(order, key, value)
            order.updated_at = datetime.utcnow()
            session.add(order)
            if local_session:
                session.commit()
            return order
        return None
    finally:
        if local_session:
            session.close()

def get_order_by_id(order_id: str, session: Optional[Session] = None, engine=None) -> Optional[Order]:
    """Get a specific order by its order_id"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order).where(Order.order_id == order_id)
        return session.exec(statement).first()
    finally:
        if local_session:
            session.close()

def get_orders_by_parent_id(parent_order_id: str, session: Optional[Session] = None, engine=None) -> List[Order]:
    """Get all orders associated with a parent order"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order).where(Order.parent_order_id == parent_order_id)
        return session.exec(statement).all()
    finally:
        if local_session:
            session.close()

def delete_order(order_id: str, session: Optional[Session] = None, engine=None) -> bool:
    """Delete an order from the database"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(Order).where(Order.order_id == order_id)
        order = session.exec(statement).first()
        if order:
            session.delete(order)
            session.commit()
            return True
        return False
    finally:
        if local_session:
            session.close()

def save_strategy(strategy_data: Dict[str, Any], session: Optional[Session] = None, engine: Optional[Engine] = None) -> TradingStrategy:
    """
    Save a new trading strategy to the database.
    
    Args:
        strategy_data: Dictionary containing strategy configuration
        session: Optional existing session to use
        engine: Optional engine to use if no session provided
    """
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        # Convert string values to enum values if needed
        if isinstance(strategy_data.get('type'), str):
            strategy_data['type'] = StrategyType(strategy_data['type'])
        if isinstance(strategy_data.get('state'), str):
            strategy_data['state'] = StrategyState(strategy_data['state'])

        strategy = TradingStrategy(**strategy_data)
        session.add(strategy)
        session.commit()
        session.refresh(strategy)
        return strategy
    finally:
        if local_session:
            session.close()

def get_active_strategies(session: Optional[Session] = None, engine=None) -> List[TradingStrategy]:
    """Get all active trading strategies"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(TradingStrategy).where(
            and_(
                TradingStrategy.is_active == True,
                TradingStrategy.state != StrategyState.COMPLETED
            )
        )
        return session.exec(statement).all()
    finally:
        if local_session:
            session.close()

def get_strategy_by_id(strategy_id: int, session: Optional[Session] = None, engine=None) -> Optional[TradingStrategy]:
    """Get a specific strategy by its ID"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(TradingStrategy).where(TradingStrategy.id == strategy_id)
        return session.exec(statement).first()
    finally:
        if local_session:
            session.close()

def update_strategy(strategy_id: int, session: Optional[Session] = None, engine=None, **updates) -> Optional[TradingStrategy]:
    """Update an existing strategy in the database"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(TradingStrategy).where(TradingStrategy.id == strategy_id)
        strategy = session.exec(statement).first()
        if strategy:
            for key, value in updates.items():
                if key == 'type' and isinstance(value, str):
                    value = StrategyType(value)
                elif key == 'state' and isinstance(value, str):
                    value = StrategyState(value)
                setattr(strategy, key, value)
            strategy.updated_at = datetime.utcnow()
            session.add(strategy)
            if local_session:
                session.commit()
            session.refresh(strategy)
            return strategy
        return None
    finally:
        if local_session:
            session.close()

def get_strategy_by_name(name: str, session: Optional[Session] = None, engine=None) -> Optional[TradingStrategy]:
    """Get a specific strategy by its name"""
    local_session = False
    if session is None:
        engine = engine or default_engine
        session = Session(engine)
        local_session = True

    try:
        statement = select(TradingStrategy).where(TradingStrategy.name == name)
        return session.exec(statement).first()
    finally:
        if local_session:
            session.close() 