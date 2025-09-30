
import psycopg2.pool
from contextlib import contextmanager
from config import Config

class Database:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            config = Config()
            self._pool = psycopg2.pool.SimpleConnectionPool(
                config.DB_POOL_MIN,
                config.DB_POOL_MAX,
                **config.DB_PARAMS
            )

    @contextmanager
    def get_connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def getconn(self):
        return self._pool.getconn()

    def putconn(self, conn):
        self._pool.putconn(conn)

    def closeall(self):
        if self._pool:
            self._pool.closeall()
            self._pool = None

    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                return cur.fetchall()

    def execute_update(self, query, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                conn.commit()
                return cur.rowcount