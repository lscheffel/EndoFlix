import threading
import time
from flask_socketio import emit
from db import Database
import logging
from datetime import datetime, timedelta

class UltraControlService:
    def __init__(self, socketio, db_pool):
        self.socketio = socketio
        self.db_pool = db_pool
        self.running = False
        self.thread = None
        self.player_states = {
            'playing': [False, False, False, False],
            'speed': [1.0, 1.0, 1.0, 1.0],
            'shuffle': False,
            'shuffle_interval': 3
        }
        self.command_queue = []
        self.lock = threading.Lock()

    def start_real_time_updates(self):
        """Start the real-time update thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._real_time_loop, daemon=True)
            self.thread.start()
            logging.info("UltraControlService real-time updates started")

    def stop_real_time_updates(self):
        """Stop the real-time update thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            logging.info("UltraControlService real-time updates stopped")

    def _real_time_loop(self):
        """Main loop for emitting real-time analytics data"""
        while self.running:
            try:
                data = self._get_real_time_analytics()
                logging.info(f"Emitting real-time analytics update: stats={data.get('stats', {})}")
                self.socketio.emit('ultra_analytics_update', data, namespace='/ultra')
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logging.error(f"Error in real-time loop: {e}")
                time.sleep(10)  # Wait longer on error

    def _get_real_time_analytics(self):
        """Fetch real-time analytics data"""
        with self.db_pool.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # Current stats
                    cur.execute("SELECT COUNT(*) FROM endoflix_files")
                    video_count = cur.fetchone()[0] or 0
                    logging.info(f"Ultra analytics: video_count = {video_count}")

                    cur.execute("SELECT COUNT(*) FROM endoflix_playlist WHERE is_temp = FALSE")
                    playlist_count = cur.fetchone()[0] or 0
                    logging.info(f"Ultra analytics: playlist_count = {playlist_count}")

                    cur.execute("SELECT COUNT(*) FROM endoflix_session")
                    session_count = cur.fetchone()[0] or 0
                    logging.info(f"Ultra analytics: session_count = {session_count}")

                    # Active sessions (sessions created in last hour)
                    one_hour_ago = datetime.now() - timedelta(hours=1)
                    cur.execute("SELECT COUNT(*) FROM session_metadata WHERE created_at > %s", (one_hour_ago,))
                    active_sessions = cur.fetchone()[0] or 0
                    logging.info(f"Ultra analytics: active_sessions = {active_sessions}")

                    # Total play time (assuming we add a play_time column, for now use view_count * 10 as mock)
                    cur.execute("SELECT SUM(view_count) FROM endoflix_files")
                    total_views = cur.fetchone()[0] or 0
                    total_play_time = total_views * 10  # Mock: 10 seconds per view
                    logging.info(f"Ultra analytics: total_play_time = {total_play_time}")

                    # User activity: count of sessions in last 24 hours
                    last_24h = datetime.now() - timedelta(hours=24)
                    cur.execute("SELECT COUNT(*) FROM session_metadata WHERE created_at > %s", (last_24h,))
                    user_activity_24h = cur.fetchone()[0] or 0
                    logging.info(f"Ultra analytics: user_activity_24h = {user_activity_24h}")

                    # Top videos with additional metrics (for real-time updates)
                    cur.execute("""
                        SELECT file_path, view_count, is_favorite,
                               view_count * 10 AS total_play_time,
                               view_count + CASE WHEN is_favorite THEN 10 ELSE 0 END AS engagement_score
                        FROM endoflix_files
                        ORDER BY view_count DESC LIMIT 10
                    """)
                    top_videos = [{
                        "path": row[0],
                        "play_count": row[1],
                        "favorited": row[2],
                        "total_play_time": row[3],
                        "engagement_score": row[4]
                    } for row in cur.fetchall()]

                    # Real-time metrics
                    current_time = datetime.now().isoformat()

                    return {
                        'timestamp': current_time,
                        'stats': {
                            'videos': video_count,
                            'playlists': playlist_count,
                            'sessions': session_count,
                            'active_sessions': active_sessions,
                            'total_play_time': total_play_time,
                            'user_activity_24h': user_activity_24h
                        },
                        'top_videos': top_videos,
                        'real_time_metrics': {
                            'current_active_users': active_sessions,  # Mock
                            'play_time_today': total_play_time // 10,  # Mock
                            'new_sessions_last_hour': active_sessions
                        }
                    }
                except Exception as e:
                    logging.error(f"Error fetching real-time analytics: {e}")
                    return {'error': str(e)}

    def emit_control_command(self, command, data=None):
        """Emit control commands to clients"""
        self.socketio.emit('ultra_control', {'command': command, 'data': data}, namespace='/ultra')

    def emit_session_update(self, session_data):
        """Emit session updates to clients"""
        self.socketio.emit('ultra_session_update', session_data, namespace='/ultra')

    def process_batch_commands(self, commands):
        """Process a batch of commands with conflict resolution"""
        results = []
        with self.lock:
            for cmd in commands:
                try:
                    result = self._execute_command(cmd)
                    results.append({'command': cmd['command'], 'success': True, 'result': result})
                    logging.info(f"Executed command: {cmd}")
                except Exception as e:
                    results.append({'command': cmd['command'], 'success': False, 'error': str(e)})
                    logging.error(f"Failed to execute command {cmd}: {e}")
        return results

    def _execute_command(self, cmd):
        """Execute a single command"""
        command = cmd['command']
        if command == 'play_all':
            self._play_all()
            return {'action': 'play_all', 'players': self.player_states['playing']}
        elif command == 'pause_all':
            self._pause_all()
            return {'action': 'pause_all', 'players': self.player_states['playing']}
        elif command == 'set_speed':
            speed = cmd.get('speed', 1.0)
            self._set_speed(speed)
            return {'action': 'set_speed', 'speed': self.player_states['speed']}
        elif command == 'toggle_shuffle':
            enable = cmd.get('enable', True)
            interval = cmd.get('interval', 3)
            self._toggle_shuffle(enable, interval)
            return {'action': 'toggle_shuffle', 'shuffle': self.player_states['shuffle'], 'interval': self.player_states['shuffle_interval']}
        elif command == 'batch_operation':
            operations = cmd.get('operations', [])
            return self._batch_operation(operations)
        else:
            raise ValueError(f"Unknown command: {command}")

    def _play_all(self):
        """Play all players"""
        self.player_states['playing'] = [True, True, True, True]
        self.emit_control_command('play_all', {'players': self.player_states['playing']})

    def _pause_all(self):
        """Pause all players"""
        self.player_states['playing'] = [False, False, False, False]
        self.emit_control_command('pause_all', {'players': self.player_states['playing']})

    def _set_speed(self, speed):
        """Set speed for all players"""
        if not (0.5 <= speed <= 2.0):
            raise ValueError("Speed must be between 0.5 and 2.0")
        self.player_states['speed'] = [speed, speed, speed, speed]
        self.emit_control_command('set_speed', {'speed': speed, 'players': self.player_states['speed']})

    def _toggle_shuffle(self, enable, interval):
        """Toggle auto-shuffle"""
        self.player_states['shuffle'] = enable
        self.player_states['shuffle_interval'] = interval
        self.emit_control_command('toggle_shuffle', {'enable': enable, 'interval': interval})

    def _batch_operation(self, operations):
        """Perform batch operations like load videos, etc."""
        # Placeholder for batch operations
        self.emit_control_command('batch_operation', {'operations': operations})
        return {'operations': operations}

    def get_player_states(self):
        """Get current player states"""
        return self.player_states.copy()

# Global instance
ultra_service = None

def init_ultra_service(socketio, db_pool):
    global ultra_service
    ultra_service = UltraControlService(socketio, db_pool)
    return ultra_service