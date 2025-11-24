"""
Lipsync Processor configuration.

Centralized configuration for Sync Labs LipSync 2.0 model and processing settings.
"""
import os
from decimal import Decimal
from shared.config import settings
from shared.logging import get_logger

logger = get_logger("lipsync_processor.config")

# Sync Labs LipSync 2.0 model configuration
SYNC_LIPSYNC_MODEL = "sync/lipsync-2"
SYNC_LIPSYNC_VERSION = os.getenv("SYNC_LIPSYNC_VERSION", "latest")

# Legacy support - keep old variable names for backward compatibility
PIXVERSE_LIPSYNC_MODEL = SYNC_LIPSYNC_MODEL
PIXVERSE_LIPSYNC_VERSION = SYNC_LIPSYNC_VERSION

# Processing settings
LIPSYNC_TIMEOUT_SECONDS = int(os.getenv("LIPSYNC_TIMEOUT_SECONDS", "180"))  # 3 minutes
LIPSYNC_MAX_DURATION = 30.0  # Max clip duration in seconds (model limit)
LIPSYNC_MAX_VIDEO_SIZE_MB = 20  # Max video file size in MB (model limit)

# Sync Labs LipSync 2.0 specific settings
LIPSYNC_TEMPERATURE = float(os.getenv("LIPSYNC_TEMPERATURE", "0.95"))  # Temperature control (0-1, default 0.95)
LIPSYNC_SYNC_MODE = os.getenv("LIPSYNC_SYNC_MODE", "silence")  # Sync mode: "silence", "cut_off", "loop", "bounce", "remap"
LIPSYNC_ACTIVE_SPEAKER_DETECTION = os.getenv("LIPSYNC_ACTIVE_SPEAKER_DETECTION", "true").lower() == "true"  # Active speaker detection

# Cost estimation (if not available from Replicate)
LIPSYNC_ESTIMATED_COST = Decimal(os.getenv("LIPSYNC_ESTIMATED_COST", "0.10"))  # $0.10 per clip

# Polling settings
LIPSYNC_POLL_INTERVAL = 3  # Poll every 3 seconds
LIPSYNC_FAST_POLL_INTERVAL = 1  # Fast poll when close to completion (1 second)
LIPSYNC_FAST_POLL_THRESHOLD = 0.8  # Switch to fast polling at 80% of estimated time

# Estimated processing time (for progress tracking)
LIPSYNC_ESTIMATED_TIME_PER_CLIP = 60  # 60 seconds per clip average

logger.info(
    f"Lipsync processor configuration loaded",
    extra={
        "model": SYNC_LIPSYNC_MODEL,
        "version": SYNC_LIPSYNC_VERSION,
        "timeout": LIPSYNC_TIMEOUT_SECONDS,
        "max_duration": LIPSYNC_MAX_DURATION,
        "max_video_size_mb": LIPSYNC_MAX_VIDEO_SIZE_MB,
        "temperature": LIPSYNC_TEMPERATURE,
        "sync_mode": LIPSYNC_SYNC_MODE,
        "active_speaker_detection": LIPSYNC_ACTIVE_SPEAKER_DETECTION,
        "estimated_cost": float(LIPSYNC_ESTIMATED_COST)
    }
)

