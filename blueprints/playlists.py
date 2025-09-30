from flask import Blueprint, request, jsonify
from pathlib import Path
import json
import logging
from flask_login import login_required
from db import Database
from utils import get_media_files

DB_POOL = Database()  # Create database instance

playlists_bp = Blueprint('playlists', __name__)

@playlists_bp.route('/playlists', methods=['GET', 'POST'])
@login_required
def playlists():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
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

@playlists_bp.route('/save_temp_playlist', methods=['POST'])
@login_required
def save_temp_playlist():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
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

@playlists_bp.route('/remove_playlist', methods=['POST'])
@login_required
def remove_playlist():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
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

@playlists_bp.route('/update_playlist', methods=['POST'])
@login_required
def update_playlist():
    data = request.get_json()
    name = data.get('name')
    source_folder = data.get('source_folder')
    temp_playlist = data.get('temp_playlist')

    if not name or not source_folder:
        return jsonify({'success': False, 'error': 'Nome da playlist e pasta são obrigatórios'}), 400

    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
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