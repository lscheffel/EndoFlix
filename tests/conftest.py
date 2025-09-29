import pytest
from main import app, DB_POOL
import psycopg2.pool

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def db_connection():
    # For testing, we might want to use a test database
    # For now, just return the existing pool
    conn = DB_POOL.getconn()
    yield conn
    DB_POOL.putconn(conn)