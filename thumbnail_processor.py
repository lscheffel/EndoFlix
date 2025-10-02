import os
import subprocess
import logging
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Set
import time
from config import Config
from db import Database
from utils import get_video_metadata

class ThumbnailProcessor:
    def __init__(self):
        self.config = Config()
        self.db = Database()
        self.ffmpeg_path = self.config.FFMPEG_PATH
        self.thumb_size = self.config.THUMB_SIZE
        self.thumb_format = self.config.THUMB_FORMAT
        self.thumb_quality = self.config.THUMB_QUALITY
        self.extraction_point = self.config.THUMB_EXTRACTION_POINT
        self.max_workers = self.config.THUMB_WORKERS

    @staticmethod
    def generate_thumbnail(video_path: str, output_path: str, ffmpeg_path: str, thumb_size: int, thumb_quality: int, extraction_point: float) -> bool:
        """Generate a thumbnail for a single video file."""
        try:
            # Get video duration
            metadata = get_video_metadata(video_path)
            duration = metadata.get('duration_seconds', 0)
            if duration <= 0:
                logging.warning(f"Could not get duration for {video_path}")
                return False

            # Calculate timestamp for extraction (10% into video)
            timestamp = duration * extraction_point

            # FFmpeg command to extract frame, scale, and save as WebP
            cmd = [
                ffmpeg_path,
                '-ss', str(timestamp),  # Seek to timestamp
                '-i', video_path,       # Input file
                '-vframes', '1',        # Extract one frame
                '-vf', f'scale={thumb_size}:{thumb_size}:force_original_aspect_ratio=decrease,pad={thumb_size}:{thumb_size}:(ow-iw)/2:(oh-ih)/2',  # Scale and pad to square
                '-q:v', str(thumb_quality),  # Quality for WebP
                '-f', 'webp',           # Output format
                '-y',                   # Overwrite output
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logging.info(f"Thumbnail generated for {video_path}")
                return True
            else:
                logging.error(f"FFmpeg error for {video_path}: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout generating thumbnail for {video_path}")
            return False
        except Exception as e:
            logging.error(f"Error generating thumbnail for {video_path}: {e}")
            return False

    def sanitize_thumbs(self, thumbs_dir: Path, video_files: List[str]) -> List[str]:
        """Sanitize thumbnails: delete orphaned ones, return videos needing thumbs."""
        if not thumbs_dir.exists():
            return video_files  # All need thumbs

        # Get existing thumbs
        existing_thumbs = set()
        for file in thumbs_dir.iterdir():
            if file.is_file() and file.suffix.lower() == f'.{self.thumb_format}':
                existing_thumbs.add(file.stem)  # filename without extension

        # Video filenames without extension
        video_names = {Path(v).stem for v in video_files}

        # Orphaned thumbs: exist but no video
        orphaned = existing_thumbs - video_names
        for orphan in orphaned:
            thumb_path = thumbs_dir / f"{orphan}.{self.thumb_format}"
            try:
                thumb_path.unlink()
                logging.info(f"Deleted orphaned thumbnail: {thumb_path}")
            except Exception as e:
                logging.error(f"Error deleting orphaned thumbnail {thumb_path}: {e}")

        # Videos needing thumbs: have video but no thumb
        needing_thumbs = [v for v in video_files if Path(v).stem not in existing_thumbs]

        return needing_thumbs

    def process_playlist_thumbnails(self, playlist_name: str) -> dict:
        """Process thumbnails for a playlist."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get playlist source_folder and files
                    cur.execute("SELECT source_folder, files FROM endoflix_playlist WHERE name = %s AND is_temp = FALSE", (playlist_name,))
                    result = cur.fetchone()
                    if not result:
                        return {'success': False, 'error': 'Playlist not found'}

                    source_folder, files = result
                    if not files:
                        return {'success': True, 'message': 'No files in playlist'}

            thumbs_dir = Path(source_folder) / '.thumbs'
            thumbs_dir.mkdir(exist_ok=True)

            # Sanitize
            needing_thumbs = self.sanitize_thumbs(thumbs_dir, files)

            if not needing_thumbs:
                return {'success': True, 'message': 'All thumbnails up to date'}

            # Generate thumbnails in parallel
            generated = 0
            failed = 0

            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for video_path in needing_thumbs:
                    output_path = thumbs_dir / f"{Path(video_path).stem}.{self.thumb_format}"
                    future = executor.submit(
                        self.generate_thumbnail,
                        video_path,
                        str(output_path),
                        self.ffmpeg_path,
                        self.thumb_size,
                        self.thumb_quality,
                        self.extraction_point
                    )
                    futures[future] = video_path

                for future in as_completed(futures):
                    video_path = futures[future]
                    try:
                        if future.result():
                            generated += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logging.error(f"Exception processing {video_path}: {e}")
                        failed += 1

            message = f"Generated {generated} thumbnails, {failed} failed"
            return {'success': True, 'message': message, 'generated': generated, 'failed': failed}

        except Exception as e:
            logging.error(f"Error processing thumbnails for playlist {playlist_name}: {e}")
            return {'success': False, 'error': str(e)}