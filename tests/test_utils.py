import pytest
import os
import tempfile
from pathlib import Path
from utils import calculate_hash, get_video_metadata, process_file

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

    def test_get_video_metadata_no_cache(self, monkeypatch):
        # Mock Redis to be None
        monkeypatch.setattr('utils.REDIS_CLIENT', None)

        # Mock DB connection to return None
        def mock_getconn():
            class MockConn:
                def cursor(self):
                    class MockCur:
                        def execute(self, query, params=None):
                            pass
                        def fetchone(self):
                            return None
                        def close(self):
                            pass
                    return MockCur()
                def close(self):
                    pass
            return MockConn()

        monkeypatch.setattr('utils.DB_POOL.getconn', mock_getconn)

        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(b"fake video")
            temp_path = temp_file.name

        try:
            # This will try to run ffprobe, but since it's fake data, it should return default metadata
            result = get_video_metadata(Path(temp_path))
            assert 'duration_seconds' in result
            assert 'resolution' in result
            assert 'orientation' in result
            assert 'video_codec' in result
        finally:
            os.unlink(temp_path)