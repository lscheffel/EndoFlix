import json
import logging
from pathlib import Path
from typing import Optional
from db import Database
from cache import RedisCache
from utils import get_media_files, normalize_path

class PlaylistService:
    def __init__(self, db: Database, cache: RedisCache):
        self.db = db
        self.cache = cache

    def create_playlist(self, name: str, files: list, source_folder: str) -> dict:
        """Create a new playlist, insert into DB, invalidate cache, return dict."""
        source_folder = normalize_path(source_folder)
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, 0, %s) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, play_count = endoflix_playlist.play_count, source_folder = EXCLUDED.source_folder RETURNING id",
                        (name, files, source_folder)
                    )
                    conn.commit()
                    # Invalidate cache for this playlist
                    self.cache.delete(f"playlist:{name}")
                    return {"name": name, "files": files, "play_count": 0, "source_folder": source_folder}
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error creating playlist: {str(e)}")
                    raise

    def get_playlist(self, name: str) -> Optional[dict]:
        """Get playlist, check cache first, then DB, cache result."""
        logging.info(f"Getting playlist: {name}")
        cache_key = f"playlist:{name}"
        cached = self.cache.get(cache_key)
        if cached:
            logging.info(f"Found cached playlist: {name}")
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                logging.warning(f"Invalid cache for playlist: {name}")
                pass  # Fall through to DB

        logging.info(f"Querying DB for playlist: {name}")
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT files, play_count, source_folder FROM endoflix_playlist WHERE name = %s AND is_temp = FALSE", (name,))
                result = cur.fetchone()
                if not result or len(result) != 3:
                    logging.warning(f"No result from DB for playlist: {name}, result: {result}")
                    return None
                files, play_count, source_folder = result
                logging.info(f"Found DB data for playlist: {name}, files count: {len(files)}")
                # Add metadata to files
                files_with_meta = []
                for f in files:
                    cur2 = conn.cursor()
                    cur2.execute("SELECT size_bytes, modified_at FROM endoflix_files WHERE file_path = %s", (f,))
                    meta_result = cur2.fetchone()
                    if meta_result and len(meta_result) == 2:
                        size, modified = meta_result
                        files_with_meta.append({"path": f, "size": size, "modified": modified.isoformat() if modified else None, "extension": Path(f).suffix.lower()[1:]})
                    else:
                        files_with_meta.append({"path": f, "size": 0, "modified": None, "extension": Path(f).suffix.lower()[1:]})
                    cur2.close()
                playlist_data = {"name": name, "files": files_with_meta, "play_count": play_count, "source_folder": source_folder}
                # Cache the result
                self.cache.set(cache_key, json.dumps(playlist_data))
                logging.info(f"Returning playlist: {name}")
                return playlist_data

    def update_playlist(self, name: str, source_folder: str, temp_playlist: Optional[str] = None) -> dict:
        """Update playlist by rescanning source_folder, incorporating temp_playlist if provided."""
        source_folder = normalize_path(source_folder)
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # Verify playlist exists
                    cur.execute("SELECT files, source_folder FROM endoflix_playlist WHERE name = %s AND is_temp = FALSE", (name,))
                    playlist = cur.fetchone()
                    if not playlist or len(playlist) != 2:
                        raise ValueError("Playlist not found")

                    # Get updated files from source_folder
                    updated_files = []
                    for event in get_media_files(source_folder):  # Synchronous iteration
                        data = json.loads(event.replace('data: ', ''))
                        if data['status'] in ['skipped', 'update']:
                            updated_files.append(data['file']['path'])
                        elif data['status'] == 'error':
                            logging.error(f"Error processing file: {data['message']}")

                    # If temp_playlist provided, incorporate its files
                    if temp_playlist:
                        cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_playlist,))
                        temp_result = cur.fetchone()
                        if temp_result and len(temp_result) > 0:
                            updated_files.extend(temp_result[0])
                            # Delete temp playlist
                            cur.execute("DELETE FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_playlist,))

                    # Sanitize: remove duplicates and non-existent files
                    updated_files = list(dict.fromkeys(updated_files))  # Remove duplicates
                    valid_files = [f for f in updated_files if Path(f).exists()]

                    # Update DB
                    cur.execute(
                        "UPDATE endoflix_playlist SET files = %s, source_folder = %s WHERE name = %s AND is_temp = FALSE",
                        (valid_files, source_folder, name)
                    )
                    conn.commit()
                    # Invalidate cache
                    self.cache.delete(f"playlist:{name}")
                    return {"name": name, "files": valid_files, "source_folder": source_folder}
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error updating playlist: {str(e)}")
                    raise

    def delete_playlist(self, name: str) -> bool:
        """Delete playlist from DB, invalidate cache."""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("DELETE FROM endoflix_playlist WHERE name = %s", (name,))
                    deleted = cur.rowcount > 0
                    if deleted:
                        conn.commit()
                        # Invalidate cache
                        self.cache.delete(f"playlist:{name}")
                    return deleted
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error deleting playlist: {str(e)}")
                    raise

    def get_all_playlists(self) -> dict:
        """Get all non-temp playlists."""
        logging.info("Starting get_all_playlists")
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM endoflix_playlist WHERE is_temp = FALSE")
                names = [row[0] for row in cur.fetchall()]
                logging.info(f"Found playlist names: {names}")
                playlists = {}
                for name in names:
                    logging.info(f"Loading playlist: {name}")
                    playlist = self.get_playlist(name)
                    if playlist:
                        playlists[name] = playlist
                        logging.info(f"Successfully loaded playlist: {name}")
                    else:
                        logging.warning(f"Failed to load playlist: {name}")
                logging.info(f"Returning {len(playlists)} playlists")
                return playlists

    def save_temp_playlist(self, temp_name: str, new_name: str) -> dict:
        """Save temp playlist as permanent."""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT files, source_folder FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_name,))
                    result = cur.fetchone()
                    if not result or len(result) != 2:
                        raise ValueError("Temp playlist not found")
                    files, source_folder = result
                    cur.execute(
                        "INSERT INTO endoflix_playlist (name, files, play_count, source_folder, is_temp) VALUES (%s, %s, %s, %s, %s)",
                        (new_name.strip(), files, 0, source_folder, False)
                    )
                    cur.execute("DELETE FROM endoflix_playlist WHERE name = %s AND is_temp = TRUE", (temp_name,))
                    conn.commit()
                    self.cache.delete(f"playlist:{new_name}")
                    return {"name": new_name, "files": files, "source_folder": source_folder}
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error saving temp playlist: {str(e)}")
                    raise

    def remove_from_playlist(self, name: str, files_to_remove: list) -> dict:
        """Remove files from playlist."""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s AND is_temp = FALSE", (name,))
                    result = cur.fetchone()
                    if not result or len(result) == 0:
                        raise ValueError("Playlist not found")
                    current_files = result[0]
                    updated_files = [f for f in current_files if f not in files_to_remove]
                    cur.execute("UPDATE endoflix_playlist SET files = %s WHERE name = %s AND is_temp = FALSE", (updated_files, name))
                    conn.commit()
                    self.cache.delete(f"playlist:{name}")
                    return {"name": name, "files": updated_files}
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error removing from playlist: {str(e)}")
                    raise

    def import_playlist(self, name: str, files: list, source_folder: str, play_count: int = 0) -> dict:
        """Import playlist."""
        source_folder = normalize_path(source_folder)
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, play_count = EXCLUDED.play_count, source_folder = EXCLUDED.source_folder",
                        (name, files, play_count, source_folder)
                    )
                    conn.commit()
                    self.cache.delete(f"playlist:{name}")
                    return {"name": name, "files": files, "play_count": play_count, "source_folder": source_folder}
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error importing playlist: {str(e)}")
                    raise