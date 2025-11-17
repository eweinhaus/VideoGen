"""
Audio synchronization for composer module.

Syncs original audio with video.
"""
from pathlib import Path
from typing import Tuple
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command, get_video_duration, get_audio_duration
from .config import OUTPUT_AUDIO_BITRATE

logger = get_logger("composer.audio_syncer")


async def sync_audio(
    video_path: Path,
    audio_bytes: bytes,
    temp_dir: Path,
    job_id: UUID
) -> Tuple[Path, float]:
    """
    Sync audio with video.
    
    Args:
        video_path: Path to video file (without audio)
        audio_bytes: Original audio file bytes
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Tuple of (output_path, sync_drift)
    """
    # Write audio to temp file
    # Note: Audio format is assumed to be MP3, but FFmpeg handles other formats (WAV, M4A, etc.)
    audio_path = temp_dir / "audio.mp3"
    audio_path.write_bytes(audio_bytes)
    
    output_path = temp_dir / "video_with_audio.mp4"
    
    # Get audio duration first - this is our source of truth
    # Audio clips were spliced from this audio file, so we anchor to its duration
    audio_duration = await get_audio_duration(audio_path)
    
    # FFmpeg command: combine video + audio
    # Video should already be padded to match audio length exactly
    # Use -t to explicitly set duration to audio length (ensures exact match to audio)
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",  # Copy video (no re-encoding)
        "-c:a", "aac",   # Encode audio to AAC
        "-b:a", OUTPUT_AUDIO_BITRATE,  # Audio bitrate
        "-t", str(audio_duration),  # Set duration to audio length (video should already match after padding)
        "-y",
        str(output_path)
    ]
    
    logger.info("Syncing audio with video", extra={"job_id": str(job_id)})
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Video with audio not created: {output_path}")
        
        # Measure sync drift (use ffprobe to get durations)
        video_duration = await get_video_duration(output_path)
        audio_duration = await get_audio_duration(audio_path)
        sync_drift = abs(video_duration - audio_duration)
        
        logger.info(
            f"Audio synced (drift: {sync_drift:.3f}s)",
            extra={"job_id": str(job_id), "sync_drift": sync_drift}
        )
        
        return output_path, sync_drift
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to sync audio: {e}") from e

