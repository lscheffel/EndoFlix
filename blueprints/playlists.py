from flask import Blueprint, request, jsonify
from pathlib import Path
import json
import logging
import threading
import csv
from io import StringIO
from flask_login import login_required
from db import Database
from cache import RedisCache
from utils import get_media_files
from thumbnail_processor import ThumbnailProcessor
from models import PlaylistCreate, SaveTempPlaylist, RemovePlaylist, UpdatePlaylist, RemoveFromPlaylist
from pydantic import ValidationError
from services.playlist_service import PlaylistService

DB_POOL = Database()  # Create database instance
CACHE = RedisCache()
playlist_service = PlaylistService(DB_POOL, CACHE)

playlists_bp = Blueprint('playlists', __name__)

@playlists_bp.route('/playlists', methods=['GET', 'POST'])
@login_required
def playlists():
    try:
        if request.method == 'GET':
            playlists = playlist_service.get_all_playlists()
            return jsonify(playlists)
        else:
            try:
                data = PlaylistCreate(**request.get_json())
            except ValidationError as e:
                return jsonify({'success': False, 'error': str(e)}), 400
            playlist_service.create_playlist(data.name, data.files, data.source_folder)
            return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Erro ao gerenciar playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/save_temp_playlist', methods=['POST'])
@login_required
def save_temp_playlist():
    try:
        try:
            data = SaveTempPlaylist(**request.get_json())
        except ValidationError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        result = playlist_service.save_temp_playlist(data.temp_name, data.new_name)
        logging.info(f"Playlist {result['name']} salva a partir de {data.temp_name}")
        return jsonify({'success': True, 'name': result['name'], 'files': result['files']})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Erro ao salvar playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/remove_playlist', methods=['POST'])
@login_required
def remove_playlist():
    try:
        try:
            data = RemovePlaylist(**request.get_json())
        except ValidationError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        if playlist_service.delete_playlist(data.name):
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'error': 'Playlist não encontrada'}), 404
    except Exception as e:
        logging.error(f"Erro ao remover playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/update_playlist', methods=['POST'])
@login_required
def update_playlist():
    try:
        data = UpdatePlaylist(**request.get_json())
    except ValidationError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    try:
        result = playlist_service.update_playlist(data.name, data.source_folder, data.temp_playlist)
        return jsonify({'success': True, 'files': result['files']})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Erro ao atualizar playlist: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/export_playlist/<name>', methods=['GET'])
@login_required
def export_playlist(name):
    try:
        playlist_data = playlist_service.get_playlist(name)
        if not playlist_data:
            return jsonify({'error': 'Playlist not found'}), 404
        return jsonify(playlist_data)
    except Exception as e:
        logging.error(f"Erro ao exportar playlist: {str(e)}")
        return jsonify({'error': str(e)}), 500

@playlists_bp.route('/remove_from_playlist', methods=['POST'])
@login_required
def remove_from_playlist():
    try:
        try:
            data = RemoveFromPlaylist(**request.get_json())
        except ValidationError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        result = playlist_service.remove_from_playlist(data.name, data.files)
        return jsonify({'success': True, 'files': result['files']})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Erro ao remover arquivos da playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/import_playlist', methods=['POST'])
@login_required
def import_playlist():
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'Arquivo não fornecido'}), 400

    filename = file.filename.lower() if file.filename else ''
    if not (filename.endswith('.json') or filename.endswith('.csv')):
        return jsonify({'success': False, 'error': 'Arquivo deve ser .json ou .csv'}), 400

    try:
        content = file.read().decode('utf-8')
        name = None
        files = None
        source_folder = ''
        play_count = 0
        if filename.endswith('.json'):
            data = json.loads(content)
            name = data.get('name')
            files = data.get('files', [])
            source_folder = data.get('source_folder', '')
            play_count = data.get('play_count', 0)
        elif filename.endswith('.csv'):
            reader = csv.DictReader(StringIO(content))
            row = next(reader)  # Assume one row
            name = row.get('name')
            files = [f.strip() for f in row.get('files', '').split(',') if f.strip()]
            source_folder = row.get('source_folder', '')
            play_count = int(row.get('play_count', 0))

        if not name or not files:
            return jsonify({'success': False, 'error': 'Dados inválidos no arquivo'}), 400

        playlist_service.import_playlist(name, files, source_folder, play_count)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Erro ao importar playlist: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@playlists_bp.route('/generate_thumbnails/<playlist_name>', methods=['POST'])
@login_required
def generate_thumbnails(playlist_name):
    try:
        def run_in_background():
            processor = ThumbnailProcessor()
            processor.process_playlist_thumbnails(playlist_name)

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()
        return jsonify({"status": "started", "message": "Thumbnail generation started in background"})
    except Exception as e:
        logging.error(f"Erro ao iniciar geração de thumbnails para playlist {playlist_name}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500