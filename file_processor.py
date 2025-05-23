import os
import hashlib
import subprocess
import json
import mmap
import logging
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from config import Config
from cache import RedisCache
from db import Database
from typing import List, Dict, Any, Optional

class FileProcessor:
    def __init__(self):
        self.cache = RedisCache()
        self.db = Database()
        self._hash_cache = {}
        self._ffprobe_cache = {}

    def calculate_hash(self, file_path: str) -> str:
        # Verifica cache local primeiro
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]

        try:
            with open(file_path, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    sha256_hash = hashlib.sha256(mm).hexdigest()
                    self._hash_cache[file_path] = sha256_hash
                    return sha256_hash
        except Exception as e:
            logging.error(f"Erro ao calcular hash de {file_path}: {e}")
            # Fallback para método tradicional
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(Config.CHUNK_SIZE), b""):
                    sha256_hash.update(byte_block)
            hash_value = sha256_hash.hexdigest()
            self._hash_cache[file_path] = hash_value
            return hash_value

    def get_video_metadata(self, file_path: str) -> Dict[str, Any]:
        # Tenta obter do cache primeiro
        cached_metadata = self.cache.get_metadata(file_path)
        if cached_metadata:
            return cached_metadata

        # Se não estiver em cache, busca do banco
        result = self.db.execute_query(
            "SELECT video_codec, resolution, orientation, duration_seconds FROM endoflix_files WHERE file_path = %s",
            (file_path,)
        )

        if result:
            metadata = {
                "video_codec": result[0][0],
                "resolution": result[0][1],
                "orientation": result[0][2],
                "duration_seconds": result[0][3]
            }
            self.cache.set_metadata(file_path, metadata)
            return metadata

        # Se não estiver no banco, extrai com ffprobe
        return self._extract_metadata_with_ffprobe(file_path)

    def _extract_metadata_with_ffprobe(self, file_path: str) -> Dict[str, Any]:
        # Verifica cache de ffprobe
        if file_path in self._ffprobe_cache:
            return self._ffprobe_cache[file_path]

        for attempt in range(Config.MAX_RETRIES):
            try:
                cmd = [Config.FFPROBE_PATH, "-v", "error", "-show_entries", 
                      "stream=codec_type,codec_name,width,height,duration", 
                      "-of", "json", file_path]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                metadata = self._parse_ffprobe_output(result.stdout)
                self.cache.set_metadata(file_path, metadata)
                self._ffprobe_cache[file_path] = metadata
                return metadata
            except subprocess.CalledProcessError as e:
                logging.error(f"Erro ao executar ffprobe (tentativa {attempt + 1}): {e}")
                if attempt == Config.MAX_RETRIES - 1:
                    break
                time.sleep(Config.RETRY_DELAY * (attempt + 1))

        return {
            "duration_seconds": 0,
            "resolution": "unknown",
            "orientation": "unknown",
            "video_codec": "unknown"
        }

    def _parse_ffprobe_output(self, output: str) -> Dict[str, Any]:
        try:
            data = json.loads(output)
            streams = data.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
            
            duration = float(video_stream.get("duration", 0))
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            resolution = f"{width}x{height}" if width and height else "unknown"
            orientation = "portrait" if width < height else "landscape" if width > height else "square"
            video_codec = video_stream.get("codec_name", "unknown")
            
            return {
                "duration_seconds": duration,
                "resolution": resolution,
                "orientation": orientation,
                "video_codec": video_codec
            }
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar saída do ffprobe: {e}")
            return {
                "duration_seconds": 0,
                "resolution": "unknown",
                "orientation": "unknown",
                "video_codec": "unknown"
            }

    def process_files_batch(self, files: List[Path]) -> List[Dict[str, Any]]:
        results = []
        with ProcessPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            futures = []
            for file in files:
                futures.append(executor.submit(self._process_single_file, file))
            
            for future in futures:
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logging.error(f"Erro ao processar arquivo: {e}")
        
        return results

    def _process_single_file(self, file: Path) -> Optional[Dict[str, Any]]:
        try:
            file_path = str(file)
            stats = os.stat(file)
            hash_id = self.calculate_hash(file)
            metadata = self.get_video_metadata(file)
            
            return {
                "hash_id": hash_id,
                "file_path": file_path,
                "size_bytes": stats.st_size,
                "created_at": stats.st_ctime,
                "modified_at": stats.st_mtime,
                "duration_seconds": metadata["duration_seconds"],
                "resolution": metadata["resolution"],
                "orientation": metadata["orientation"],
                "video_codec": metadata["video_codec"],
                "view_count": 0,
                "last_viewed_at": None,
                "is_favorite": False
            }
        except Exception as e:
            logging.error(f"Erro ao processar arquivo {file}: {e}")
            return None 