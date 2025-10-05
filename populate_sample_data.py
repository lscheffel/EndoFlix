#!/usr/bin/env python3
"""
Script to populate EndoFlix database with sample data for testing analytics.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from db import Database

def populate_sample_data():
    """Insert sample data into the database for testing."""
    db = Database()

    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Insert sample videos
                videos = [
                    ('/videos/sample1.mp4', 15000000, 'hash1', 5, True, datetime.now() - timedelta(days=1)),
                    ('/videos/sample2.mkv', 20000000, 'hash2', 3, False, datetime.now() - timedelta(hours=12)),
                    ('/videos/sample3.avi', 10000000, 'hash3', 8, True, datetime.now() - timedelta(days=2)),
                    ('/videos/sample4.mp4', 25000000, 'hash4', 2, False, datetime.now() - timedelta(hours=6)),
                    ('/videos/sample5.webm', 18000000, 'hash5', 4, True, datetime.now() - timedelta(days=3)),
                ]

                cur.executemany("""
                    INSERT INTO endoflix_files (file_path, size_bytes, hash_id, view_count, is_favorite, last_viewed_at, created_at, modified_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, [(v[0], v[1], v[2], v[3], v[4], v[5], datetime.now(), datetime.now()) for v in videos])

                # Insert sample playlists
                playlists = [
                    ('My Favorites', ['/videos/sample1.mp4', '/videos/sample3.avi', '/videos/sample5.webm'], 10, False),
                    ('Recent Videos', ['/videos/sample2.mkv', '/videos/sample4.mp4'], 5, False),
                    ('Temp Playlist', ['/videos/sample1.mp4'], 1, True),
                ]

                for name, files, play_count, is_temp in playlists:
                    cur.execute("""
                        INSERT INTO endoflix_playlist (name, files, play_count, is_temp)
                        VALUES (%s, %s, %s, %s)
                    """, (name, files, play_count, is_temp))

                # Insert sample sessions
                sessions = [
                    ('session_2024-10-01T10-00-00', ['/videos/sample1.mp4', '/videos/sample2.mkv']),
                    ('session_2024-10-02T14-30-00', ['/videos/sample3.avi']),
                    ('session_2024-10-03T09-15-00', ['/videos/sample4.mp4', '/videos/sample5.webm', '/videos/sample1.mp4']),
                ]

                for name, videos in sessions:
                    cur.execute("""
                        INSERT INTO endoflix_session (name, videos)
                        VALUES (%s, %s)
                    """, (name, videos))

                # # Insert sample session metadata
                # metadata = [
                #     (1, datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1), 3600, 'ended', 1),
                #     (2, datetime.now() - timedelta(hours=4), datetime.now() - timedelta(hours=3), 1800, 'active', 1),
                #     (3, datetime.now() - timedelta(hours=6), datetime.now() - timedelta(hours=5), 2400, 'paused', 1),
                # ]

                # for session_id, created_at, updated_at, duration, state, user_id in metadata:
                #     cur.execute("""
                #         INSERT INTO session_metadata (session_id, created_at, updated_at, duration, state, user_id)
                #         VALUES (%s, %s, %s, %s, %s, %s)
                #     """, (session_id, created_at, updated_at, duration, state, user_id))

                conn.commit()
                print("Sample data inserted successfully!")

    except Exception as e:
        print(f"Error inserting sample data: {e}")
        conn.rollback()

if __name__ == '__main__':
    populate_sample_data()