from flask import Blueprint, jsonify
from collections import Counter
from datetime import datetime
import logging
from flask_login import login_required
from db import Database

DB_POOL = Database()  # Create database instance

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/stats', methods=['GET'])
@login_required
def stats():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                # Use optimized materialized view for stats
                cur.execute("SELECT total_videos, total_playlists, total_sessions FROM mv_analytics_stats")
                result = cur.fetchone()
                if result:
                    video_count, playlist_count, session_count = result
                else:
                    # Fallback to direct queries if view not available
                    cur.execute("SELECT COUNT(*) FROM endoflix_files")
                    video_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM endoflix_playlist WHERE is_temp = FALSE")
                    playlist_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM endoflix_session")
                    session_count = cur.fetchone()[0]
                return jsonify({'videos': video_count, 'playlists': playlist_count, 'sessions': session_count})
            except Exception as e:
                logging.error(f"Erro ao obter estatísticas: {e}")
                return jsonify({'error': str(e)}), 500

@analytics_bp.route('/analytics', methods=['GET'])
@login_required
def analytics():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT COUNT(*) FROM endoflix_files")
                video_count = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
                playlist_count = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM endoflix_session")
                session_count = cur.fetchone()[0] or 0

                cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
                playlists = [{"name": row[0], "files": row[1], "play_count": row[2]} for row in cur.fetchall()]

                # Use optimized view for top videos
                cur.execute("SELECT file_path, view_count, is_favorite FROM v_top_videos")
                top_videos = [{"path": row[0], "play_count": row[1], "favorited": row[2]} for row in cur.fetchall()]

                # Use optimized view for file types
                cur.execute("SELECT file_type, count FROM v_file_types")
                file_types = {row[0]: row[1] for row in cur.fetchall()}

                cur.execute("SELECT name, videos FROM endoflix_session")
                sessions = []
                for row in cur.fetchall():
                    name_parts = row[0].split('_')[0].split('-')
                    try:
                        timestamp = datetime.strptime('-'.join(name_parts[:5]), '%Y-%m-%dT%H-%M-%S') if len(name_parts) >= 5 else datetime.now()
                    except ValueError:
                        timestamp = datetime.now()
                    sessions.append({"name": row[0], "videos": row[1], "timestamp": timestamp})

                player_usage = [0, 0, 0, 0]
                for session in sessions:
                    for i, video in enumerate(session["videos"][:4]):
                        if video:
                            player_usage[i] += 1

                return jsonify({
                    'stats': {'videos': video_count, 'playlists': playlist_count, 'sessions': session_count},
                    'playlists': playlists,
                    'top_videos': top_videos,
                    'file_types': dict(file_types),
                    'sessions': [{'name': s["name"], 'videos': s["videos"], 'timestamp': s["timestamp"].isoformat()} for s in sessions],
                    'player_usage': player_usage
                })
            except Exception as e:
                logging.error(f"Erro ao obter análises: {e}")
                return jsonify({'error': str(e)}), 500