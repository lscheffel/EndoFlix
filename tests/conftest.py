import pytest
from main import app, DB_POOL
import psycopg2.pool
from flask_login import login_user
from auth import User

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

@pytest.fixture
def test_db(db_connection):
    """Fixture to provide a clean database state for tests."""
    conn = db_connection
    with conn.cursor() as cur:
        # Clean up test data
        cur.execute("DELETE FROM endoflix_playlist WHERE name LIKE 'test_%'")
        cur.execute("DELETE FROM endoflix_files WHERE file_path LIKE 'test_%'")
        conn.commit()
    yield conn
    # Cleanup after test
    with conn.cursor() as cur:
        cur.execute("DELETE FROM endoflix_playlist WHERE name LIKE 'test_%'")
        cur.execute("DELETE FROM endoflix_files WHERE file_path LIKE 'test_%'")
        conn.commit()

@pytest.fixture
def authenticated_client(client):
    """Fixture to provide a client logged in as admin."""
    # Simulate login
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert response.status_code == 200
    return client