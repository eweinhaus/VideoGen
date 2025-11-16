"""
Final video encoding for composer module.

Encodes final MP4 with H.264/AAC at 5000k bitrate.
"""
from pathlib import Path
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command, get_video_duration
from .config import (
    FFMPEG_THREADS,
    OUTPUT_VIDEO_CODEC,
    OUTPUT_AUDIO_CODEC,
    OUTPUT_VIDEO_BITRATE,
    OUTPUT_AUDIO_BITRATE,
    FFMPEG_PRESET
)

logger = get_logger("composer.encoder")


async def encode_final_video(
    video_path: Path,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Encode final video with H.264/AAC at 5000k bitrate.
    
    Args:
        video_path: Path to video with audio
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to final encoded video
    """
    output_path = temp_dir / "final_video.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-threads", str(FFMPEG_THREADS),
        "-i", str(video_path),
        "-c:v", OUTPUT_VIDEO_CODEC,      # H.264 codec
        "-c:a", OUTPUT_AUDIO_CODEC,          # AAC codec
        "-b:v", OUTPUT_VIDEO_BITRATE,        # Video bitrate
        "-b:a", OUTPUT_AUDIO_BITRATE,         # Audio bitrate
        "-preset", FFMPEG_PRESET,    # Encoding preset
        "-movflags", "+faststart",  # Web optimization
        "-y",
        str(output_path)
    ]
    
    logger.info("Encoding final video", extra={"job_id": str(job_id)})
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        # Validate output
        if not output_path.exists():
            raise CompositionError("Final video not created")
        
        output_size = output_path.stat().st_size
        if output_size < 1024:  # Less than 1KB is suspicious
            raise CompositionError(f"Final video too small: {output_size} bytes")
        
        # Validate video properties (optional but recommended)
        video_duration = await get_video_duration(output_path)
        if video_duration <= 0:
            raise CompositionError(f"Invalid video duration: {video_duration}s")
        
        logger.info(
            f"Final video encoded ({output_size / 1024 / 1024:.2f} MB)",
            extra={"job_id": str(job_id), "size_mb": output_size / 1024 / 1024}
        )
        
        return output_path
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to encode final video: {e}") from e

