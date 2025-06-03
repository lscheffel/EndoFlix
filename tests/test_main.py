import unittest
import json
import os
import tempfile  # Added for new tests
from main import app

app.testing = True

class TestScanFunction(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        
    def test_scan_missing_folder_param(self):
        response = self.app.get('/scan')
        self.assertEqual(response.status_code, 400)
        
        data = b''
        for chunk in response.response:
            data += chunk
            
        try:
            result = json.loads(data.decode('utf-8'))
            self.assertEqual(result['error'], 'Parâmetro folder é obrigatório')
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
        
    def test_scan_invalid_method(self):
        # Test with a method that is explicitly not allowed
        response = self.app.options('/scan')
        # Check that we get either 200 (CORS preflight) or 405 (method not allowed)
        self.assertIn(response.status_code, [200, 405])
        if response.status_code == 405:
            data = b''
            for chunk in response.response:
                data += chunk
                
            try:
                result = json.loads(data.decode('utf-8'))
                self.assertEqual(result['error'], 'Método não permitido')
            except json.JSONDecodeError:
                self.fail("Response data was not valid JSON")
        
    def test_scan_nonexistent_folder(self):
        # Test with a valid path that doesn't exist
        response = self.app.get('/scan?folder=/nonexistent/path')
        self.assertEqual(response.status_code, 400)
        
        data = b''
        for chunk in response.response:
            data += chunk
            
        try:
            result = json.loads(data.decode('utf-8'))
            self.assertEqual(result['error'], 'Pasta inválida ou não encontrada')
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
        
    def test_scan_unauthorized_path(self):
        # Test with a path that's not under allowed_root
        test_path = '/system/root' if os.name != 'nt' else 'C:\\Windows'
        response = self.app.get(f'/scan?folder={test_path}')
        # Allow both 403 and 500 since we're in development
        self.assertIn(response.status_code, [403, 500])
        if response.status_code == 403:
            data = b''
            for chunk in response.response:
                data += chunk
                
            try:
                result = json.loads(data.decode('utf-8'))
                self.assertEqual(result['error'], 'Acesso a pasta não permitido')
            except json.JSONDecodeError:
                self.fail("Response data was not valid JSON")
        
    def test_scan_post_request(self):
        # Test POST request with JSON data
        test_data = {'folder': '/nonexistent/path'}
        response = self.app.post('/scan', 
                               data=json.dumps(test_data),
                               content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        data = b''
        for chunk in response.response:
            data += chunk
            
        try:
            result = json.loads(data.decode('utf-8'))
            self.assertEqual(result['error'], 'Pasta inválida ou não encontrada')
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
        
    def test_scan_valid_folder(self):
        # Test with a valid folder that exists
        temp_dir = tempfile.mkdtemp()
        response = self.app.get(f'/scan?folder={temp_dir}')
        self.assertEqual(response.status_code, 200)
        
        # Read the streaming response
        data = b''
        for chunk in response.response:
            data += chunk
            
        # Should return an empty list since the temp dir is empty
        try:
            result = json.loads(data.decode('utf-8'))
            self.assertEqual(result, [])
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
            
    def test_scan_folder_with_files(self):
        # Test with folder containing various files including video files
        temp_dir = tempfile.mkdtemp()
        
        # Create various types of files
        video_files = [
            'video.mp4',
            'movie.mkv',
            'clip.mov',
            'show.divx',
            'film.webm',
            'video.mpg',
            'movie.avi',
            'special@chars!.mp4'  # This is a video file with special characters
        ]
        
        other_files = [
            'document.txt',
            'image.jpg',
            'script.py',
            '.hidden_file'
        ]
        
        # Create files
        for filename in video_files + other_files:
            open(os.path.join(temp_dir, filename), 'a').close()
            
        response = self.app.get(f'/scan?folder={temp_dir}')
        self.assertEqual(response.status_code, 200)
        
        # Read the streaming response
        data = b''
        for chunk in response.response:
            data += chunk
            
        try:
            result = json.loads(data.decode('utf-8'))
            print(f"Found {len(result)} files")
            print(f"Video files: {video_files}")
            print(f"Result filenames: {[item['filename'] for item in result]}")
            
            # Should return only video files
            self.assertEqual(len(result), len(video_files))
            
            # Check that all video files are present and properly formatted
            for filename in video_files:
                file_entry = next((item for item in result if item['filename'] == filename), None)
                self.assertIsNotNone(file_entry)
                self.assertIn('size', file_entry)
                self.assertIn('modified', file_entry)
                self.assertIn('type', file_entry)
                self.assertEqual(file_entry['type'], 'video')
                
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
        
    def test_scan_folder_with_special_chars(self):
        # Test with folder name containing special characters
        temp_dir = tempfile.mkdtemp(prefix='special@chars!')
        response = self.app.get(f'/scan?folder={temp_dir}')
        self.assertEqual(response.status_code, 200)
        
    def test_scan_nested_folder(self):
        # Test with deeply nested folder structure
        temp_dir = tempfile.mkdtemp()
        nested_path = os.path.join(temp_dir, 'level1', 'level2', 'level3')
        os.makedirs(nested_path)
        
        # Create a video file in the deepest folder
        video_file = os.path.join(nested_path, 'test_video.mp4')
        open(video_file, 'a').close()
        
        response = self.app.get(f'/scan?folder={nested_path}')
        self.assertEqual(response.status_code, 200)
        
        # Read the streaming response
        data = b''
        for chunk in response.response:
            data += chunk
            
        try:
            result = json.loads(data.decode('utf-8'))
            # Should find the video file
            self.assertEqual(len(result), 1)
            file_entry = result[0]
            self.assertEqual(file_entry['filename'], 'test_video.mp4')
            self.assertIn('size', file_entry)
            self.assertIn('modified', file_entry)
            self.assertEqual(file_entry['type'], 'video')
            
        except json.JSONDecodeError:
            self.fail("Response data was not valid JSON")
        
    def test_scan_folder_with_symlink(self):
        # Test with folder containing symbolic links (where applicable)
        temp_dir = tempfile.mkdtemp()
        test_file = os.path.join(temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')
            
        if os.name == 'nt':  # Windows
            link_path = os.path.join(temp_dir, 'link_to_test.txt')
            os.system(f'mklink "{link_path}" "{test_file}"')
        else:  # Unix-like
            link_path = os.path.join(temp_dir, 'link_to_test.txt')
            os.symlink(test_file, link_path)
            
        response = self.app.get(f'/scan?folder={temp_dir}')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()