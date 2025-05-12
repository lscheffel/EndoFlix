from flask import Flask, render_template, request, jsonify, Response
import os
from pathlib import Path
import psycopg2
import logging
from collections import Counter
from datetime import datetime
import hashlib
import subprocess
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

app = Flask(__name__)
TRANSCODE_DIR = Path("transcode")
FFPROBE_PATH = r"C:\Program Files\FFMPEG\bin\ffprobe.exe"

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

# Conexão com o PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname="videos",
            user="postgres",
            password="admin",
            host="localhost",
            port="5432"
        )
        app.logger.debug("Conexão com o banco estabelecida")
        return conn
    except Exception as e:
        app.logger.error(f"Erro ao conectar ao banco: {e}")
        raise

def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_video_metadata(file_path):
    try:
        cmd = [
            FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,duration",
            "-of", "json",
            str(file_path)
        ]
        app.logger.debug(f"Executando comando ffprobe: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        app.logger.debug(f"Saída bruta do ffprobe: {result.stdout}")
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        
        duration = float(video_stream.get("duration", 0))
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        resolution = f"{width}x{height}" if width and height else "unknown"
        orientation = "portrait" if width < height else "landscape" if width > height else "square"
        video_codec = video_stream.get("codec_name", "unknown")
        
        app.logger.info(f"Metadados extraídos para {file_path}: duration={duration}, resolution={resolution}, orientation={orientation}, codec={video_codec}")
        return {
            "duration_seconds": duration,
            "resolution": resolution,
            "orientation": orientation,
            "video_codec": video_codec
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError) as e:
        app.logger.error(f"Erro ao extrair metadados de {file_path} com ffprobe: {e}")
        return {
            "duration_seconds": 0,
            "resolution": "unknown",
            "orientation": "unknown",
            "video_codec": "unknown"
        }

def process_file(file):
    stats = os.stat(file)
    hash_id = calculate_hash(file)
    metadata = get_video_metadata(file)
    return {
        "hash_id": hash_id,
        "file_path": str(file),
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

def index_file(conn, file_data):
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
        app.logger.info(f"Arquivo indexado/atualizado: {file_data['file_path']}")
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao indexar {file_data['file_path']}: {e}")
    finally:
        cur.close()

def get_media_files(folder):
    media = []
    folder_path = Path(folder)
    app.logger.debug(f"Escanando pasta: {folder}")
    if not folder_path.exists() or not folder_path.is_dir():
        app.logger.error(f"Pasta inválida: {folder}")
        return media

    # Listar todos os arquivos de mídia
    files_to_process = []
    for file in folder_path.rglob('*'):
        if file.is_file() and file.suffix.lower() in ['.mp4', '.mkv', '.mov', '.divx', '.webm', '.mpg', '.avi']:
            files_to_process.append(file)

    if not files_to_process:
        app.logger.warning(f"Nenhum arquivo de mídia encontrado na pasta {folder}")
        return media

    # Processar arquivos em paralelo usando ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=8) as executor:  # 8 workers para 8 núcleos
        future_to_file = {executor.submit(process_file, file): file for file in files_to_process}
        for future in as_completed(future_to_file):
            file = future_to_file[future]
            try:
                file_data = future.result()
                media.append({"path": file_data["file_path"], "duration": file_data["duration_seconds"]})
                # Indexar no banco (sequencial para evitar conflitos no PostgreSQL)
                conn = get_db_connection()
                index_file(conn, file_data)
                conn.close()
            except Exception as e:
                app.logger.error(f"Erro ao processar {file}: {e}")

    app.logger.info(f"Encontrados {len(media)} arquivos na pasta {folder}")
    return media

def serve_video_range(input_path):
    range_header = request.headers.get('Range', None)
    app.logger.debug(f"Servindo vídeo: {input_path} com range: {range_header}")
    if not os.path.exists(input_path):
        app.logger.error(f"Arquivo não encontrado: {input_path}")
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    size = os.path.getsize(input_path)
    start, end = 0, size - 1

    if range_header:
        range_match = range_header.replace('bytes=', '').split('-')
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else size - 1
        end = min(end, size - 1)

    content_length = end - start + 1
    with open(input_path, 'rb') as f:
        f.seek(start)
        data = f.read(content_length)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Verificar se o arquivo está na tabela
        cur.execute("SELECT 1 FROM endoflix_files WHERE file_path = %s", (input_path,))
        if not cur.fetchone():
            app.logger.warning(f"Arquivo {input_path} não encontrado em endoflix_files, indexando agora")
            file_data = process_file(input_path)
            index_file(conn, file_data)

        # Incrementar visualizações
        cur.execute(
            "UPDATE endoflix_files SET view_count = view_count + 1, last_viewed_at = CURRENT_TIMESTAMP WHERE file_path = %s",
            (input_path,)
        )
        if cur.rowcount == 0:
            app.logger.error(f"Falha ao atualizar visualizações para {input_path}, arquivo ainda não indexado")
        else:
            app.logger.info(f"Visualização incrementada para {input_path}")
        conn.commit()
    except Exception as e:
        app.logger.error(f"Erro ao atualizar visualizações para {input_path}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

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

@app.route('/scan', methods=['POST'])
def scan():
    folder = request.json.get('folder')
    app.logger.debug(f"Recebido pedido para escanear pasta: {folder}")
    folder_path = Path(folder)
    if folder_path.exists() and folder_path.is_dir():
        files = get_media_files(folder)
        if files:
            app.logger.info(f"Encontrados {len(files)} arquivos na pasta {folder}")
            return jsonify({'files': files})
        else:
            app.logger.warning(f"Nenhum arquivo de vídeo encontrado na pasta {folder}")
            return jsonify({'error': 'Nenhum arquivo de vídeo encontrado'}), 404
    app.logger.error(f"Pasta inválida ou não encontrada: {folder}")
    return jsonify({'error': 'Pasta inválida ou não encontrada'}), 400

@app.route('/playlists', methods=['GET', 'POST'])
def playlists():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
            playlists = {row[0]: {"files": row[1], "play_count": row[2]} for row in cur.fetchall()}
            app.logger.debug(f"Playlists carregadas: {len(playlists)} - Dados: {playlists}")
            return jsonify(playlists)
        elif request.method == 'POST':
            data = request.get_json()
            app.logger.debug(f"Dados recebidos para salvar playlist: {data}")
            name = data.get('name')
            files = data.get('files')
            
            if not name or not isinstance(name, str) or name.strip() == '':
                app.logger.error("Nome da playlist inválido ou não fornecido")
                return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
            if not files or not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                app.logger.error("Lista de arquivos inválida")
                return jsonify({'success': False, 'error': 'Lista de arquivos inválida'}), 400
            if len(files) == 0:
                app.logger.error("Nenhum arquivo fornecido para a playlist")
                return jsonify({'success': False, 'error': 'A playlist deve conter pelo menos um arquivo'}), 400
            
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files, play_count) VALUES (%s, %s, 0) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, play_count = endoflix_playlist.play_count RETURNING id",
                (name.strip(), files)
            )
            conn.commit()
            app.logger.info(f"Playlist '{name}' salva com {len(files)} arquivos")
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao gerenciar playlist: {str(e)}")
        return jsonify({'success': False, 'error': f"Erro ao salvar playlist: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/remove_playlist', methods=['POST'])
def remove_playlist():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        data = request.get_json()
        app.logger.debug(f"Dados recebidos para remover playlist: {data}")
        name = data.get('name')
        
        if not name or not isinstance(name, str) or name.strip() == '':
            app.logger.error("Nome da playlist inválido ou não fornecido")
            return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
        
        cur.execute("DELETE FROM endoflix_playlist WHERE name = %s", (name.strip(),))
        if cur.rowcount > 0:
            conn.commit()
            app.logger.info(f"Playlist '{name}' removida com sucesso")
            return jsonify({'success': True}), 200
        else:
            app.logger.warning(f"Playlist '{name}' não encontrada")
            return jsonify({'success': False, 'error': 'Playlist não encontrada'}), 404
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao remover playlist: {str(e)}")
        return jsonify({'success': False, 'error': f"Erro ao remover playlist: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/sessions', methods=['GET', 'POST'])
def sessions():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, videos FROM endoflix_session")
            sessions = {row[0]: row[1] for row in cur.fetchall()}
            app.logger.debug(f"Sessões carregadas: {len(sessions)} - Dados: {sessions}")
            return jsonify(sessions)
        elif request.method == 'POST':
            data = request.get_json()
            app.logger.debug(f"Dados recebidos para salvar sessão: {data}")
            name = data.get('name')
            videos = data.get('videos')
            
            if not name or not isinstance(name, str) or name.strip() == '':
                app.logger.error("Nome da sessão inválido ou não fornecido")
                return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
            if not videos or not isinstance(videos, list) or not all(isinstance(v, str) for v in videos):
                app.logger.error("Lista de vídeos inválida")
                return jsonify({'success': False, 'error': 'Lista de vídeos inválida'}), 400
            
            cur.execute(
                "INSERT INTO endoflix_session (name, videos) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET videos = EXCLUDED.videos RETURNING id",
                (name.strip(), videos)
            )
            conn.commit()
            app.logger.info(f"Sessão '{name}' salva com {len(videos)} vídeos")
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao gerenciar sessão: {str(e)}")
        return jsonify({'success': False, 'error': f"Erro ao salvar sessão: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/remove_session', methods=['POST'])
def remove_session():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        data = request.get_json()
        app.logger.debug(f"Dados recebidos para remover sessão: {data}")
        name = data.get('name')
        
        if not name or not isinstance(name, str) or name.strip() == '':
            app.logger.error("Nome da sessão inválido ou não fornecido")
            return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
        
        cur.execute("DELETE FROM endoflix_session WHERE name = %s", (name.strip(),))
        if cur.rowcount > 0:
            conn.commit()
            app.logger.info(f"Sessão '{name}' removida com sucesso")
            return jsonify({'success': True}), 200
        else:
            app.logger.warning(f"Sessão '{name}' não encontrada")
            return jsonify({'success': False, 'error': 'Sessão não encontrada'}), 404
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao remover sessão: {str(e)}")
        return jsonify({'success': False, 'error': f"Erro ao remover sessão: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/keymaps')
def keymaps():
    return render_template('keymaps.html')

@app.route('/favorites', methods=['GET', 'POST', 'DELETE'])
def favorites():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT file_path FROM endoflix_files WHERE is_favorite = TRUE")
            favorites = [row[0] for row in cur.fetchall()]
            app.logger.debug(f"Favoritos carregados: {len(favorites)}")
            return jsonify(favorites)
        elif request.method == 'POST':
            data = request.get_json()
            file_path = data.get('file_path')
            if not file_path or not isinstance(file_path, str):
                app.logger.error("Caminho do arquivo inválido")
                return jsonify({'success': False, 'error': 'Caminho do arquivo é obrigatório'}), 400
            cur.execute(
                "UPDATE endoflix_files SET is_favorite = TRUE WHERE file_path = %s",
                (file_path,)
            )
            conn.commit()
            app.logger.info(f"Favorito adicionado: {file_path}")
            return jsonify({'success': True})
        elif request.method == 'DELETE':
            data = request.get_json()
            file_path = data.get('file_path')
            if not file_path or not isinstance(file_path, str):
                app.logger.error("Caminho do arquivo inválido")
                return jsonify({'success': False, 'error': 'Caminho do arquivo é obrigatório'}), 400
            cur.execute(
                "UPDATE endoflix_files SET is_favorite = FALSE WHERE file_path = %s",
                (file_path,)
            )
            conn.commit()
            app.logger.info(f"Favorito removido: {file_path}")
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Erro ao gerenciar favoritos: {str(e)}")
        return jsonify({'success': False, 'error': f"Erro ao gerenciar favoritos: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/stats', methods=['GET'])
def stats():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM endoflix_files")
        video_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
        playlist_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM endoflix_session")
        session_count = cur.fetchone()[0]
        app.logger.debug(f"Estatísticas: {video_count} vídeos, {playlist_count} playlists, {session_count} sessões")
        return jsonify({
            'videos': video_count,
            'playlists': playlist_count,
            'sessions': session_count
        })
    except Exception as e:
        app.logger.error(f"Erro ao obter estatísticas: {str(e)}")
        return jsonify({'error': f"Erro ao obter estatísticas: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/analytics', methods=['GET'])
def analytics():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Estatísticas gerais
        cur.execute("SELECT COUNT(*) FROM endoflix_files")
        video_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
        playlist_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_session")
        session_count = cur.fetchone()[0] or 0

        # Playlists com play_count
        cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
        playlists = [{"name": row[0], "files": row[1], "play_count": row[2]} for row in cur.fetchall()]

        # Vídeos mais reproduzidos
        cur.execute("SELECT file_path, view_count FROM endoflix_files ORDER BY view_count DESC LIMIT 10")
        top_videos = [{"path": row[0], "play_count": row[1]} for row in cur.fetchall()]

        # Distribuição por tipo de arquivo
        cur.execute("SELECT file_path FROM endoflix_files")
        file_types = Counter()
        for row in cur.fetchall():
            ext = Path(row[0]).suffix.lower()
            file_types[ext] += 1

        # Sessões com timestamps
        cur.execute("SELECT name, videos FROM endoflix_session")
        sessions = []
        for row in cur.fetchall():
            name_parts = row[0].split('_')[0].split('-')
            if len(name_parts) >= 5:
                try:
                    timestamp_str = '-'.join(name_parts[:5])
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H-%M-%S')
                    sessions.append({
                        "name": row[0],
                        "videos": row[1],
                        "timestamp": timestamp
                    })
                except ValueError as e:
                    app.logger.warning(f"Erro ao parsear timestamp para {row[0]}: {e}")
                    sessions.append({
                        "name": row[0],
                        "videos": row[1],
                        "timestamp": datetime.now()
                    })
            else:
                sessions.append({
                    "name": row[0],
                    "videos": row[1],
                    "timestamp": datetime.now()
                })

        # Uso de players em sessões
        player_usage = [0, 0, 0, 0]
        for session in sessions:
            for i, video in enumerate(session["videos"][:4]):
                if video:
                    player_usage[i] += 1

        return jsonify({
            'stats': {
                'videos': video_count,
                'playlists': playlist_count,
                'sessions': session_count
            },
            'playlists': playlists,
            'top_videos': top_videos,
            'file_types': dict(file_types),
            'sessions': [
                {
                    "name": s["name"],
                    "videos": s["videos"],
                    "timestamp": s["timestamp"].isoformat()
                } for s in sessions
            ],
            'player_usage': player_usage
        })
    except Exception as e:
        app.logger.error(f"Erro ao obter análises: {str(e)}")
        return jsonify({'error': f"Erro ao obter análises: {str(e)}"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/video/<path:filename>')
def serve_video(filename):
    input_path = Path(filename).as_posix()
    return serve_video_range(input_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)