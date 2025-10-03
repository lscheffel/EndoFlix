import pytest
import json
import tempfile
import os
from pathlib import Path

class TestPlaylists:
    def test_get_playlists_unauthenticated(self, client):
        """Test GET /playlists requires login"""
        response = client.get('/playlists')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_get_playlists_authenticated(self, authenticated_client, test_db):
        """Test GET /playlists returns playlists"""
        response = authenticated_client.get('/playlists')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, dict)

    def test_create_playlist_valid(self, authenticated_client, test_db):
        """Test POST /playlists with valid data"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.mp4"
            test_file.write_text("fake content")
            data = {
                'name': 'test_playlist',
                'files': [str(test_file)],
                'source_folder': temp_dir
            }
            response = authenticated_client.post('/playlists', json=data)
            assert response.status_code == 200
            assert response.get_json()['success'] == True

    def test_create_playlist_invalid_name(self, authenticated_client):
        """Test POST /playlists with empty name"""
        data = {
            'name': '',
            'files': ['file.mp4'],
            'source_folder': '/tmp'
        }
        response = authenticated_client.post('/playlists', json=data)
        assert response.status_code == 400
        assert response.get_json()['success'] == False

    def test_create_playlist_invalid_files(self, authenticated_client):
        """Test POST /playlists with empty files"""
        data = {
            'name': 'test',
            'files': [],
            'source_folder': '/tmp'
        }
        response = authenticated_client.post('/playlists', json=data)
        assert response.status_code == 400

    def test_create_playlist_invalid_source_folder(self, authenticated_client):
        """Test POST /playlists with non-existent source folder"""
        data = {
            'name': 'test',
            'files': ['file.mp4'],
            'source_folder': '/nonexistent'
        }
        response = authenticated_client.post('/playlists', json=data)
        assert response.status_code == 400

    def test_save_temp_playlist_valid(self, authenticated_client, test_db):
        """Test POST /save_temp_playlist"""
        # First create a temp playlist
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files, is_temp) VALUES (%s, %s, %s)",
                ('temp_test', ['file1.mp4'], True)
            )
            test_db.commit()
        data = {
            'temp_name': 'temp_test',
            'new_name': 'saved_playlist'
        }
        response = authenticated_client.post('/save_temp_playlist', json=data)
        assert response.status_code == 200
        assert response.get_json()['success'] == True

    def test_save_temp_playlist_not_found(self, authenticated_client):
        """Test POST /save_temp_playlist with non-existent temp playlist"""
        data = {
            'temp_name': 'nonexistent',
            'new_name': 'new'
        }
        response = authenticated_client.post('/save_temp_playlist', json=data)
        assert response.status_code == 404

    def test_remove_playlist_valid(self, authenticated_client, test_db):
        """Test POST /remove_playlist"""
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files) VALUES (%s, %s)",
                ('to_remove', ['file.mp4'])
            )
            test_db.commit()
        data = {'name': 'to_remove'}
        response = authenticated_client.post('/remove_playlist', json=data)
        assert response.status_code == 200
        assert response.get_json()['success'] == True

    def test_remove_playlist_not_found(self, authenticated_client):
        """Test POST /remove_playlist with non-existent playlist"""
        data = {'name': 'nonexistent'}
        response = authenticated_client.post('/remove_playlist', json=data)
        assert response.status_code == 404

    def test_update_playlist_valid(self, authenticated_client, test_db):
        """Test POST /update_playlist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.mp4"
            test_file.write_text("content")
            with test_db.cursor() as cur:
                cur.execute(
                    "INSERT INTO endoflix_playlist (name, files, source_folder) VALUES (%s, %s, %s)",
                    ('update_test', ['old.mp4'], temp_dir)
                )
                test_db.commit()
            data = {
                'name': 'update_test',
                'source_folder': temp_dir
            }
            response = authenticated_client.post('/update_playlist', json=data)
            assert response.status_code == 200
            assert response.get_json()['success'] == True

    def test_export_playlist_valid(self, authenticated_client, test_db):
        """Test GET /export_playlist/<name>"""
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files) VALUES (%s, %s)",
                ('export_test', ['file.mp4'])
            )
            test_db.commit()
        response = authenticated_client.get('/export_playlist/export_test')
        assert response.status_code == 200
        data = response.get_json()
        assert 'name' in data
        assert 'files' in data

    def test_export_playlist_not_found(self, authenticated_client):
        """Test GET /export_playlist/<name> for non-existent"""
        response = authenticated_client.get('/export_playlist/nonexistent')
        assert response.status_code == 404

    def test_remove_from_playlist_valid(self, authenticated_client, test_db):
        """Test POST /remove_from_playlist"""
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files) VALUES (%s, %s)",
                ('remove_from', ['file1.mp4', 'file2.mp4'])
            )
            test_db.commit()
        data = {
            'name': 'remove_from',
            'files': ['file1.mp4']
        }
        response = authenticated_client.post('/remove_from_playlist', json=data)
        assert response.status_code == 200
        assert response.get_json()['success'] == True

    def test_import_playlist_json(self, authenticated_client):
        """Test POST /import_playlist with JSON file"""
        import_data = {
            'name': 'imported',
            'files': ['file.mp4'],
            'source_folder': '/tmp'
        }
        from io import BytesIO
        file_data = BytesIO(json.dumps(import_data).encode())
        file_data.filename = 'test.json'
        response = authenticated_client.post('/import_playlist', data={'file': (file_data, 'test.json')})
        assert response.status_code == 200
        assert response.get_json()['success'] == True

    def test_import_playlist_csv(self, authenticated_client):
        """Test POST /import_playlist with CSV file"""
        csv_data = "name,files,source_folder\nimported_csv,file.mp4,/tmp"
        from io import BytesIO
        file_data = BytesIO(csv_data.encode())
        file_data.filename = 'test.csv'
        response = authenticated_client.post('/import_playlist', data={'file': (file_data, 'test.csv')})
        assert response.status_code == 200

    def test_import_playlist_invalid_file_type(self, authenticated_client):
        """Test POST /import_playlist with invalid file type"""
        from io import BytesIO
        file_data = BytesIO(b"invalid")
        file_data.filename = 'test.txt'
        response = authenticated_client.post('/import_playlist', data={'file': (file_data, 'test.txt')})
        assert response.status_code == 400

    def test_generate_thumbnails(self, authenticated_client, test_db):
        """Test POST /generate_thumbnails/<name>"""
        with test_db.cursor() as cur:
            cur.execute(
                "INSERT INTO endoflix_playlist (name, files) VALUES (%s, %s)",
                ('thumb_test', ['file.mp4'])
            )
            test_db.commit()
        response = authenticated_client.post('/generate_thumbnails/thumb_test')
        assert response.status_code == 200
        data = response.get_json()
        assert 'status' in data
        assert data['status'] == 'started'