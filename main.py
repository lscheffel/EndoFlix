from flask import Flask, render_template, request, jsonify, Response
import os
from pathlib import Path
import psycopg2
import logging

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
            media.append(str(file))
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
            return jsonify({'error': 'Nenhum arquivo de vídeo encontrado na pasta'}), 404
    app.logger.error(f"Pasta inválida ou não encontrada: {folder}")
    return jsonify({'error': 'Pasta inválida ou não encontrada'}), 400

@app.route('/playlists', methods=['GET', 'POST'])
def playlists():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, files FROM endoflix_playlist")
            playlists = {row[0]: row[1] for row in cur.fetchall()}
            app.logger.debug(f"Playlists carregadas: {len(playlists)}")
            return jsonify(playlists)
        elif request.method == 'POST':
            data = request.get_json()
            app.logger.debug(f"Dados recebidos para salvar playlist: {data}")
            name = data.get('name')
            files = data.get('files')
            
            # Validação
            if not name or not isinstance(name, str) or name.strip() == '':
                app.logger.error("Nome da playlist inválido ou não fornecido")
                return jsonify({'success': False, 'error': 'Nome da playlist é obrigatório'}), 400
            if not files or not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                app.logger.error("Lista de arquivos inválida")
                return jsonify({'success': False, 'error': 'Lista de arquivos inválida'}), 400
            if len(files) == 0:
                app.logger.error("Nenhum arquivo fornecido para a playlist")
                return jsonify({'success': False, 'error': 'A playlist deve conter pelo menos um arquivo'}), 400
            
            # Salvar no banco
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files RETURNING id",
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

@app.route('/sessions', methods=['GET', 'POST'])
def sessions():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if request.method == 'GET':
            cur.execute("SELECT name, videos FROM endoflix_session")
            sessions = {row[0]: row[1] for row in cur.fetchall()}
            app.logger.debug(f"Sessões carregadas: {len(sessions)}")
            return jsonify(sessions)
        elif request.method == 'POST':
            data = request.get_json()
            app.logger.debug(f"Dados recebidos para salvar sessão: {data}")
            name = data.get('name')
            videos = data.get('videos')
            
            # Validação
            if not name or not isinstance(name, str) or name.strip() == '':
                app.logger.error("Nome da sessão inválido ou não fornecido")
                return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
            if not videos or not isinstance(videos, list) or not all(isinstance(v, str) for v in videos):
                app.logger.error("Lista de vídeos inválida")
                return jsonify({'success': False, 'error': 'Lista de vídeos inválida'}), 400
            
            # Salvar no banco
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
        
        # Validação
        if not name or not isinstance(name, str) or name.strip() == '':
            app.logger.error("Nome da sessão inválido ou não fornecido")
            return jsonify({'success': False, 'error': 'Nome da sessão é obrigatório'}), 400
        
        # Remover do banco
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

@app.route('/video/<path:filename>')
def serve_video(filename):
    input_path = Path(filename).as_posix()
    return serve_video_range(input_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)