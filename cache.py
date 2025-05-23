import redis
from config import Config
import json
from functools import lru_cache
from cachetools import TTLCache
import zlib
import logging

class RedisCache:
    _instance = None
    _client = None
    _local_cache = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            self._client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                decode_responses=True,
                socket_timeout=Config.CONNECTION_TIMEOUT
            )
            self._local_cache = TTLCache(
                maxsize=Config.CACHE_MAX_SIZE,
                ttl=Config.CACHE_TTL
            )

    def _compress(self, data: str) -> bytes:
        return zlib.compress(data.encode(), level=Config.COMPRESSION_LEVEL)

    def _decompress(self, data: bytes) -> str:
        return zlib.decompress(data).decode()

    def get(self, key: str) -> str:
        # Tenta primeiro no cache local
        if key in self._local_cache:
            return self._local_cache[key]
        
        # Se não encontrou, busca no Redis
        try:
            value = self._client.get(key)
            if value:
                # Atualiza cache local
                self._local_cache[key] = value
            return value
        except redis.RedisError as e:
            logging.error(f"Erro ao acessar Redis: {e}")
            return None

    def set(self, key: str, value: str, ttl: int = None) -> bool:
        try:
            # Comprime o valor antes de salvar
            compressed_value = self._compress(value)
            self._client.setex(key, ttl or Config.REDIS_TTL, compressed_value)
            # Atualiza cache local
            self._local_cache[key] = value
            return True
        except redis.RedisError as e:
            logging.error(f"Erro ao salvar no Redis: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            self._client.delete(key)
            # Remove do cache local
            self._local_cache.pop(key, None)
            return True
        except redis.RedisError as e:
            logging.error(f"Erro ao deletar do Redis: {e}")
            return False

    def clear_local_cache(self):
        self._local_cache.clear()

    @lru_cache(maxsize=1000)
    def get_metadata(self, file_path: str) -> dict:
        key = f"metadata:{file_path}"
        data = self.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                logging.error(f"Erro ao decodificar JSON: {e}")
                return None
        return None

    def set_metadata(self, file_path: str, metadata: dict) -> bool:
        key = f"metadata:{file_path}"
        return self.set(key, json.dumps(metadata))

    def batch_get(self, keys: list) -> dict:
        try:
            values = self._client.mget(keys)
            return {k: v for k, v in zip(keys, values) if v is not None}
        except redis.RedisError as e:
            logging.error(f"Erro no batch get do Redis: {e}")
            return {}

    def batch_set(self, data: dict, ttl: int = None) -> bool:
        try:
            pipe = self._client.pipeline()
            for key, value in data.items():
                compressed_value = self._compress(value)
                pipe.setex(key, ttl or Config.REDIS_TTL, compressed_value)
            pipe.execute()
            return True
        except redis.RedisError as e:
            logging.error(f"Erro no batch set do Redis: {e}")
            return False 