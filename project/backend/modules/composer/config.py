"""
Composer configuration.

Centralized configuration for storage buckets, FFmpeg settings, and output parameters.
"""
import os
from typing import Tuple

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


def get_output_dimensions_from_aspect_ratio(aspect_ratio: str = "16:9") -> Tuple[int, int]:
    """
    Get output width and height from aspect ratio.
    
    Uses standard resolutions for each aspect ratio:
    - 16:9 -> 1920x1080 (1080p)
    - 9:16 -> 1080x1920 (vertical/portrait)
    - 1:1 -> 1080x1080 (square)
    - 4:3 -> 1440x1080
    - 3:4 -> 1080x1440 (vertical)
    
    Args:
        aspect_ratio: Aspect ratio string (e.g., "16:9", "9:16", "1:1")
        
    Returns:
        Tuple of (width, height) in pixels
        
    Raises:
        ValueError: If aspect ratio is not supported
    """
    # Parse aspect ratio
    try:
        parts = aspect_ratio.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid aspect ratio format: {aspect_ratio}")
        width_ratio = float(parts[0])
        height_ratio = float(parts[1])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid aspect ratio format: {aspect_ratio}") from e
    
    # Standard resolutions for each aspect ratio (maintaining 1080p quality)
    aspect_ratio_map = {
        "16:9": (1920, 1080),   # Standard widescreen (1080p)
        "9:16": (1080, 1920),   # Vertical/portrait (TikTok/Instagram Stories)
        "1:1": (1080, 1080),    # Square (Instagram post)
        "4:3": (1440, 1080),    # Classic TV/computer monitor
        "3:4": (1080, 1440),    # Vertical portrait (Instagram portrait)
    }
    
    # Check if we have a standard resolution
    if aspect_ratio in aspect_ratio_map:
        return aspect_ratio_map[aspect_ratio]
    
    # Calculate dimensions for custom aspect ratios (maintain 1080p height for landscape, width for portrait)
    if width_ratio >= height_ratio:
        # Landscape: maintain 1080p height, calculate width
        height = 1080
        width = int(height * (width_ratio / height_ratio))
        # Round to nearest multiple of 2 (required for video codecs)
        width = (width // 2) * 2
    else:
        # Portrait: maintain 1080p width, calculate height
        width = 1080
        height = int(width * (height_ratio / width_ratio))
        # Round to nearest multiple of 2
        height = (height // 2) * 2
    
    return (width, height)

