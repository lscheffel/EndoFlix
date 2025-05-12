from flask import Flask, render_template, request, jsonify, Response
import os
from pathlib import Path
import psycopg2
import logging
from collections import Counter
from datetime import datetime

app = Flask(__name__)
TRANSCODE_DIR = Path("transcode")

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

def get_media_files(folder):
    media = []
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        app.logger.error(f"Pasta inválida: {folder}")
        return media
    for file in folder_path.rglob('*'):
        if file.is_file() and file.suffix.lower() in ['.mp4', '.mkv', '.mov', '.divx', '.webm', '.mpg', '.avi']:
            media.append({"path": str(file), "duration": os.path.getsize(file) % 1000})
            app.logger.debug(f"Arquivo encontrado: {file}")
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
        cur.execute(
            "UPDATE endoflix_playlist SET play_count = play_count + 1 WHERE %s = ANY(files)",
            (input_path,)
        )
        conn.commit()
    except Exception as e:
        app.logger.error(f"Erro ao atualizar play_count: {e}")
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
            cur.execute("SELECT file_path FROM endoflix_favorites")
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
                "INSERT INTO endoflix_favorites (file_path) VALUES (%s) ON CONFLICT DO NOTHING",
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
            cur.execute("DELETE FROM endoflix_favorites WHERE file_path = %s", (file_path,))
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
        cur.execute("""
            SELECT COUNT(DISTINCT file_path)
            FROM endoflix_playlist,
            LATERAL unnest(files) AS file_path
        """)
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
        cur.execute("""
            SELECT COUNT(DISTINCT file_path)
            FROM endoflix_playlist,
            LATERAL unnest(files) AS file_path
        """)
        video_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
        playlist_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM endoflix_session")
        session_count = cur.fetchone()[0] or 0

        # Playlists com play_count
        cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
        playlists = [{"name": row[0], "files": row[1], "play_count": row[2]} for row in cur.fetchall()]

        # Vídeos mais reproduzidos
        video_play_counts = Counter()
        for playlist in playlists:
            play_count = playlist["play_count"] or 0
            for file in playlist["files"]:
                video_play_counts[file] += play_count

        top_videos = [
            {"path": path, "play_count": count}
            for path, count in video_play_counts.most_common(10)
        ]

        # Distribuição por tipo de arquivo
        file_types = Counter()
        for playlist in playlists:
            for file in playlist["files"]:
                ext = Path(file).suffix.lower()
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