from models import UpdatePlaylist

try:
    u = UpdatePlaylist(name='test', source_folder='C:\\NonExisting')
    print("Validation passed for absolute path - UNEXPECTED")
except Exception as e:
    print(f"Validation failed as expected: {e}")

# Test that relative paths work
try:
    u = UpdatePlaylist(name='test', source_folder='relative/path')
    print("Validation passed for relative path")
except Exception as e:
    print(f"Validation failed unexpectedly for relative path: {e}")