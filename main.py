from flask import Flask, render_template, request, jsonify, Response
import os
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

app = Flask(__name__)
TRANSCODE_DIR = Path("transcode")
FFPROBE_PATH = r"C:\Program Files\FFMPEG\bin\ffprobe.exe"
REDIS_SERVER_PATH = r"C:\Program Files\Redis\redis-server.exe"
REDIS_CLIENT = None
REDIS_PROCESS = None
DB_POOL = psycopg2.pool.SimpleConnectionPool(1, 20, dbname="videos", user="postgres", password="admin", host="localhost", port="5432")

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

    if not os.path.exists(REDIS_SERVER_PATH):
        logging.error(f"Arquivo redis-server.exe não encontrado em {REDIS_SERVER_PATH}")
        return

    try:
        REDIS_PROCESS = subprocess.Popen(
            [REDIS_SERVER_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(2)
        if REDIS_PROCESS.poll() is not None:
            logging.error("Falha ao iniciar o Redis: processo terminou inesperadamente")
            return
        logging.info("Servidor Redis iniciado com sucesso")
    except Exception as e:
        logging.error(f"Erro ao iniciar o Redis: {e}")

def init_redis(max_retries=3, retry_delay=2):
    global REDIS_CLIENT
    for attempt in range(max_retries):
        try:
            REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0)
            REDIS_CLIENT.ping()
            logging.info("Conexão com Redis estabelecida")
            return True
        except redis.ConnectionError as e:
            logging.warning(f"Tentativa {attempt + 1}/{max_retries} de conexão ao Redis falhou: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    logging.warning("Não foi possível conectar ao Redis. Usando fallback sem cache.")
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
    signal.signal(signal.SIGINT, signal_handler)

def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_video_metadata(file_path):
    file_path_str = str(file_path)
    if REDIS_CLIENT:
        try:
            cached = REDIS_CLIENT.get(f"metadata:{file_path_str}")
            if cached:
                return json.loads(cached)
        except redis.RedisError as e:
            logging.error(f"Erro ao acessar Redis para {file_path_str}: {e}")

    conn = DB_POOL.getconn()
    cur = conn.cursor()
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
            if REDIS_CLIENT:
                try:
                    REDIS_CLIENT.setex(f"metadata:{file_path_str}", 86400, json.dumps(metadata))
                except redis.RedisError as e:
                    logging.error(f"Erro ao salvar no Redis para {file_path_str}: {e}")
            return metadata
    except Exception as e:
        logging.error(f"Erro ao consultar metadados no banco para {file_path_str}: {e}")
    finally:
        cur.close()
        DB_POOL.putconn(conn)

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
        if REDIS_CLIENT:
            try:
                REDIS_CLIENT.setex(f"metadata:{file_path_str}", 86400, json.dumps(result))
            except redis.RedisError as e:
                logging.error(f"Erro ao salvar no Redis para {file_path_str}: {e}")
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
        "created_at": datetime.fromtimestamp(stats.st_ctime),
        "modified_at": datetime.fromtimestamp(stats.st_mtime),
        "duration_seconds": metadata["duration_seconds"],
        "resolution": metadata["resolution"],
        "orientation": metadata["orientation"],
        "video_codec": metadata["video_codec"],
        "view_count": 0,
        "last_viewed_at": None,
        "is_favorite": False
    }

def check_existing_hash(conn, hash_id, file_path):
    cur = conn.cursor()
    try:
        file_path_str = str(file_path)
        filename = os.path.basename(file_path_str)
        stats = os.stat(file_path)
        size_bytes = stats.st_size
        # Verifica se existe na mesma pasta com mesmo nome e tamanho
        cur.execute(
            "SELECT file_path FROM endoflix_files WHERE file_path = %s AND size_bytes = %s",
            (file_path_str, size_bytes)
        )
        if cur.fetchone():
            return True  # Arquivo idêntico na mesma pasta, pular reindexação
        # Verifica se o hash existe em outra pasta (arquivo movido)
        cur.execute(
            "SELECT file_path FROM endoflix_files WHERE hash_id = %s",
            (hash_id,)
        )
        result = cur.fetchone()
        if result:
            existing_path = result[0]
            if existing_path != file_path_str:
                # Atualiza caminho para arquivo movido
                cur.execute(
                    "UPDATE endoflix_files SET file_path = %s, modified_at = %s WHERE hash_id = %s",
                    (file_path_str, datetime.fromtimestamp(stats.st_mtime), hash_id)
                )
                conn.commit()
            return True
        return False  # Arquivo novo
    except Exception as e:
        logging.error(f"Erro ao verificar hash de {file_path_str}: {e}")
        return False
    finally:
        cur.close()

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

    conn = DB_POOL.getconn()
    cur = conn.cursor()
    # Obter arquivos atualmente indexados para a pasta
    cur.execute("SELECT file_path FROM endoflix_files WHERE file_path LIKE %s", (f"{str(folder_path)}%",))
    db_files = {row[0] for row in cur.fetchall()}
    cur.close()

    current_files = {str(file) for file in files_to_process}
    # Arquivos para remover do DB (não estão mais na pasta)
    files_to_remove = db_files - current_files
    if files_to_remove:
        cur = conn.cursor()
        cur.execute("DELETE FROM endoflix_files WHERE file_path IN %s", (tuple(files_to_remove),))
        conn.commit()
        cur.close()

    # Criar playlist temporária
    temp_playlist_name = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO endoflix_playlist (name, files, play_count, source_folder, is_temp) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
        (temp_playlist_name, [], 0, str(folder_path), True)
    )
    conn.commit()
    cur.close()

    yield f"data: {json.dumps({'status': 'start', 'total': len(files_to_process), 'temp_playlist': temp_playlist_name})}\n\n"
    for i, file in enumerate(files_to_process, 1):
        try:
            hash_id = calculate_hash(file)
            stats = os.stat(file)
            media_item = None
            cur = conn.cursor()
            cur.execute(
                "SELECT file_path, duration_seconds, size_bytes, created_at, modified_at, video_codec, resolution, orientation, view_count, last_viewed_at, is_favorite FROM endoflix_files WHERE file_path = %s AND size_bytes = %s",
                (str(file), stats.st_size)
            )
            result = cur.fetchone()
            cur.close()
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
                cur = conn.cursor()
                cur.execute("SELECT file_path FROM endoflix_files WHERE hash_id = %s", (hash_id,))
                existing = cur.fetchone()
                if existing and existing[0] != str(file):
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
                cur.close()
                if not media_item:
                    # Arquivo novo, processar
                    with ProcessPoolExecutor(max_workers=8) as executor:
                        future = executor.submit(process_file, file)
                        file_data = future.result()
                        media_item = {"path": file_data["file_path"], "duration": file_data["duration_seconds"]}
                        index_file(conn, file_data)
                        yield f"data: {json.dumps({'status': 'update', 'file': media_item, 'progress': i, 'total': len(files_to_process)})}\n\n"
            # Adicionar arquivo à playlist temporária
            cur = conn.cursor()
            cur.execute(
                "UPDATE endoflix_playlist SET files = array_append(files, %s) WHERE name = %s",
                (str(file), temp_playlist_name)
            )
            conn.commit()
            cur.close()
        except Exception as e:
            logging.error(f"Erro ao processar {file}: {e}")
            yield f"data: {json.dumps({'status': 'error', 'file': str(file), 'message': str(e)})}\n\n"
    DB_POOL.putconn(conn)
    yield f"data: {json.dumps({'status': 'end', 'total': len(files_to_process), 'temp_playlist': temp_playlist_name})}\n\n"

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
            file_data = process_file(input_path_str)
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

@app.route('/scan', methods=['POST', 'GET'])
def scan():
    if request.method == 'POST':
        folder = request.json.get('folder')
        folder_path = Path(folder)
        if not folder_path.exists() or not folder_path.is_dir():
            return jsonify({'error': 'Pasta inválida ou não encontrada'}), 400
        return Response(get_media_files(folder), mimetype='text/event-stream')
    elif request.method == 'GET':
        folder = request.args.get('folder')
        if not folder:
            return jsonify({'error': 'Parâmetro folder é obrigatório'}), 400
        return Response(get_media_files(folder), mimetype='text/event-stream')

@app.route('/playlists', methods=['GET', 'POST'])
def playlists():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, files, play_count, source_folder FROM endoflix_playlist WHERE is_temp = FALSE")
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

@app.route('/save_temp_playlist', methods=['POST'])
def save_temp_playlist():
    conn = DB_POOL.getconn()
    cur = conn.cursor()
    try:
        data = request.get_json()
        temp_name = data.get('temp_name')
        new_name = data.get('new_name')
        if not temp_name or not new_name or not isinstance(new_name, str) or new_name.strip() == '':
            return jsonify({'success': False, 'error': 'Nomes de playlist inválidos'}), 400
        
        cur.execute("SELECT files, source_folder FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_name,))
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Playlist temporária não encontrada'}), 404
        
        files, source_folder = result
        cur.execute(
            "INSERT INTO endoflix_playlist (name, files, play_count, source_folder, is_temp) VALUES (%s, %s, %s, %s, %s)",
            (new_name.strip(), files, 0, source_folder, False)
        )
        # Opcional: remover playlist temporária após salvar
        cur.execute("DELETE FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_name,))
        conn.commit()
        logging.info(f"Playlist {new_name} salva a partir de {temp_name}")
        return jsonify({'success': True, 'name': new_name, 'files': files})
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao salvar playlist: {str(e)}")
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
    data = request.get_json()
    name = data.get('name')
    source_folder = data.get('source_folder')
    temp_playlist = data.get('temp_playlist')

    if not name or not source_folder:
        return jsonify({'success': False, 'error': 'Nome da playlist e pasta são obrigatórios'}), 400

    conn = DB_POOL.getconn()
    try:
        cur = conn.cursor()
        # Verificar se a playlist existe
        cur.execute("SELECT files, source_folder FROM endoflix_playlist WHERE name = %s AND is_temp = FALSE", (name,))
        playlist = cur.fetchone()
        if not playlist:
            return jsonify({'success': False, 'error': 'Playlist não encontrada'}), 404

        # Obter arquivos atuais da pasta via get_media_files
        updated_files = []
        for event in get_media_files(source_folder):  # Iteração síncrona
            data = json.loads(event.replace('data: ', ''))
            if data['status'] in ['skipped', 'update']:
                updated_files.append(data['file']['path'])
            elif data['status'] == 'error':
                logging.error(f"Erro ao processar arquivo: {data['message']}")

        # Se temp_playlist fornecida, incorporar seus arquivos
        if temp_playlist:
            cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_playlist,))
            temp_result = cur.fetchone()
            if temp_result:
                updated_files.extend(temp_result[0])
                # Remover playlist temporária após uso
                cur.execute("DELETE FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_playlist,))
                conn.commit()

        # Sanitizar: remover duplicatas e arquivos inexistentes
        updated_files = list(dict.fromkeys(updated_files))  # Remove duplicatas
        valid_files = [f for f in updated_files if Path(f).exists()]

        # Atualizar playlist no banco
        cur.execute(
            "UPDATE endoflix_playlist SET files = %s, source_folder = %s WHERE name = %s AND is_temp = FALSE",
            (valid_files, source_folder, name)
        )
        conn.commit()
        return jsonify({'success': True, 'files': valid_files})
    except Exception as e:
        logging.error(f"Erro ao atualizar playlist: {e}")
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
    return serve_video_range(Path(filename))

def ensure_snapshots_dir(video_path):
    video_dir = os.path.dirname(video_path)
    snapshots_dir = os.path.join(video_dir, 'snapshots')
    if not os.path.exists(snapshots_dir):
        os.makedirs(snapshots_dir)
    return snapshots_dir

def save_snapshot_worker(snapshot_queue):
    while True:
        try:
            data = snapshot_queue.get()
            if data is None:
                break

            video_path = data['video_path']
            image_data = data['image_data']
            is_burst = data['is_burst']
            burst_index = data['burst_index']

            # Remove o prefixo da URL do vídeo
            video_path = video_path.replace('/video/', '')
            video_path = os.path.normpath(video_path)

            # Cria a pasta snapshots se não existir
            snapshots_dir = ensure_snapshots_dir(video_path)
            
            # Gera o nome do arquivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if is_burst:
                filename = f'burst_{timestamp}_{burst_index}.webp'
            else:
                filename = f'snapshot_{timestamp}.webp'
            
            # Salva a imagem
            file_path = os.path.join(snapshots_dir, filename)
            image_data = base64.b64decode(image_data.split(',')[1])
            with open(file_path, 'wb') as f:
                f.write(image_data)

            snapshot_queue.task_done()
        except Exception as e:
            logging.error(f"Erro no worker de snapshot: {str(e)}")
            snapshot_queue.task_done()
snapshot_queue = Queue()
snapshot_workers = []
for _ in range(6):
    worker = threading.Thread(target=save_snapshot_worker, args=(snapshot_queue,))
    worker.daemon = True
    worker.start()
    snapshot_workers.append(worker)

@app.route('/save_snapshot', methods=['POST'])
def save_snapshot():
    try:
        data = request.get_json()
        video_path = data.get('video_path')
        frames = data.get('frames', [])
        image_data = data.get('image_data')
        is_burst = data.get('is_burst', False)

        if not video_path or (not frames and not image_data):
            return jsonify({'success': False, 'error': 'Dados inválidos'}), 400

        # Remove o prefixo da URL do vídeo
        video_path = video_path.replace('/video/', '')
        video_path = os.path.normpath(video_path)

        # Cria a pasta snapshots se não existir
        snapshots_dir = ensure_snapshots_dir(video_path)
        
        # Gera o timestamp base
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if frames:  # Processamento em lote para burst
            for i, frame_data in enumerate(frames, 1):
                filename = f'burst_{timestamp}_{i}.webp'
                file_path = os.path.join(snapshots_dir, filename)
                image_data = base64.b64decode(frame_data.split(',')[1])
                with open(file_path, 'wb') as f:
                    f.write(image_data)
        else:  # Processamento de snapshot único
            filename = f'snapshot_{timestamp}.webp'
            file_path = os.path.join(snapshots_dir, filename)
            image_data = base64.b64decode(image_data.split(',')[1])
            with open(file_path, 'wb') as f:
                f.write(image_data)

        return jsonify({
            'success': True,
            'message': 'Snapshot(s) salvo(s) com sucesso'
        })
    except Exception as e:
        logging.error(f"Erro ao processar snapshot: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def cleanup_snapshot_workers():
    for _ in range(len(snapshot_workers)):
        snapshot_queue.put(None)
    for worker in snapshot_workers:
        worker.join()

if __name__ == '__main__':
    start_redis()
    init_redis()
    try:
        app.run(port=5000)
    finally:
        cleanup_snapshot_workers()
        shutdown_redis()
        DB_POOL.closeall()