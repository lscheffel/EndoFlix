from flask import Blueprint, request, Response, jsonify
from pathlib import Path
import os
import base64
import json
import logging
from datetime import datetime
from flask_login import login_required
from ..main import DB_POOL, TRANSCODE_DIR  # Import from main for now
from ..utils import process_file, index_file

video_bp = Blueprint('video', __name__)

@video_bp.route('/video/<path:filename>')
@login_required
def serve_video(filename):
    return serve_video_range(Path(filename))

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

def ensure_snapshots_dir(video_path):
    video_dir = os.path.dirname(video_path)
    snapshots_dir = os.path.join(video_dir, 'snapshots')
    if not os.path.exists(snapshots_dir):
        os.makedirs(snapshots_dir)
    return snapshots_dir

@video_bp.route('/save_snapshot', methods=['POST'])
@login_required
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