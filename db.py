
import pg8000
from contextlib import contextmanager
from config import Config
import threading
import time
import logging
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
                logging.info(f"Initializing database connection pool with min={config.DB_POOL_MIN}, max={config.DB_POOL_MAX}")
                for _ in range(config.DB_POOL_MIN):
                    self._create_connection()
                logging.info(f"Database connection pool initialized with {self._connections.qsize()} connections")

    def _create_connection(self):
        config = Config()
        try:
            logging.debug(f"Attempting to connect to DB: {config.DB_PARAMS['host']}:{config.DB_PARAMS['port']}/{config.DB_PARAMS['dbname']}")
            conn = pg8000.connect(
                database=config.DB_PARAMS['dbname'],
                user=config.DB_PARAMS['user'],
                password=config.DB_PARAMS['password'],
                host=config.DB_PARAMS['host'],
                port=int(config.DB_PARAMS['port'])
            )
            if self._connections is not None:
                self._connections.put(conn)
                logging.debug("Database connection created and added to pool")
            else:
                logging.error("Connection pool not initialized")
        except Exception as e:
            logging.error(f"Failed to create database connection: {e}")

    @contextmanager
    def get_connection(self):
        if self._connections is None:
            raise RuntimeError("Database connections not initialized")
        logging.debug(f"Attempting to get connection from pool. Current pool size: {self._connections.qsize()}")
        try:
            conn = self._connections.get(timeout=30)
            logging.debug("Connection acquired from pool")
        except Empty:
            logging.warning("Connection pool is empty, attempting to create new connection")
            self._create_connection()
            try:
                conn = self._connections.get(timeout=30)
                logging.debug("New connection acquired from pool")
            except Empty:
                logging.error("Failed to acquire connection after creating new one")
                raise
        try:
            yield conn
        finally:
            if self._connections is not None:
                self._connections.put(conn)
                logging.debug("Connection returned to pool")

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