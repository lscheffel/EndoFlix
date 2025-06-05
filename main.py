from flask import Flask, render_template, request, jsonify, Response, make_response, stream_with_context, Response as FlaskResponse
import os
import tempfile
from pathlib import Path
import psycopg2.pool
import logging
from collections import Counter
from datetime import datetime
import hashlib
import subprocess
import json
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
import redis
import time
import signal
import sys
import base64
import threading
from queue import Queue

app = Flask(__name__, template_folder='Templates')
TRANSCODE_DIR = Path("transcode")
FFPROBE_PATH = r"C:\\Program Files\\FFMPEG\\bin\\ffprobe.exe"
REDIS_SERVER_PATH = r"C:\\Program Files\\Redis\\redis-server.exe"
REDIS_CLIENT = None
REDIS_PROCESS = None

HTML5_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.divx', '.webm', '.mpg', '.avi', '.ogg', '.ogv'}
HTML5_CODECS = {'h264', 'vp8', 'vp9'}

DB_POOL = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    dbname="videos",
    user="postgres",
    password="admin",
    host="localhost",
    port="5432",
    options="-c statement_timeout=30000"
)

logging.basicConfig(level=logging.INFO)

def start_redis():
    global REDIS_PROCESS
    try:
        temp_client = redis.Redis(host='localhost', port=6379, db=0)
        temp_client.ping()
        logging.info("Redis já está rodando em localhost:6379")
        return
    except redis.ConnectionError:
        pass
    logging.warning("Redis server não encontrado. Cache Redis desativado.")
    return

def init_redis(max_retries=3, retry_delay=2):
    global REDIS_CLIENT
    for attempt in range(max_retries):
        try:
            REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=5)
            REDIS_CLIENT.ping()
            logging.info("Conexão com Redis estabelecida")
            return True
        except redis.ConnectionError as e:
            logging.warning(f"Tentativa {attempt + 1}/{max_retries} de conexão ao Redis falhou: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    logging.warning("Não foi possível conectar ao Redis. Cache desativado.")
    REDIS_CLIENT = None
    return False

def shutdown_redis():
    global REDIS_PROCESS
    if REDIS_PROCESS:
        try:
            REDIS_PROCESS.terminate()
            REDIS_PROCESS.wait(timeout=5)
            logging.info("Servidor Redis encerrado")
        except Exception as e:
            logging.error(f"Erro ao encerrar o Redis: {e}")

def signal_handler(sig, frame):
    logging.info("Encerrando o EndoFlix...")
    shutdown_redis()
    DB_POOL.closeall()
    sys.exit(0)

def setup_signal_handlers():
    if not app.testing:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

setup_signal_handlers()

def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def sync_directory_with_db(folder_path: Path, conn):
    existing_files = {}
    cur = conn.cursor()
    try:
        cur.execute("SELECT hash_id, file_path, modified_at FROM endoflix_files WHERE file_path LIKE %s", (str(folder_path) + '%',))
        for row in cur.fetchall():
            existing_files[Path(row[1]).resolve().as_posix()] = {'hash_id': row[0], 'modified_at': row[2]}
    except Exception as e:
        logging.error(f"[SYNC] Erro ao buscar arquivos existentes: {e}")
        return []
    finally:
        cur.close()

    found_files = list(folder_path.rglob('*'))
    all_files = []
    with ThreadPoolExecutor() as executor:
        future_to_file = {
            executor.submit(process_file, file): file 
            for file in found_files 
            if file.is_file() and file.suffix.lower() in HTML5_EXTENSIONS
            and Path(file).resolve().as_posix() not in existing_files  # Evita duplicatas
        }
        for future in as_completed(future_to_file):
            file = future_to_file[future]
            try:
                file_data = future.result()
                if file_data:
                    all_files.append(file_data["file_path"])
                    previous = existing_files.get(Path(file).resolve().as_posix())
                    if not previous:
                        index_file(conn, file_data)
                        logging.info(f"[SYNC] Novo arquivo indexado: {file}")
                    else:
                        mtime = datetime.fromtimestamp(file.stat().st_mtime)
                        if mtime != previous['modified_at']:
                            index_file(conn, file_data)
                            logging.info(f"[SYNC] Arquivo atualizado: {file}")
            except Exception as e:
                logging.warning(f"[SYNC] Erro ao processar {file}: {e}")

    indexed_paths = {Path(f).resolve().as_posix() for f in found_files if f.is_file()}
    obsolete = [path for path in existing_files if path not in indexed_paths]
    cur = conn.cursor()
    try:
        for path in obsolete:
            cur.execute("DELETE FROM endoflix_files WHERE file_path = %s", (path,))
            logging.info(f"[SYNC] Arquivo removido do DB: {path}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"[SYNC] Erro ao remover obsoletos: {e}")
    finally:
        cur.close()
    return all_files

@app.route('/playlists', methods=['POST'])
def create_or_update_playlist():
    data = request.get_json()
    name = data.get('name')
    source_folder = data.get('source_folder')

    if not name or not isinstance(name, str) or name.strip() == '':
        return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
    if not source_folder:
        return jsonify({'success': False, 'error': 'Pasta de origem é obrigatória'}), 400

    conn = DB_POOL.getconn()
    try:
        folder_path = Path(source_folder).resolve(strict=True)
        if not folder_path.is_dir():
            raise ValueError("Não é um diretório")
    except Exception as e:
        logging.error(f"[PLAYLIST] Caminho inválido: {source_folder} - {e}")
        return jsonify({'success': False, 'error': f'Caminho inválido: {e}'}), 400

    try:
        all_files = sync_directory_with_db(folder_path, conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, 0, %s) "
            "ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, source_folder = EXCLUDED.source_folder",
            (name.strip(), all_files, str(folder_path))
        )
        conn.commit()
        logging.info(f"[PLAYLIST] Playlist '{name}' atualizada com {len(all_files)} arquivos.")
        return jsonify({'success': True, 'files': all_files})
    except Exception as e:
        conn.rollback()
        logging.error(f"[PLAYLIST] Erro ao criar playlist '{name}': {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        cur.close()
        DB_POOL.putconn(conn)

def get_video_metadata(file):
    file_path_str = str(file)
    if REDIS_CLIENT:
        try:
            cached = REDIS_CLIENT.get(f"metadata:{file_path_str}")
            if cached is not None:
                try:
                    if isinstance(cached, (bytes, bytearray)):
                        return json.loads(cached.decode('utf-8'))
                    elif isinstance(cached, str):
                        return json.loads(cached)
                    logging.warning(f"Tipo desconhecido de cache do Redis para {file_path_str}: {type(cached)}")
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logging.error(f"Erro ao decodificar cache do Redis para {file_path_str}: {e}")
        except redis.RedisError as e:
            logging.error(f"Erro ao ler do Redis para {file_path_str}: {e}")

    try:
        cmd = [FFPROBE_PATH, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,duration", "-of", "json", file_path_str]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
        if metadata is None:
            raise ValueError("Falha ao obter metadados do ffprobe")

        streams = metadata.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        
        video_codec = video_stream.get("codec_name", "unknown")
        if video_codec not in HTML5_CODECS:
            return None  # Ignora arquivos com codecs não suportados
        
        duration = float(video_stream.get("duration", 0))
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        resolution = f"{width}x{height}" if width and height else "unknown"
        orientation = "portrait" if width < height else "landscape" if width > height else "square"
        
        result = {
            "duration_seconds": duration,
            "resolution": resolution,
            "orientation": orientation,
            "video_codec": video_codec
        }
        
        if REDIS_CLIENT:
            try:
                REDIS_CLIENT.setex(f"metadata:{file_path_str}", 86400, json.dumps(result))
            except redis.RedisError as e:
                logging.error(f"Erro ao salvar no Redis para {file_path_str}: {e}")
        return result
    except Exception as e:
        logging.error(f"Erro ao extrair metadados de {file_path_str}: {e}")
        return None

def process_file(file):
    file_path_str = str(file)
    stats = os.stat(file)
    hash_id = calculate_hash(file)
    metadata = get_video_metadata(file)
    
    if not metadata:  # Ignora se metadados inválidos (codec não suportado)
        return None
    
    return {
        "hash_id": hash_id,
        "file_path": file_path_str,
        "size_bytes": stats.st_size,
        "created_at": datetime.fromtimestamp(stats.st_ctime),
        "modified_at": datetime.fromtimestamp(stats.st_mtime),
        "duration_seconds": metadata.get("duration_seconds", 0),
        "resolution": metadata.get("resolution", "unknown"),
        "orientation": metadata.get("orientation", "unknown"),
        "video_codec": metadata.get("video_codec", "unknown"),
        "view_count": 0,
        "last_viewed_at": None,
        "is_favorite": False
    }

def check_existing_hash(conn, hash_id, file_path):
    cur = conn.cursor()
    file_path_str = str(file_path)
    try:
        cur.execute("SELECT file_path FROM endoflix_files WHERE hash_id = %s", (hash_id,))
        result = cur.fetchone()
        if result:
            existing_path = result[0]
            if existing_path != file_path_str:
                cur.execute(
                    "UPDATE endoflix_files SET file_path = %s, modified_at = %s WHERE hash_id = %s",
                    (file_path_str, datetime.fromtimestamp(os.stat(file_path).st_mtime), hash_id)
                )
                conn.commit()
            return True
        return False
    except Exception as e:
        logging.error(f"Erro ao verificar hash de {file_path_str}: {e}")
        return False
    finally:
        cur.close()

def index_file(conn, file_data):
    if not file_data:  # Ignora se file_data é None
        return
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO endoflix_files (hash_id, file_path, size_bytes, created_at, modified_at, video_codec, resolution, orientation, duration_seconds, view_count, last_viewed_at, is_favorite)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash_id) DO UPDATE
            SET file_path = EXCLUDED.file_path,
                size_bytes = EXCLUDED.size_bytes,
                created_at = EXCLUDED.created_at,
                modified_at = EXCLUDED.modified_at,
                video_codec = EXCLUDED.video_codec,
                resolution = EXCLUDED.resolution,
                orientation = EXCLUDED.orientation,
                duration_seconds = EXCLUDED.duration_seconds,
                view_count = EXCLUDED.view_count,
                last_viewed_at = EXCLUDED.last_viewed_at,
                is_favorite = EXCLUDED.is_favorite
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
    try:
        folder_path = Path(folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            yield json.dumps([])
            return
        
        files_to_process = [file for file in folder_path.rglob('*') if file.is_file() and file.suffix.lower() in HTML5_EXTENSIONS]
        files_to_process.sort(key=lambda x: x.name.lower())
        
        yield '['
        for i, file_path in enumerate(files_to_process):
            try:
                metadata = get_video_metadata(file_path)
                if not metadata:  # Ignora arquivos com codecs não suportados
                    continue
                stat = file_path.stat()
                file_info = {
                    'filename': file_path.name,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'type': 'video',
                    'resolution': metadata.get('resolution', 'unknown'),
                    'codec': metadata.get('video_codec', 'unknown')
                }
                json_str = json.dumps(file_info, ensure_ascii=False)
                if i > 0:
                    yield f',{json_str}'
                else:
                    yield json_str
            except Exception as e:
                logging.error(f"Erro ao processar arquivo {file_path}: {str(e)}")
                continue
        yield ']'
    except Exception as e:
        logging.error(f"Erro ao obter arquivos de mídia: {str(e)}")
        yield json.dumps([])

def serve_video_range(input_path):
    input_path_str = str(input_path)
    if not os.path.exists(input_path_str):
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    size = os.path.getsize(input_path_str)
    start, end = 0, size - 1
    range_header = request.headers.get('Range')
    if range_header:
        range_match = range_header.replace('bytes=', '').split('-')
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else size - 1
        end = min(end, size - 1)

    content_length = end - start + 1
    with open(input_path_str, 'rb') as f:
        f.seek(start)
        data = f.read(content_length)

    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM endoflix_files WHERE file_path = %s", (input_path_str,))
        if not cur.fetchone():
            file_data = process_file(input_path)
            index_file(conn, file_data)
        cur.execute("UPDATE endoflix_files SET view_count = view_count + 1, last_viewed_at = CURRENT_TIMESTAMP WHERE file_path = %s", (input_path_str,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao atualizar visualizações para {input_path_str}: {e}")
    finally:
        cur.close()
        DB_POOL.putconn(conn)

    return Response(
        data,
        status=206 if range_header else 200,
        mimetype='video/mp4',
        headers={
            'Content-Range': f'bytes {start}-{end}/{size}',
            'Accept-Ranges': 'bytes',
            'Content-Length': str(content_length)
        }
    )

@app.route('/')
def index():
    return render_template('base.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ultra')
def ultra():
    return render_template('ultra.html')

@app.route('/scan', methods=['GET', 'POST'])
def scan():
    try:
        # Get folder path from query parameter (GET) or JSON body (POST)
        if request.method == 'GET':
            folder = request.args.get('folder')
        else:  # POST
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Dados JSON inválidos'}), 400
            folder = data.get('folder')

        if not folder:
            return jsonify({'error': 'Parâmetro folder é obrigatório'}), 400
        
        folder_path = Path(folder).resolve(strict=True)
        if not folder_path.exists() or not folder_path.is_dir():
            return jsonify({'error': 'Pasta inválida'}), 400
        
        conn = DB_POOL.getconn()
        try:
            files = sync_directory_with_db(folder_path, conn)
            return jsonify({'success': True, 'files': files})
        finally:
            DB_POOL.putconn(conn)
    except Exception as e:
        logging.error(f"[SCAN] Erro ao escanear pasta {folder}: {e}")
        return jsonify({'error': f'Erro ao escanear pasta: {e}'}), 500

@app.route('/playlists', methods=['GET', 'POST'])
def playlists():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, files, play_count, source_folder FROM endoflix_playlist")
            playlists = {row[0]: {"files": row[1], "play_count": row[2], "source_folder": row[3]} for row in cur.fetchall()}
            return jsonify(playlists)
        else:
            data = request.get_json()
            name = data.get('name')
            files = data.get('files')
            source_folder = data.get('source_folder')
            if not name or not isinstance(name, str) or name.strip() == '':
                return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
            if not files or not isinstance(files, list) or not all(isinstance(f, str) for f in files) or len(files) == 0:
                return jsonify({'success': False, 'error': 'Lista de arquivos inválida'}), 400
            if not source_folder or not isinstance(source_folder, str) or not Path(source_folder).exists():
                return jsonify({'success': False, 'error': 'Pasta de origem inválida'}), 400
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, 0, %s) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, play_count = endoflix_playlist.play_count, source_folder = EXCLUDED.source_folder RETURNING id",
                (name.strip(), files, source_folder)
            )
            conn.commit()
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao gerenciar playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/remove_playlist', methods=['POST'])
def remove_playlist():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        data = request.get_json()
        name = data.get('name')
        if not name or not isinstance(name, str) or name.strip() == '':
            return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
        cur.execute("DELETE FROM endoflix_playlist WHERE name = %s", (name.strip(),))
        if cur.rowcount > 0:
            conn.commit()
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'error': 'Playlist não encontrada'}), 404
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao remover playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/update_playlist', methods=['POST'])
def update_playlist():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        data = request.get_json()
        name = data.get('name')
        if not name or not isinstance(name, str) or name.strip() == '':
            return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
        
        cur.execute("SELECT source_folder FROM endoflix_playlist WHERE name = %s", (name.strip(),))
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Playlist não encontrada'}), 404
        
        source_folder = result[0]
        if not source_folder or not Path(source_folder).exists():
            return jsonify({'success': False, 'error': 'Pasta de origem inválida ou não especificada'}), 400

        folder_path = Path(source_folder)
        updated_files = sync_directory_with_db(folder_path, conn)

        cur.execute(
            "UPDATE endoflix_playlist SET files = %s WHERE name = %s",
            (updated_files, name.strip())
        )
        conn.commit()
        return jsonify({'success': True, 'files': updated_files})
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao atualizar playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/sessions', methods=['GET', 'POST'])
def sessions():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, videos FROM endoflix_session")
            sessions = {row[0]: row[1] for row in cur.fetchall()}
            return jsonify(sessions)
        else:
            data = request.get_json()
            name = data.get('name')
            videos = data.get('videos')
            if not name or not isinstance(name, str) or name.strip() == '':
                return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
            if not videos or not isinstance(videos, list) or not all(isinstance(v, str) or v is None for v in videos):
                return jsonify({'success': False, 'error': 'Lista de vídeos inválida'}), 400
            cur.execute(
                "INSERT INTO endoflix_session (name, videos) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET videos = EXCLUDED.videos RETURNING id",
                (name.strip(), videos)
            )
            conn.commit()
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao gerenciar sessão: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/remove_session', methods=['POST'])
def remove_session():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        data = request.get_json()
        name = data.get('name')
        if not name or not isinstance(name, str) or name.strip() == '':
            return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
        cur.execute("DELETE FROM endoflix_session WHERE name = %s", (name.strip(),))
        if cur.rowcount > 0:
            conn.commit()
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'error': 'Sessão não encontrada'}), 404
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao remover sessão: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/keymaps')
def keymaps():
    return render_template('keymaps.html')

@app.route('/favorites', methods=['GET', 'POST', 'DELETE'])
def favorites():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT file_path FROM endoflix_files WHERE is_favorite = TRUE")
            favorites = [row[0] for row in cur.fetchall()]
            return jsonify(favorites)
        elif request.method == 'POST':
            data = request.get_json()
            file_path = data.get('file_path')
            if not file_path or not isinstance(file_path, str):
                return jsonify({'success': False, 'error': 'Caminho do arquivo é obrigatório'}), 400
            cur.execute("UPDATE endoflix_files SET is_favorite = TRUE WHERE file_path = %s", (file_path,))
            conn.commit()
            return jsonify({'success': True})
        else:
            data = request.get_json()
            file_path = data.get('file_path')
            if not file_path or not isinstance(file_path, str):
                return jsonify({'success': False, 'error': 'Caminho do arquivo é obrigatório'}), 400
            cur.execute("UPDATE endoflix_files SET is_favorite = FALSE WHERE file_path = %s", (file_path,))
            conn.commit()
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao gerenciar favoritos: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/stats', methods=['GET'])
def stats():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM endoflix_files")
        video_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
        playlist_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM endoflix_session")
        session_count = cur.fetchone()[0]
        return jsonify({'videos': video_count, 'playlists': playlist_count, 'sessions': session_count})
    except Exception as e:
        logging.error(f"Erro ao obter estatísticas: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/analytics', methods=['GET'])
def analytics():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM endoflix_files")
        video_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
        playlist_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_session")
        session_count = cur.fetchone()[0] or 0

        cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
        playlists = [{"name": row[0], "files": row[1], "play_count": row[2]} for row in cur.fetchall()]

        cur.execute("SELECT file_path, view_count, is_favorite FROM endoflix_files ORDER BY view_count DESC LIMIT 10")
        top_videos = [{"path": row[0], "play_count": row[1], "favorited": row[2]} for row in cur.fetchall()]

        cur.execute("SELECT file_path FROM endoflix_files")
        file_types = Counter()
        for row in cur.fetchall():
            ext = Path(row[0]).suffix.lower()
            file_types[ext] += 1

        cur.execute("SELECT name, videos FROM endoflix_session")
        sessions = []
        for row in cur.fetchall():
            name_parts = row[0].split('_')[0].split('-')
            try:
                timestamp = datetime.strptime('-'.join(name_parts[:5]), '%Y-%m-%dT%H-%M-%S') if len(name_parts) >= 5 else datetime.now()
            except ValueError:
                timestamp = datetime.now()
            sessions.append({"name": row[0], "videos": row[1], "timestamp": timestamp})

        player_usage = [0, 0, 0, 0]
        for session in sessions:
            for i, video in enumerate(session["videos"][:4]):
                if video:
                    player_usage[i] += 1

        return jsonify({
            'stats': {'videos': video_count, 'playlists': playlist_count, 'sessions': session_count},
            'playlists': playlists,
            'top_videos': top_videos,
            'file_types': dict(file_types),
            'sessions': [{'name': s["name"], 'videos': s["videos"], 'timestamp': s["timestamp"].isoformat()} for s in sessions],
            'player_usage': player_usage
        })
    except Exception as e:
        logging.error(f"Erro ao obter análises: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        DB_POOL.putconn(conn)

@app.route('/video/<path:filename>')
def serve_video(filename):
    try:
        if isinstance(filename, bytes):
            file_path = filename.decode('utf-8')
        else:
            file_path = filename
        return serve_video_range(Path(file_path))
    except Exception as e:
        logging.error(f"Erro ao processar caminho do vídeo: {e}")
        return jsonify({'error': 'Caminho do vídeo inválido', 'original_error': str(e)}), 400

if __name__ == '__main__':
    logging.info("Iniciando o EndoFlix...")
    try:
        init_redis()
        conn = DB_POOL.getconn()
        if conn:
            logging.info("Conexão com o banco de dados PostgreSQL estabelecida")
            DB_POOL.putconn(conn)
        else:
            logging.error("Falha ao obter conexão do pool de conexões")
        app.run(debug=True, threaded=True)
    except Exception as e:
        logging.error(f"Erro fatal ao iniciar o aplicativo: {e}", exc_info=True)
        sys.exit(1)