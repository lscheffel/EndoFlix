from flask import Blueprint, jsonify, request
from collections import Counter
from datetime import datetime, timedelta
import logging
from flask_login import login_required
from db import Database
from services.ultra_control_service import ultra_service
from limiter import limiter

DB_POOL = Database()  # Create database instance

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/stats', methods=['GET'])
@login_required
def stats():
    with DB_POOL.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                # Direct queries for stats
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
                logging.info(f"Analytics: video_count = {video_count}")
                cur.execute("SELECT COUNT(*) FROM endoflix_playlist")
                playlist_count = cur.fetchone()[0] or 0
                logging.info(f"Analytics: playlist_count = {playlist_count}")
                cur.execute("SELECT COUNT(*) FROM endoflix_session")
                session_count = cur.fetchone()[0] or 0
                logging.info(f"Analytics: session_count = {session_count}")

                # Active sessions (last hour)
                one_hour_ago = datetime.now() - timedelta(hours=1)
                cur.execute("SELECT COUNT(*) FROM session_metadata WHERE created_at > %s", (one_hour_ago,))
                active_sessions = cur.fetchone()[0] or 0
                logging.info(f"Analytics: active_sessions = {active_sessions}")

                # Total play time (mock: view_count * 10 seconds)
                cur.execute("SELECT SUM(view_count) FROM endoflix_files")
                total_views = cur.fetchone()[0] or 0
                total_play_time = total_views * 10
                logging.info(f"Analytics: total_play_time = {total_play_time}")

                # User activity (sessions in last 24h)
                last_24h = datetime.now() - timedelta(hours=24)
                cur.execute("SELECT COUNT(*) FROM session_metadata WHERE created_at > %s", (last_24h,))
                user_activity_24h = cur.fetchone()[0] or 0

                cur.execute("SELECT name, files, play_count FROM endoflix_playlist")
                playlists = [{"name": row[0], "files": row[1], "play_count": row[2]} for row in cur.fetchall()]

                # Enhanced query for top videos with pagination, search, sorting, and additional metrics
                page = int(request.args.get('page', 1))
                limit = int(request.args.get('limit', 10))
                search = request.args.get('search', '').strip()
                sort_by = request.args.get('sort_by', 'view_count')
                sort_order = request.args.get('sort_order', 'desc')

                # Whitelist allowed sort columns for security
                allowed_sort = {'view_count', 'total_play_time', 'engagement_score', 'file_path'}
                if sort_by not in allowed_sort:
                    sort_by = 'view_count'
                if sort_order not in ['asc', 'desc']:
                    sort_order = 'desc'

                offset = (page - 1) * limit

                # Build query
                base_query = """
                    SELECT file_path, view_count, is_favorite,
                           view_count * 10 AS total_play_time,
                           view_count + CASE WHEN is_favorite THEN 10 ELSE 0 END AS engagement_score
                    FROM endoflix_files
                """
                where_clause = ""
                params = []

                if search:
                    where_clause = "WHERE file_path ILIKE %s"
                    params.append(f'%{search}%')

                order_clause = f"ORDER BY {sort_by} {sort_order}"
                limit_clause = "LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                full_query = f"{base_query} {where_clause} {order_clause} {limit_clause}"

                cur.execute(full_query, params)
                top_videos = [{
                    "path": row[0],
                    "play_count": row[1],
                    "favorited": row[2],
                    "total_play_time": row[3],
                    "engagement_score": row[4]
                } for row in cur.fetchall()]

                # Get total count for pagination
                count_query = "SELECT COUNT(*) FROM endoflix_files"
                if search:
                    count_query += " WHERE file_path ILIKE %s"
                    count_params = [f'%{search}%']
                else:
                    count_params = []
                cur.execute(count_query, count_params)
                total_count = cur.fetchone()[0]

                # Direct query for file types
                cur.execute("SELECT file_path FROM endoflix_files")
                file_types = Counter()
                for row in cur.fetchall():
                    from pathlib import Path
                    ext = Path(row[0]).suffix.lower()
                    file_types[ext] += 1

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
                    'stats': {
                        'videos': video_count,
                        'playlists': playlist_count,
                        'sessions': session_count,
                        'active_sessions': active_sessions,
                        'total_play_time': total_play_time,
                        'user_activity_24h': user_activity_24h
                    },
                    'playlists': playlists,
                    'top_videos': top_videos,
                    'top_videos_total': total_count,
                    'file_types': dict(file_types),
                    'sessions': [{'name': s["name"], 'videos': s["videos"], 'timestamp': s["timestamp"].isoformat()} for s in sessions],
                    'player_usage': player_usage
                })
            except Exception as e:
                logging.error(f"Erro ao obter análises: {e}")
                return jsonify({'error': str(e)}), 500

@analytics_bp.route('/ultra/analytics/realtime', methods=['GET'])
@login_required
def ultra_realtime_analytics():
    if ultra_service:
        data = ultra_service._get_real_time_analytics()
        return jsonify(data)
    else:
        return jsonify({'error': 'Ultra service not available'}), 503

@analytics_bp.route('/ultra/commands/batch', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def ultra_batch_commands():
    try:
        commands = request.get_json()
        if not commands or not isinstance(commands, list):
            return jsonify({'error': 'Invalid commands format'}), 400

        # Validate commands
        valid_commands = ['play_all', 'pause_all', 'set_speed', 'toggle_shuffle', 'batch_operation']
        for cmd in commands:
            if not isinstance(cmd, dict) or 'command' not in cmd:
                return jsonify({'error': 'Each command must be a dict with "command" key'}), 400
            if cmd['command'] not in valid_commands:
                return jsonify({'error': f'Invalid command: {cmd["command"]}'}), 400

        # Process commands via ultra_service
        results = ultra_service.process_batch_commands(commands)

        logging.info(f"Processed {len(commands)} ultra batch commands")
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        logging.error(f"Error processing ultra batch commands: {e}")
        return jsonify({'error': str(e)}), 500