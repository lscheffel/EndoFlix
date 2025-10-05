from flask import Blueprint, request, Response, jsonify
from pathlib import Path
import os
import base64
import json
import logging
from datetime import datetime
from urllib.parse import unquote
from flask_login import login_required
from db import Database
from config import Config
from utils import process_file, index_file
from prometheus_flask_exporter import Counter

DB_POOL = Database()  # Create database instance
TRANSCODE_DIR = Config.TRANSCODE_DIR

video_bp = Blueprint('video', __name__)

# Prometheus counter for video views
video_views_counter = Counter('video_views', 'Number of video views')

@video_bp.route('/video/preview/<path:filename>')
@login_required
def serve_video_preview(filename):
    filename = unquote(filename)
    if filename.startswith('/'):
        filename = filename.lstrip('/')
    return serve_video_range(Path(filename), is_preview=True)

@video_bp.route('/video/<path:filename>')
@login_required
def serve_video(filename):
    filename = unquote(filename)
    if filename.startswith('/'):
        filename = filename.lstrip('/')
    return serve_video_range(Path(filename))

def serve_video_range(input_path, is_preview=False):
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

    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT 1 FROM endoflix_files WHERE file_path = %s", (input_path_str,))
                if not cur.fetchone():
                    file_data = process_file(input_path_str)
                    index_file(conn, file_data)
                # Only increment view_count if not a preview request
                if not is_preview:
                    cur.execute("UPDATE endoflix_files SET view_count = view_count + 1, last_viewed_at = CURRENT_TIMESTAMP WHERE file_path = %s", (input_path_str,))
                    conn.commit()
                    logging.info(f"Incremented view_count for {input_path_str} (is_preview={is_preview})")
                else:
                    logging.debug(f"Preview request for {input_path_str}, not incrementing view_count (is_preview={is_preview})")
            except Exception as e:
                conn.rollback()
                logging.error(f"Erro ao atualizar visualizações para {input_path_str}: {e}")

    # Increment Prometheus counter
    video_views_counter.inc()

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

@video_bp.route('/all_videos')
@login_required
def all_videos():
    try:
        with DB_POOL.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT file_path, size_bytes, modified_at, video_codec
                    FROM endoflix_files
                    ORDER BY file_path
                """)
                rows = cur.fetchall()
                videos = []
                for row in rows:
                    # Extract extension from file_path
                    file_path = row[0]
                    extension = file_path.split('.')[-1].lower() if '.' in file_path else 'unknown'
                    videos.append({
                        'path': file_path,
                        'size': row[1],
                        'modified': row[2].isoformat() if row[2] else None,
                        'extension': extension
                    })
                logging.info(f"Returning {len(videos)} videos from /all_videos")
                return jsonify(videos)
    except Exception as e:
        logging.error(f"Erro ao obter todos os vídeos: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@video_bp.route('/thumbnail/<path:filename>')
@login_required
def serve_thumbnail(filename):
    filename = unquote(filename)
    if filename.startswith('/'):
        filename = filename.lstrip('/')

    # For now, return a placeholder or generate thumbnail
    # This is a simplified version - in production you'd cache thumbnails
    try:
        # Check if thumbnail exists
        thumbnail_path = Path(filename).parent / 'thumbnails' / f"{Path(filename).stem}.jpg"
        if thumbnail_path.exists():
            return Response(
                thumbnail_path.read_bytes(),
                mimetype='image/jpeg'
            )
        else:
            # Return a default thumbnail or generate one
            # For simplicity, return a 1x1 pixel image
            return Response(
                b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\x00\x00\x00\x00\xff\xd9',
                mimetype='image/jpeg'
            )
    except Exception as e:
        logging.error(f"Erro ao servir thumbnail: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

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