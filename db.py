
import pg8000
from contextlib import contextmanager
from config import Config
import threading
import time
from queue import Queue, Empty

class Database:
    _instance = None
    _connections = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        with self._lock:
            if self._connections is None:
                config = Config()
                self._connections = Queue(maxsize=config.DB_POOL_MAX)
                for _ in range(config.DB_POOL_MIN):
                    self._create_connection()

    def _create_connection(self):
        config = Config()
        try:
            conn = pg8000.connect(
                database=config.DB_PARAMS['dbname'],
                user=config.DB_PARAMS['user'],
                password=config.DB_PARAMS['password'],
                host=config.DB_PARAMS['host'],
                port=int(config.DB_PARAMS['port'])
            )
            self._connections.put(conn)
        except Exception as e:
            print(f"Failed to create database connection: {e}")

    @contextmanager
    def get_connection(self):
        if self._connections is None:
            raise RuntimeError("Database connections not initialized")
        conn = self._connections.get(timeout=30)
        try:
            yield conn
        finally:
            self._connections.put(conn)

    def getconn(self):
        if self._connections is None:
            raise RuntimeError("Database connections not initialized")
        try:
            return self._connections.get(timeout=30)
        except Empty:
            self._create_connection()
            return self._connections.get(timeout=30)

    def putconn(self, conn):
        if self._connections is None:
            # If connections are closed, just close this connection
            try:
                conn.close()
            except:
                pass
            return
        try:
            self._connections.put(conn, timeout=5)
        except:
            # If we can't return the connection, close it
            try:
                conn.close()
            except:
                pass

    def closeall(self):
        with self._lock:
            if self._connections is not None:
                while not self._connections.empty():
                    try:
                        conn = self._connections.get_nowait()
                        conn.close()
                    except:
                        break
                self._connections = None

    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            return result

    def execute_update(self, query, params=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            rowcount = cursor.rowcount
            cursor.close()
            return rowcount