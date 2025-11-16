"""
Composer configuration.

Centralized configuration for storage buckets, FFmpeg settings, and output parameters.
"""

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

