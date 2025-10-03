#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '.')
from utils import get_video_metadata_cached as get_video_metadata

file_path = 'test_thumbnails/test_video1.mp4'
stats = os.stat(file_path)
metadata = get_video_metadata(file_path, stats.st_size, stats.st_mtime)
print(metadata)