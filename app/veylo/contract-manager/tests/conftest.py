import os
import pytest

# Force sqlite in-memory for testing before importing application modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATA_BACKEND"] = "sqlite"
os.environ["SECRET_KEY"] = "test-secret-key"

import database
from app import create_app
from models.orm import Base


@pytest.fixture(autouse=True)
def setup_database():
    """Create in-memory SQLite tables before each test and drop them after."""
    Base.metadata.create_all(bind=database.engine)
    yield
    Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
