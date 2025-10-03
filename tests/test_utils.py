import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from utils import calculate_hash, get_video_metadata_cached, process_file, get_media_files

class TestUtils:
    def test_calculate_hash(self):
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"test content for hashing")
            temp_path = temp_file.name

        try:
            hash_result = calculate_hash(temp_path)
            assert isinstance(hash_result, str)
            assert len(hash_result) == 64  # SHA256 hex length
        finally:
            os.unlink(temp_path)

    def test_calculate_hash_large_file(self):
        # Test with larger file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"x" * 3 * 1024 * 1024)  # 3MB
            temp_path = temp_file.name

        try:
            hash_result = calculate_hash(temp_path)
            assert isinstance(hash_result, str)
            assert len(hash_result) == 64
        finally:
            os.unlink(temp_path)

    def test_process_file(self):
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(b"fake video content")
            temp_path = temp_file.name

        try:
            result = process_file(Path(temp_path))
            assert 'hash_id' in result
            assert 'file_path' in result
            assert 'size_bytes' in result
            assert result['size_bytes'] == len(b"fake video content")
            assert 'view_count' in result
            assert result['view_count'] == 0
        finally:
            os.unlink(temp_path)

    @patch('utils.REDIS_CLIENT')
    def test_get_video_metadata_cached_hit(self, mock_cache):
        # Mock cache hit
        mock_cache.get.return_value = '{"duration_seconds": 10, "resolution": "1920x1080"}'

        result = get_video_metadata_cached('/fake/path1.mp4', 1000, 1234567890)
        assert result['duration_seconds'] == 10
        assert result['resolution'] == '1920x1080'

    @patch('utils.DB_POOL')
    @patch('utils.REDIS_CLIENT')
    def test_get_video_metadata_cached_miss_db_hit(self, mock_cache, mock_pool):
        # Mock cache miss, DB hit
        mock_cache.get.return_value = None

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ('h264', '1920x1080', 'landscape', 10.5)
        mock_conn.cursor.return_value = mock_cur
        mock_pool.getconn.return_value = mock_conn

        result = get_video_metadata_cached('/fake/path2.mp4', 1000, 1234567890)
        assert result['video_codec'] == 'h264'
        assert result['duration_seconds'] == 10.5

    @patch('utils.DB_POOL')
    @patch('utils.REDIS_CLIENT')
    def test_get_video_metadata_cached_miss_ffprobe(self, mock_cache, mock_pool):
        # Mock cache miss, DB miss, use ffprobe
        mock_cache.get.return_value = None

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cur
        mock_pool.getconn.return_value = mock_conn

        # Mock subprocess
        with patch('utils.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b'{"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "duration": "10.5"}]}')
            result = get_video_metadata_cached('/fake/path3.mp4', 1000, 1234567890)
            assert result['video_codec'] == 'h264'
            assert result['duration_seconds'] == 10.5

    @patch('utils.DB_POOL')
    @patch('utils.REDIS_CLIENT')
    def test_get_video_metadata_cached_ffprobe_error(self, mock_cache, mock_pool):
        # Mock ffprobe error
        mock_cache.get.return_value = None

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cur
        mock_pool.getconn.return_value = mock_conn

        with patch('utils.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b'error')
            result = get_video_metadata_cached('/fake/path4.mp4', 1000, 1234567890)
            assert result['video_codec'] == 'unknown'
            assert result['duration_seconds'] == 0

    def test_get_media_files_invalid_folder(self):
        """Test get_media_files with invalid folder"""
        events = list(get_media_files('/nonexistent'))
        assert len(events) == 1
        assert 'error' in events[0]

    def test_get_media_files_empty_folder(self, tmp_path):
        """Test get_media_files with empty folder"""
        events = list(get_media_files(str(tmp_path)))
        assert len(events) >= 1  # At least end event

    def test_get_media_files_with_files(self, tmp_path):
        """Test get_media_files with media files"""
        # Create fake mp4
        (tmp_path / "test.mp4").write_bytes(b"fake")
        events = list(get_media_files(str(tmp_path)))
        # Should have start, update, end events
        assert any('start' in event for event in events)
        assert any('end' in event for event in events)

    def test_calculate_hash_nonexistent_file(self):
        """Test calculate_hash with non-existent file"""
        with pytest.raises(FileNotFoundError):
            calculate_hash('/nonexistent')

    def test_process_file_nonexistent(self):
        """Test process_file with non-existent file"""
        with pytest.raises(FileNotFoundError):
            process_file(Path('/nonexistent'))