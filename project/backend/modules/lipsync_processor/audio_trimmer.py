"""
Audio trimming utilities for lipsync processing.

Handles trimming audio files to exact clip boundaries using FFmpeg.
"""
import asyncio
import subprocess
import shutil
from pathlib import Path
from typing import Tuple
from uuid import UUID

from shared.logging import get_logger
from shared.errors import RetryableError
from modules.lipsync_processor.config import LIPSYNC_MAX_DURATION

logger = get_logger("lipsync_processor.audio_trimmer")


async def trim_audio_to_clip(
    audio_bytes: bytes,
    start_time: float,
    end_time: float,
    job_id: UUID,
    temp_dir: Path
) -> Tuple[bytes, float]:
    """
    Trim audio to exact clip boundaries using FFmpeg.
    
    Args:
        audio_bytes: Original audio file bytes
        start_time: Start time in seconds
        end_time: End time in seconds
        job_id: Job ID for logging
        temp_dir: Temporary directory for processing
        
    Returns:
        Tuple of (trimmed_audio_bytes, duration)
        
    Raises:
        RetryableError: If trimming fails (retryable)
        ValueError: If duration exceeds limit (non-retryable)
    """
    duration = end_time - start_time
    
    # Validate duration (pixverse/lipsync max is 30s)
    if duration > LIPSYNC_MAX_DURATION:
        raise ValueError(
            f"Clip duration {duration:.2f}s exceeds {LIPSYNC_MAX_DURATION}s limit for lipsync"
        )
    
    if duration <= 0:
        raise ValueError(f"Invalid duration: {duration}s (start={start_time}s, end={end_time}s)")
    
    # Check if FFmpeg is available
    if not shutil.which("ffmpeg"):
        raise RetryableError("FFmpeg is not available for audio trimming")
    
    # Create temporary input file
    input_path = temp_dir / f"audio_input_{job_id}.mp3"
    output_path = temp_dir / f"audio_trimmed_{job_id}.mp3"
    
    try:
        # Write input audio to temp file
        input_path.write_bytes(audio_bytes)
        
        logger.info(
            f"Trimming audio: {start_time:.2f}s to {end_time:.2f}s (duration: {duration:.2f}s)",
            extra={
                "job_id": str(job_id),
                "start": start_time,
                "end": end_time,
                "duration": duration
            }
        )
        
        # FFmpeg command to trim audio
        # -ss: seek to start time
        # -t: duration to extract
        # -c:a copy: copy audio codec (fast, no re-encoding)
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-ss", str(start_time),
            "-t", str(duration),
            "-c:a", "copy",  # Copy audio stream (fast)
            "-y",  # Overwrite output
            str(output_path)
        ]
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"Failed to trim audio: {error_msg}",
                extra={"job_id": str(job_id), "error": error_msg}
            )
            raise RetryableError(f"Audio trimming failed: {error_msg}")
        
        # Read trimmed audio
        if not output_path.exists():
            raise RetryableError(f"Trimmed audio file not created: {output_path}")
        
        trimmed_bytes = output_path.read_bytes()
        
        logger.info(
            f"Audio trimmed successfully: {len(trimmed_bytes)} bytes",
            extra={
                "job_id": str(job_id),
                "size": len(trimmed_bytes),
                "duration": duration
            }
        )
        
        return trimmed_bytes, duration
        
    except asyncio.TimeoutError:
        logger.error(
            "Audio trimming timeout after 60s",
            extra={"job_id": str(job_id)}
        )
        raise RetryableError("Audio trimming timeout after 60s")
    except ValueError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        logger.error(
            f"Error trimming audio: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        raise RetryableError(f"Audio trimming error: {str(e)}") from e
    finally:
        # Cleanup temp files
        for path in [input_path, output_path]:
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass

