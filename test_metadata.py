#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from utils import get_video_metadata

metadata = get_video_metadata('test_thumbnails/test_video1.mp4')
print(metadata)