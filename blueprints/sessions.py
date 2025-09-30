from flask import Blueprint, request, jsonify
import logging
from flask_login import login_required
from db import Database

DB_POOL = Database()  # Create database instance

sessions_bp = Blueprint('sessions', __name__)

@sessions_bp.route('/sessions', methods=['GET', 'POST'])
@login_required
def sessions():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
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

@sessions_bp.route('/remove_session', methods=['POST'])
@login_required
def remove_session():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
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