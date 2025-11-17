"""
Composer configuration.

Centralized configuration for storage buckets, FFmpeg settings, and output parameters.
"""
import os

# Storage bucket names
VIDEO_CLIPS_BUCKET = "video-clips"
VIDEO_OUTPUTS_BUCKET = "video-outputs"
AUDIO_UPLOADS_BUCKET = "audio-uploads"

# FFmpeg settings
FFMPEG_THREADS = 4
FFMPEG_TIMEOUT = 300  # 5 minutes
FFMPEG_PRESET = "medium"  # Balance speed/quality
FFMPEG_CRF = 23  # High quality

# Video output settings
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_FPS = 30
OUTPUT_VIDEO_BITRATE = "5000k"
OUTPUT_AUDIO_BITRATE = "192k"
OUTPUT_VIDEO_CODEC = "libx264"
OUTPUT_AUDIO_CODEC = "aac"

# Duration handling
DURATION_TOLERANCE = 0.5  # 0.5s tolerance for duration matching

# Cascading duration compensation configuration
MAX_SHORTFALL_PERCENTAGE = float(os.getenv("MAX_SHORTFALL_PERCENTAGE", "10.0"))  # Maximum acceptable shortfall (default: 10%)
EXTEND_LAST_CLIP_THRESHOLD = float(os.getenv("EXTEND_LAST_CLIP_THRESHOLD", "20.0"))  # Threshold for extending last clip (default: 20%)
FAIL_JOB_THRESHOLD = float(os.getenv("FAIL_JOB_THRESHOLD", "50.0"))  # Threshold for failing job (default: 50%)
USE_CASCADING_COMPENSATION = os.getenv("USE_CASCADING_COMPENSATION", "true").lower() == "true"  # Feature flag (default: true)
MAX_LAST_CLIP_EXTENSION = float(os.getenv("MAX_LAST_CLIP_EXTENSION", "5.0"))  # Maximum extension for last clip in seconds (default: 5.0)
EXTENSION_METHOD_THRESHOLD = float(os.getenv("EXTENSION_METHOD_THRESHOLD", "2.0"))  # Freeze vs loop threshold (default: 2.0s)

