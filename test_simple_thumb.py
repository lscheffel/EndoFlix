#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '.')
from thumbnail_processor import ThumbnailProcessor

# Test the generate_thumbnail function directly
processor = ThumbnailProcessor()

video_path = "test_thumbnails/test_video1.mp4"
output_path = "test_thumbnails/test_thumb.webp"

# Get file stats for metadata function
stats = os.stat(video_path)

try:
    result = processor.generate_thumbnail(
        video_path=video_path,
        output_path=output_path,
        thumb_size=50,
        thumb_quality=80,
        extraction_point=0.1,
        ffmpeg_timeout=60
    )

    print(f"Thumbnail generation result: {result}")

    if result:
        if os.path.exists(output_path):
            print(f"Thumbnail file created: {output_path}")
            file_size = os.path.getsize(output_path)
            print(f"File size: {file_size} bytes")
        else:
            print("Thumbnail file not found!")
    else:
        print("Thumbnail generation failed!")
except Exception as e:
    print(f"Exception during thumbnail generation: {e}")
    import traceback
    traceback.print_exc()