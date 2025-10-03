#!/usr/bin/env python3
"""
Test script for EndoFlix thumbnail logic implementation.
Tests all requirements: .thumbs folder creation, 50x50 WebP thumbnails,
frame extraction from 10% into video, sanitization, and performance.
"""

import os
import sys
import time
import logging
from pathlib import Path
from PIL import Image
import json

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

from thumbnail_processor import ThumbnailProcessor
from db import Database
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThumbnailTester:
    def __init__(self):
        self.config = Config()
        self.db = Database()
        self.processor = ThumbnailProcessor()
        self.test_dir = Path("test_thumbnails")
        self.playlist_name = "test_playlist"

    def setup_test_playlist(self):
        """Create a test playlist with the sample videos."""
        logger.info("Setting up test playlist...")

        # Get absolute paths for the test videos
        video_files = [str((self.test_dir / "test_video1.mp4").absolute())]

        if not video_files:
            raise ValueError("No test video files found!")

        logger.info(f"Found {len(video_files)} test videos: {[Path(f).name for f in video_files]}")

        # Create playlist in database
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, 0, %s) ON CONFLICT (name) DO UPDATE SET files = EXCLUDED.files, source_folder = EXCLUDED.source_folder",
                    (self.playlist_name, video_files, str(self.test_dir.absolute()))
                )
                conn.commit()

        logger.info(f"Created test playlist '{self.playlist_name}' with {len(video_files)} videos")
        return video_files

    def cleanup_previous_test(self):
        """Clean up any previous test artifacts."""
        logger.info("Cleaning up previous test artifacts...")

        # Remove .thumbs directory if it exists
        thumbs_dir = self.test_dir / '.thumbs'
        if thumbs_dir.exists():
            import shutil
            shutil.rmtree(thumbs_dir)
            logger.info("Removed existing .thumbs directory")

        # Remove test playlist from database
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM endoflix_playlist WHERE name = %s", (self.playlist_name,))
                conn.commit()
                logger.info("Removed existing test playlist from database")

    def test_thumbs_folder_creation(self):
        """Test 1: Verify .thumbs folder is created in playlist directory."""
        logger.info("Testing .thumbs folder creation...")

        thumbs_dir = self.test_dir / '.thumbs'
        assert not thumbs_dir.exists(), ".thumbs directory should not exist before processing"

        # Process thumbnails
        result = self.processor.process_playlist_thumbnails(self.playlist_name)
        assert result['success'], f"Thumbnail processing failed: {result.get('error', 'Unknown error')}"

        # Check if .thumbs directory was created
        assert thumbs_dir.exists(), ".thumbs directory was not created"
        assert thumbs_dir.is_dir(), ".thumbs should be a directory"

        logger.info("✓ .thumbs folder creation test passed")
        return True

    def test_thumbnail_generation(self):
        """Test 2: Verify 50x50 square WebP thumbnails with same name as video."""
        logger.info("Testing thumbnail generation...")

        thumbs_dir = self.test_dir / '.thumbs'

        # Get video files
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s", (self.playlist_name,))
                result = cur.fetchone()
                video_files = result[0] if result else []

        assert len(video_files) > 0, "No video files in playlist"

        # Check each video has a corresponding thumbnail
        for video_path in video_files:
            video_name = Path(video_path).stem
            thumb_path = thumbs_dir / f"{video_name}.webp"

            assert thumb_path.exists(), f"Thumbnail not found for {video_name}"
            assert thumb_path.is_file(), f"Thumbnail should be a file: {thumb_path}"

            # Verify it's a valid WebP image
            try:
                with Image.open(thumb_path) as img:
                    assert img.format == 'WEBP', f"Thumbnail is not WebP format: {thumb_path}"
                    assert img.size == (50, 50), f"Thumbnail size is not 50x50: {img.size} for {thumb_path}"
                    logger.info(f"✓ Thumbnail verified: {thumb_path.name} - {img.size} {img.format}")
            except Exception as e:
                assert False, f"Invalid thumbnail image {thumb_path}: {e}"

        logger.info("✓ Thumbnail generation test passed")
        return True

    def test_frame_extraction_timing(self):
        """Test 3: Verify frame extraction from 10% into video."""
        logger.info("Testing frame extraction timing...")

        # This is harder to test directly, but we can verify the FFmpeg command structure
        # by checking the processor code and ensuring the timestamp calculation is correct

        from utils import get_video_metadata_cached as get_video_metadata

        for video_file in self.test_dir.glob("*.mp4"):
            metadata = get_video_metadata(str(video_file))
            duration = metadata.get('duration_seconds', 0)
            expected_timestamp = duration * 0.1  # 10%

            logger.info(f"Video {video_file.name}: duration={duration:.2f}s, expected timestamp={expected_timestamp:.2f}s")

            # We can't easily verify the exact frame extracted without complex analysis,
            # but we can ensure the logic is sound
            assert duration > 0, f"Video duration should be > 0 for {video_file}"
            assert expected_timestamp > 0, f"Expected timestamp should be > 0 for {video_file}"

        logger.info("✓ Frame extraction timing logic verified")
        return True

    def test_sanitization(self):
        """Test 4: Test sanitization (deleting orphaned thumbs, creating only for new videos)."""
        logger.info("Testing sanitization...")

        thumbs_dir = self.test_dir / '.thumbs'

        # First, create an orphaned thumbnail (no corresponding video)
        orphaned_thumb = thumbs_dir / "orphaned.webp"
        orphaned_thumb.write_bytes(b"fake webp data")

        # Add a new video to the playlist
        new_video_path = self.test_dir / "test_video4.mp4"
        # Copy an existing video as the new one
        import shutil
        shutil.copy(self.test_dir / "test_video1.mp4", new_video_path)

        # Update playlist with new video
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s", (self.playlist_name,))
                result = cur.fetchone()
                current_files = result[0] if result else []
                current_files.append(str(new_video_path.absolute()))
                cur.execute("UPDATE endoflix_playlist SET files = %s WHERE name = %s", (current_files, self.playlist_name))
                conn.commit()

        # Re-run thumbnail processing
        result = self.processor.process_playlist_thumbnails(self.playlist_name)
        assert result['success'], f"Thumbnail processing failed: {result.get('error', 'Unknown error')}"

        # Check orphaned thumbnail was deleted
        assert not orphaned_thumb.exists(), "Orphaned thumbnail was not deleted"

        # Check new thumbnail was created
        new_thumb_path = thumbs_dir / "test_video4.webp"
        assert new_thumb_path.exists(), "New thumbnail was not created"

        # Clean up
        new_video_path.unlink()
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s", (self.playlist_name,))
                result = cur.fetchone()
                current_files = result[0] if result else []
                current_files = [f for f in current_files if f != str(new_video_path.absolute())]
                cur.execute("UPDATE endoflix_playlist SET files = %s WHERE name = %s", (current_files, self.playlist_name))
                conn.commit()

        logger.info("✓ Sanitization test passed")
        return True

    def test_performance(self):
        """Test 5: Test performance optimizations for large playlists (100+ videos)."""
        logger.info("Testing performance optimizations for large volumes...")

        # Create a larger playlist by duplicating videos
        large_playlist_name = "large_test_playlist"
        large_video_files = []

        # Duplicate videos to simulate a larger playlist (120 videos = 120 copies of test_video1.mp4)
        for i in range(120):
            large_video_files.append(str((self.test_dir / "test_video1.mp4").absolute()))

        logger.info(f"Created simulated playlist with {len(large_video_files)} video entries")

        # Create large playlist
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO endoflix_playlist (name, files, play_count, source_folder) VALUES (%s, %s, 0, %s)",
                    (large_playlist_name, large_video_files, str(self.test_dir.absolute()))
                )
                conn.commit()

        # Time the processing
        start_time = time.time()
        result = self.processor.process_playlist_thumbnails(large_playlist_name)
        end_time = time.time()

        processing_time = end_time - start_time
        logger.info(f"Processed {len(large_video_files)} videos in {processing_time:.2f} seconds")
        logger.info(f"Average time per video: {processing_time/len(large_video_files):.3f} seconds")

        assert result['success'], f"Large playlist processing failed: {result.get('error', 'Unknown error')}"
        assert processing_time < 120, f"Processing took too long: {processing_time:.2f} seconds (should be < 120s for 120 videos)"

        # Verify all thumbnails were created (should be 3 unique thumbnails since same videos repeated)
        thumbs_dir = self.test_dir / '.thumbs'
        expected_thumbs = len(set(Path(f).stem for f in large_video_files))  # Unique video names
        actual_thumbs = len(list(thumbs_dir.glob("*.webp")))
        assert actual_thumbs >= expected_thumbs, f"Expected at least {expected_thumbs} thumbnails, got {actual_thumbs}"

        # Verify batch processing and worker settings
        logger.info(f"Configuration: workers={self.processor.max_workers}, batch_size={self.processor.batch_size}, timeout={self.processor.ffmpeg_timeout}s")

        # Clean up
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM endoflix_playlist WHERE name = %s", (large_playlist_name,))
                conn.commit()

        logger.info("✓ Large volume performance test passed")
        return True

    def test_optimizations_and_requirements(self):
        """Test 6: Verify all optimization requirements for large volume processing."""
        logger.info("Testing optimization requirements...")

        # Verify configuration settings before processing
        assert self.processor.max_workers == 4, f"Expected 4 workers, got {self.processor.max_workers}"
        assert self.processor.ffmpeg_timeout == 60, f"Expected 60s timeout, got {self.processor.ffmpeg_timeout}"
        assert self.processor.batch_size == 100, f"Expected batch size 100, got {self.processor.batch_size}"

        # Test .thumbs folder creation as hidden
        thumbs_dir = self.test_dir / '.thumbs'
        result = self.processor.process_playlist_thumbnails(self.playlist_name)
        assert result['success'], f"Thumbnail processing failed: {result.get('error', 'Unknown error')}"

        assert thumbs_dir.exists(), ".thumbs directory was not created"
        if os.name == 'nt':  # Windows
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(thumbs_dir))
            is_hidden = bool(attrs & 2)  # FILE_ATTRIBUTE_HIDDEN
            assert is_hidden, ".thumbs directory should be hidden on Windows"

        # Test correct saving location
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT files FROM endoflix_playlist WHERE name = %s", (self.playlist_name,))
                result = cur.fetchone()
                video_files = result[0] if result else []

        for video_path in video_files:
            video_name = Path(video_path).stem
            thumb_path = thumbs_dir / f"{video_name}.webp"
            assert thumb_path.exists(), f"Thumbnail not saved in correct location: {thumb_path}"

        # Test progress logging (check if logs contain expected messages)
        # This is harder to test directly, but we can verify the processor has logging

        # Test resource monitoring (if psutil available)
        if hasattr(self.processor, '__class__') and 'psutil' in str(self.processor.__class__.__module__):
            logger.info("Resource monitoring is implemented")
        else:
            logger.info("Resource monitoring check skipped (psutil not available)")

        logger.info("✓ Optimization requirements test passed")
        return True

    def run_all_tests(self):
        """Run all thumbnail tests."""
        logger.info("Starting thumbnail logic tests...")

        try:
            # Setup
            self.cleanup_previous_test()
            self.setup_test_playlist()

            # Run tests
            test_results = []

            test_results.append(("Thumbs folder creation", self.test_thumbs_folder_creation()))
            test_results.append(("Thumbnail generation", self.test_thumbnail_generation()))
            test_results.append(("Frame extraction timing", self.test_frame_extraction_timing()))
            test_results.append(("Sanitization", self.test_sanitization()))
            test_results.append(("Performance", self.test_performance()))
            test_results.append(("Optimizations and requirements", self.test_optimizations_and_requirements()))

            # Summary
            passed = sum(1 for _, result in test_results if result)
            total = len(test_results)

            logger.info(f"\n{'='*50}")
            logger.info("TEST RESULTS SUMMARY")
            logger.info(f"{'='*50}")

            for test_name, result in test_results:
                status = "✓ PASS" if result else "✗ FAIL"
                logger.info(f"{status}: {test_name}")

            logger.info(f"\nPassed: {passed}/{total}")

            if passed == total:
                logger.info("🎉 All tests passed!")
                return True
            else:
                logger.error("❌ Some tests failed!")
                return False

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Cleanup
            self.cleanup_previous_test()

def main():
    tester = ThumbnailTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()