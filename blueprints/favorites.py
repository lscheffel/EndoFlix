from flask import Blueprint, request, jsonify
import logging
from flask_login import login_required
from db import Database

DB_POOL = Database()  # Create database instance

favorites_bp = Blueprint('favorites', __name__)

@favorites_bp.route('/favorites', methods=['GET', 'POST', 'DELETE'])
@login_required
def favorites():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                if request.method == 'GET':
                    cur.execute("SELECT file_path FROM endoflix_files WHERE is_favorite = TRUE")
                    favorites = [row[0] for row in cur.fetchall()]
                    return jsonify(favorites)
                elif request.method == 'POST':
                    data = request.get_json()
                    file_paths = data.get('file_paths') or [data.get('file_path')]
                    if not file_paths or not isinstance(file_paths, list) or not all(isinstance(f, str) for f in file_paths):
                        return jsonify({'success': False, 'error': 'Caminhos dos arquivos são obrigatórios'}), 400
                    for file_path in file_paths:
                        cur.execute("UPDATE endoflix_files SET is_favorite = TRUE WHERE file_path = %s", (file_path,))
                    conn.commit()
                    return jsonify({'success': True})
                else:
                    data = request.get_json()
                    file_paths = data.get('file_paths') or [data.get('file_path')]
                    if not file_paths or not isinstance(file_paths, list) or not all(isinstance(f, str) for f in file_paths):
                        return jsonify({'success': False, 'error': 'Caminhos dos arquivos são obrigatórios'}), 400
                    for file_path in file_paths:
                        cur.execute("UPDATE endoflix_files SET is_favorite = FALSE WHERE file_path = %s", (file_path,))
                    conn.commit()
                    return jsonify({'success': True})
            except Exception as e:
                conn.rollback()
                logging.error(f"Erro ao gerenciar favoritos: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500