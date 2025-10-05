from flask import Blueprint, request, jsonify
import logging
from flask_login import login_required, current_user
from db import Database
from models import CreateSession, UpdateSession, RemoveSession
from datetime import datetime
from services.ultra_control_service import ultra_service

DB_POOL = Database()  # Create database instance

sessions_bp = Blueprint('sessions', __name__)

@sessions_bp.route('/sessions', methods=['GET', 'POST'])
@login_required
def sessions():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                if request.method == 'GET':
                    cur.execute("""
                        SELECT s.name, s.videos, m.created_at, m.updated_at, m.duration, m.state
                        FROM endoflix_session s
                        LEFT JOIN session_metadata m ON s.id = m.session_id
                        ORDER BY m.created_at DESC
                    """)
                    sessions = []
                    for row in cur.fetchall():
                        sessions.append({
                            'name': row[0],
                            'videos': row[1],
                            'created_at': row[2].isoformat() if row[2] else None,
                            'updated_at': row[3].isoformat() if row[3] else None,
                            'duration': row[4] or 0,
                            'state': row[5] or 'active'
                        })
                    return jsonify(sessions)
                else:
                    data = request.get_json()
                    session_data = CreateSession(**data)
                    # Insert session
                    cur.execute(
                        "INSERT INTO endoflix_session (name, videos) VALUES (%s, %s) RETURNING id",
                        (session_data.name, session_data.videos)
                    )
                    session_id = cur.fetchone()[0]
                    # Insert metadata
                    cur.execute(
                        "INSERT INTO session_metadata (session_id, user_id) VALUES (%s, %s)",
                        (session_id, current_user.id if current_user.is_authenticated else None)
                    )
                    conn.commit()
                    # Emit real-time update
                    if ultra_service:
                        ultra_service.emit_session_update({
                            'action': 'created',
                            'session': {
                                'name': session_data.name,
                                'videos': session_data.videos,
                                'state': 'active',
                                'user_id': current_user.id if current_user.is_authenticated else None
                            }
                        })
                    return jsonify({'success': True, 'session_id': session_id})
            except Exception as e:
                conn.rollback()
                logging.error(f"Erro ao gerenciar sessão: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500

@sessions_bp.route('/ultra/sessions/active', methods=['GET'])
@login_required
def get_active_sessions():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT s.name, s.videos, m.created_at, m.updated_at, m.duration, m.state, m.user_id
                    FROM endoflix_session s
                    JOIN session_metadata m ON s.id = m.session_id
                    WHERE m.state = 'active' AND m.updated_at > NOW() - INTERVAL '1 hour'
                    ORDER BY m.updated_at DESC
                """)
                sessions = []
                for row in cur.fetchall():
                    sessions.append({
                        'name': row[0],
                        'videos': row[1],
                        'created_at': row[2].isoformat() if row[2] else None,
                        'updated_at': row[3].isoformat() if row[3] else None,
                        'duration': row[4] or 0,
                        'state': row[5] or 'active',
                        'user_id': row[6]
                    })
                return jsonify(sessions)
            except Exception as e:
                logging.error(f"Erro ao buscar sessões ativas: {str(e)}")
                return jsonify({'error': str(e)}), 500

@sessions_bp.route('/ultra/sessions/<session_name>', methods=['PUT'])
@login_required
def update_session(session_name):
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                data = request.get_json()
                update_data = UpdateSession(name=session_name, **data)
                # Get current version
                cur.execute("SELECT m.version FROM endoflix_session s JOIN session_metadata m ON s.id = m.session_id WHERE s.name = %s", (session_name,))
                row = cur.fetchone()
                if not row:
                    return jsonify({'success': False, 'error': 'Sessão não encontrada'}), 404
                current_version = row[0]
                # Check version for conflict
                if 'version' in data and data['version'] != current_version:
                    return jsonify({'success': False, 'error': 'Conflito de versão', 'current_version': current_version}), 409
                # Update metadata
                update_fields = []
                params = []
                if update_data.videos is not None:
                    update_fields.append("videos = %s")
                    params.append(update_data.videos)
                    cur.execute("UPDATE endoflix_session SET videos = %s WHERE name = %s", (update_data.videos, session_name))
                if update_data.state is not None:
                    update_fields.append("state = %s")
                    params.append(update_data.state)
                if update_data.duration is not None:
                    update_fields.append("duration = %s")
                    params.append(update_data.duration)
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                update_fields.append("version = version + 1")
                params.append(session_name)
                cur.execute(f"UPDATE session_metadata SET {', '.join(update_fields)} WHERE session_id = (SELECT id FROM endoflix_session WHERE name = %s)", params)
                conn.commit()
                # Emit real-time update
                if ultra_service:
                    ultra_service.emit_session_update({
                        'action': 'updated',
                        'session': {
                            'name': session_name,
                            'state': update_data.state,
                            'duration': update_data.duration
                        }
                    })
                return jsonify({'success': True})
            except Exception as e:
                conn.rollback()
                logging.error(f"Erro ao atualizar sessão: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
@sessions_bp.route('/remove_session', methods=['POST'])
@login_required
def remove_session():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                data = request.get_json()
                session_data = RemoveSession(**data)
                cur.execute("DELETE FROM endoflix_session WHERE name = %s", (session_data.name,))
                if cur.rowcount > 0:
                    conn.commit()
                    return jsonify({'success': True}), 200
                return jsonify({'success': False, 'error': 'Sessão não encontrada'}), 404
            except Exception as e:
                conn.rollback()
                logging.error(f"Erro ao remover sessão: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500