import pytest
from sqlmodel import Session, SQLModel, create_engine

@pytest.fixture(name="engine")
def engine_fixture():
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:", echo=True)
    SQLModel.metadata.create_all(engine)
    return engine

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session
        session.rollback() 