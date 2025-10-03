from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass, field

@dataclass
class Config:
    # Database
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 20
    DB_PARAMS: Dict[str, Any] = field(default_factory=lambda: {
        'dbname': 'videos',
        'user': 'postgres',
        'password': 'admin',
        'host': 'localhost',
        'port': '5432'
    })
    CONNECTION_TIMEOUT: int = 30
    POOL_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1

    # Redis
    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_TTL: int = 86400  # 24 horas
    CACHE_MAX_SIZE: int = 1000
    CACHE_TTL: int = 3600
    COMPRESSION_LEVEL: int = 6

    # Paths
    FFPROBE_PATH: str = r"C:\Program Files\FFMPEG\bin\ffprobe.exe"
    FFMPEG_PATH: str = r"C:\Program Files\FFMPEG\bin\ffmpeg.exe"
    REDIS_SERVER_PATH: str = r"C:\Program Files\Redis\redis-server.exe"
    TRANSCODE_DIR: Path = Path("transcode")

    # Processing
    MAX_WORKERS: int = 8
    SNAPSHOT_WORKERS: int = 6
    CHUNK_SIZE: int = 4096  # Para leitura de arquivos
    BATCH_SIZE: int = 100   # Para processamento em lote
    QUEUE_MAX_SIZE: int = 1000  # Para backpressure

    # Thumbnails
    THUMB_SIZE: int = 50
    THUMB_FORMAT: str = 'webp'
    THUMB_QUALITY: int = 80  # For WebP
    THUMB_EXTRACTION_POINT: float = 0.1  # 10% into video
    THUMB_WORKERS: int = 4
    FFMPEG_TIMEOUT: int = 60  # Timeout for FFmpeg commands in seconds
    THUMB_BATCH_SIZE: int = 100  # Process videos in batches of 100