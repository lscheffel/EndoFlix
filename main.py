from flask import Flask, render_template, request, jsonify, send_file, Response
import os
import json
from pathlib import Path
import logging

app = Flask(__name__)
PLAYLISTS_FILE = "playlists.json"
TRANSCODE_DIR = Path("transcode")

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

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

def load_playlists():
    try:
        with open(PLAYLISTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        app.logger.warning(f"Arquivo {PLAYLISTS_FILE} não encontrado, criando novo.")
        return {}

def save_playlists(playlists):
    try:
        with open(PLAYLISTS_FILE, 'w') as f:
            json.dump(playlists, f, indent=4)
        app.logger.debug(f"Playlists salvas em {PLAYLISTS_FILE}")
    except Exception as e:
        app.logger.error(f"Erro ao salvar playlists: {e}")

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
    if request.method == 'GET':
        return jsonify(load_playlists())
    elif request.method == 'POST':
        data = request.get_json()
        playlists = load_playlists()
        playlists[data['name']] = data['files']
        save_playlists(playlists)
        return jsonify({'success': True})

@app.route('/video/<path:filename>')
def serve_video(filename):
    input_path = Path(filename).as_posix()
    return serve_video_range(input_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)