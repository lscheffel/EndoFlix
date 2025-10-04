from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config

redis_url = f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/{Config.REDIS_DB}"
limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)