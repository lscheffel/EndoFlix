from models import UpdatePlaylist

try:
    u = UpdatePlaylist(name='test', source_folder='C:\\NonExisting')
    print("Validation passed for absolute path")
except Exception as e:
    print(f"Validation failed: {e}")