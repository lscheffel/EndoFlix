import os
import hashlib
import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from db import Database
from config import Config
from cache import RedisCache

DB_POOL = Database()  # Create database instance
REDIS_CLIENT = RedisCache()  # Create cache instance
FFPROBE_PATH = Config.FFPROBE_PATH

def calculate_hash(file_path, max_bytes=2*1024*1024):  # 2MB início + 2MB meio
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Primeiros 2MB
        bytes_read = 0
        while bytes_read < max_bytes:
            byte_block = f.read(4096)
            if not byte_block:
                break
            sha256_hash.update(byte_block)
            bytes_read += len(byte_block)
        # Pular para o meio do arquivo
        file_size = os.stat(file_path).st_size
        if file_size > max_bytes * 2:
            f.seek(file_size // 2)
            bytes_read = 0
            while bytes_read < max_bytes:
                byte_block = f.read(4096)
                if not byte_block:
                    break
                sha256_hash.update(byte_block)
                bytes_read += len(byte_block)
    return sha256_hash.hexdigest()

def get_video_metadata(file_path):
    file_path_str = str(file_path)
    # Try cache first
    cached = REDIS_CLIENT.get(f"metadata:{file_path_str}")
    if cached:
        return json.loads(cached)

    # Query database
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT video_codec, resolution, orientation, duration_seconds FROM endoflix_files WHERE file_path = %s", (file_path_str,))
                result = cur.fetchone()
                if result:
                    video_codec, resolution, orientation, duration_seconds = result
                    metadata = {
                        "video_codec": video_codec,
                        "resolution": resolution,
                        "orientation": orientation,
                        "duration_seconds": duration_seconds
                    }
                    # Cache the result
                    REDIS_CLIENT.set(f"metadata:{file_path_str}", json.dumps(metadata), ttl=86400)
                    return metadata
            except Exception as e:
                logging.error(f"Erro ao consultar metadados no banco para {file_path_str}: {e}")

    try:
        cmd = [FFPROBE_PATH, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,duration", "-of", "json", file_path_str]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

        duration = float(video_stream.get("duration", 0))
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        resolution = f"{width}x{height}" if width and height else "unknown"
        orientation = "portrait" if width < height else "landscape" if width > height else "square"
        video_codec = video_stream.get("codec_name", "unknown")

        result = {
            "duration_seconds": duration,
            "resolution": resolution,
            "orientation": orientation,
            "video_codec": video_codec
        }
        # Cache the result
        REDIS_CLIENT.set(f"metadata:{file_path_str}", json.dumps(result), ttl=86400)
        return result
    except Exception as e:
        logging.error(f"Erro ao extrair metadados de {file_path_str}: {e}")
        return {
            "duration_seconds": 0,
            "resolution": "unknown",
            "orientation": "unknown",
            "video_codec": "unknown"
        }

def process_file(file):
    file_path_str = str(file)
    stats = os.stat(file)
    hash_id = calculate_hash(file)
    metadata = get_video_metadata(file)
    return {
        "hash_id": hash_id,
        "file_path": file_path_str,
        "size_bytes": stats.st_size,
        "created_at": datetime.fromtimestamp(stats.st_birthtime),
        "modified_at": datetime.fromtimestamp(stats.st_mtime),
        "duration_seconds": metadata["duration_seconds"],
        "resolution": metadata["resolution"],
        "orientation": metadata["orientation"],
        "video_codec": metadata["video_codec"],
        "view_count": 0,
        "last_viewed_at": None,
        "is_favorite": False
    }

def index_file(conn, file_data):
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO endoflix_files (id, hash_id, file_path, size_bytes, created_at, modified_at, video_codec, resolution, orientation, duration_seconds, view_count, last_viewed_at, is_favorite)
            VALUES (DEFAULT, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            file_data["hash_id"],
            file_data["file_path"],
            file_data["size_bytes"],
            file_data["created_at"],
            file_data["modified_at"],
            file_data["video_codec"],
            file_data["resolution"],
            file_data["orientation"],
            file_data["duration_seconds"],
            file_data["view_count"],
            file_data["last_viewed_at"],
            file_data["is_favorite"]
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao indexar {file_data['file_path']}: {e}")
    finally:
        cur.close()

def get_media_files(folder):
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        yield f"data: {json.dumps({'status': 'error', 'message': 'Pasta inválida ou não encontrada'})}\n\n"
        return

    files_to_process = [file for file in folder_path.rglob('*') if file.is_file() and file.suffix.lower() in ['.mp4', '.mkv', '.mov', '.divx', '.webm', '.mpg', '.avi']]
    if not files_to_process:
        yield f"data: {json.dumps({'status': 'end', 'total': 0, 'message': 'Nenhum arquivo de mídia encontrado'})}\n\n"
        return

    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            # Obter arquivos atualmente indexados para a pasta
            cur.execute("SELECT file_path FROM endoflix_files WHERE file_path LIKE %s", (f"{str(folder_path)}%",))
            db_files = {row[0] for row in cur.fetchall()}

        current_files = {str(file) for file in files_to_process}
        # Arquivos para remover do DB (não estão mais na pasta)
        files_to_remove = db_files - current_files
        if files_to_remove:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM endoflix_files WHERE file_path IN %s", (tuple(files_to_remove),))
                conn.commit()

        # Criar playlist temporária
        temp_playlist_name = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files, play_count, source_folder, is_temp) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                (temp_playlist_name, [], 0, str(folder_path), True)
            )
            conn.commit()

        yield f"data: {json.dumps({'status': 'start', 'total': len(files_to_process), 'temp_playlist': temp_playlist_name})}\n\n"
        for i, file in enumerate(files_to_process, 1):
            try:
                hash_id = calculate_hash(file)
                stats = os.stat(file)
                media_item = None
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT file_path, duration_seconds, size_bytes, created_at, modified_at, video_codec, resolution, orientation, view_count, last_viewed_at, is_favorite FROM endoflix_files WHERE file_path = %s AND size_bytes = %s",
                        (str(file), stats.st_size)
                    )
                    result = cur.fetchone()
                if result:
                    # Arquivo já indexado, usar dados do DB
                    file_data = {
                        "hash_id": hash_id,
                        "file_path": result[0],
                        "duration_seconds": result[1],
                        "size_bytes": result[2],
                        "created_at": result[3],
                        "modified_at": result[4],
                        "video_codec": result[5],
                        "resolution": result[6],
                        "orientation": result[7],
                        "view_count": result[8],
                        "last_viewed_at": result[9],
                        "is_favorite": result[10]
                    }
                    media_item = {"path": file_data["file_path"], "duration": file_data["duration_seconds"]}
                    yield f"data: {json.dumps({'status': 'skipped', 'file': media_item, 'progress': i, 'total': len(files_to_process), 'message': 'Arquivo já indexado'})}\n\n"
                else:
                    # Verificar se é um arquivo movido (mesmo hash, outro caminho)
                    with conn.cursor() as cur:
                        cur.execute("SELECT file_path FROM endoflix_files WHERE hash_id = %s", (hash_id,))
                        existing = cur.fetchone()
                    if existing and existing[0] != str(file):
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE endoflix_files SET file_path = %s, modified_at = %s WHERE hash_id = %s",
                                (str(file), datetime.fromtimestamp(stats.st_mtime), hash_id)
                            )
                            conn.commit()
                            cur.execute(
                                "SELECT file_path, duration_seconds, size_bytes, created_at, modified_at, video_codec, resolution, orientation, view_count, last_viewed_at, is_favorite FROM endoflix_files WHERE file_path = %s",
                                (str(file),)
                            )
                            result = cur.fetchone()
                        if result:
                            file_data = {
                                "hash_id": hash_id,
                                "file_path": result[0],
                                "duration_seconds": result[1],
                                "size_bytes": result[2],
                                "created_at": result[3],
                                "modified_at": result[4],
                                "video_codec": result[5],
                                "resolution": result[6],
                                "orientation": result[7],
                                "view_count": result[8],
                                "last_viewed_at": result[9],
                                "is_favorite": result[10]
                            }
                            media_item = {"path": file_data["file_path"], "duration": file_data["duration_seconds"]}
                            yield f"data: {json.dumps({'status': 'skipped', 'file': media_item, 'progress': i, 'total': len(files_to_process), 'message': 'Arquivo movido e atualizado'})}\n\n"
                    if not media_item:
                        # Arquivo novo, processar
                        with ProcessPoolExecutor(max_workers=8) as executor:
                            future = executor.submit(process_file, file)
                            file_data = future.result()
                            media_item = {"path": file_data["file_path"], "duration": file_data["duration_seconds"]}
                            index_file(conn, file_data)
                            yield f"data: {json.dumps({'status': 'update', 'file': media_item, 'progress': i, 'total': len(files_to_process)})}\n\n"
                # Adicionar arquivo à playlist temporária
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE endoflix_playlist SET files = array_append(files, %s) WHERE name = %s",
                        (str(file), temp_playlist_name)
                    )
                    conn.commit()
            except Exception as e:
                logging.error(f"Erro ao processar {file}: {e}")
                yield f"data: {json.dumps({'status': 'error', 'file': str(file), 'message': str(e)})}\n\n"
    yield f"data: {json.dumps({'status': 'end', 'total': len(files_to_process), 'temp_playlist': temp_playlist_name})}\n\n"