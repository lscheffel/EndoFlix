import pytest
from services.playlist_service import PlaylistService
from db import Database
from cache import RedisCache
import tempfile
from pathlib import Path

class TestPlaylistService:
    @pytest.fixture
    def service(self, test_db):
        db = Database()
        cache = RedisCache()
        return PlaylistService(db, cache)

    def test_create_playlist(self, service, test_db):
        """Test create_playlist"""
        result = service.create_playlist('test_create', ['file.mp4'], '/tmp')
        assert result['name'] == 'test_create'
        assert result['files'] == ['file.mp4']

    def test_get_playlist(self, service, test_db):
        """Test get_playlist"""
        service.create_playlist('test_get', ['file.mp4'], '/tmp')
        result = service.get_playlist('test_get')
        assert result['name'] == 'test_get'
        assert len(result['files']) == 1

    def test_get_playlist_not_found(self, service):
        """Test get_playlist for non-existent"""
        result = service.get_playlist('nonexistent')
        assert result is None

    def test_update_playlist(self, service, test_db):
        """Test update_playlist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.mp4"
            test_file.write_text("content")
            service.create_playlist('test_update', ['old.mp4'], temp_dir)
            result = service.update_playlist('test_update', temp_dir)
            assert result['name'] == 'test_update'

    def test_update_playlist_not_found(self, service):
        """Test update_playlist for non-existent"""
        with pytest.raises(ValueError):
            service.update_playlist('nonexistent', '/tmp')

    def test_delete_playlist(self, service, test_db):
        """Test delete_playlist"""
        service.create_playlist('test_delete', ['file.mp4'], '/tmp')
        result = service.delete_playlist('test_delete')
        assert result == True
        assert service.get_playlist('test_delete') is None

    def test_delete_playlist_not_found(self, service):
        """Test delete_playlist for non-existent"""
        result = service.delete_playlist('nonexistent')
        assert result == False

    def test_get_all_playlists(self, service, test_db):
        """Test get_all_playlists"""
        service.create_playlist('test_all1', ['file1.mp4'], '/tmp')
        service.create_playlist('test_all2', ['file2.mp4'], '/tmp')
        result = service.get_all_playlists()
        assert 'test_all1' in result
        assert 'test_all2' in result

    def test_save_temp_playlist(self, service, test_db):
        """Test save_temp_playlist"""
        # Create temp playlist
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files, is_temp) VALUES (%s, %s, %s)",
                ('temp_save', ['file.mp4'], True)
            )
            test_db.commit()
        result = service.save_temp_playlist('temp_save', 'saved')
        assert result['name'] == 'saved'

    def test_save_temp_playlist_not_found(self, service):
        """Test save_temp_playlist for non-existent temp"""
        with pytest.raises(ValueError):
            service.save_temp_playlist('nonexistent', 'new')

    def test_remove_from_playlist(self, service, test_db):
        """Test remove_from_playlist"""
        service.create_playlist('test_remove', ['file1.mp4', 'file2.mp4'], '/tmp')
        result = service.remove_from_playlist('test_remove', ['file1.mp4'])
        assert result['files'] == ['file2.mp4']

    def test_remove_from_playlist_not_found(self, service):
        """Test remove_from_playlist for non-existent"""
        with pytest.raises(ValueError):
            service.remove_from_playlist('nonexistent', ['file.mp4'])

    def test_import_playlist(self, service, test_db):
        """Test import_playlist"""
        result = service.import_playlist('imported', ['file.mp4'], '/tmp', 5)
        assert result['name'] == 'imported'
        assert result['play_count'] == 5

    def test_create_playlist_conflict(self, service, test_db):
        """Test create_playlist with existing name updates"""
        service.create_playlist('conflict', ['file1.mp4'], '/tmp')
        result = service.create_playlist('conflict', ['file2.mp4'], '/tmp')
        assert result['files'] == ['file2.mp4']

    def test_get_playlist_with_cache(self, service, test_db):
        """Test get_playlist uses cache"""
        service.create_playlist('cached', ['file.mp4'], '/tmp')
        # First call
        result1 = service.get_playlist('cached')
        # Second call should use cache
        result2 = service.get_playlist('cached')
        assert result1 == result2

    def test_update_playlist_with_temp(self, service, test_db):
        """Test update_playlist with temp_playlist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            service.create_playlist('update_temp', ['old.mp4'], temp_dir)
            # Create temp
            with test_db.cursor() as cur:
                cur.execute(
                    "INSERT INTO endoflix_playlist (name, files, is_temp) VALUES (%s, %s, %s)",
                    ('temp_update', ['new.mp4'], True)
                )
                test_db.commit()
            result = service.update_playlist('update_temp', temp_dir, 'temp_update')
            assert 'new.mp4' in result['files']