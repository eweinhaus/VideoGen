"""
Utility functions for composer module.

FFmpeg command execution, duration extraction, and availability checks.
"""
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import List
from uuid import UUID

from shared.errors import CompositionError, RetryableError
from shared.retry import retry_with_backoff
from shared.logging import get_logger

logger = get_logger("composer.utils")


def check_ffmpeg_available() -> bool:
    """
    Check if FFmpeg is installed and available in PATH.
    
    Returns:
        True if FFmpeg is available, False otherwise
    """
    return shutil.which("ffmpeg") is not None


@retry_with_backoff(max_attempts=2, base_delay=2)
async def run_ffmpeg_command(
    cmd: List[str],
    job_id: UUID,
    timeout: int = 300
) -> None:
    """
    Run FFmpeg command with retry logic.
    
    Args:
        cmd: FFmpeg command as list of strings
        job_id: Job ID for logging
        timeout: Timeout in seconds (default: 300)
        
    Raises:
        CompositionError: If command fails after retries
        RetryableError: If transient failure (will retry)
    """
    logger.info(
        f"Running FFmpeg command: {' '.join(cmd)}",
        extra={"job_id": str(job_id), "command": cmd}
    )
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"FFmpeg command failed: {error_msg}",
                extra={"job_id": str(job_id), "error": error_msg, "command": cmd}
            )
            # All FFmpeg errors are retryable (system load, disk I/O, etc.)
            raise RetryableError(f"FFmpeg command failed: {error_msg}")
        
    except asyncio.TimeoutError:
        raise RetryableError(f"FFmpeg command timeout after {timeout}s")
    except RetryableError:
        raise  # Re-raise for retry logic
    except Exception as e:
        raise CompositionError(f"FFmpeg command failed: {e}") from e


async def get_video_duration(video_path: Path) -> float:
    """
    Get video duration using ffprobe. Reuse pattern from video_generator.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Duration in seconds, falls back to 5.0 if fails
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        duration = float(result.stdout.strip())
        return duration
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as e:
        logger.warning(
            f"Failed to get video duration: {e}, using estimate",
            extra={"video_path": str(video_path)}
        )
        return 5.0  # Default estimate


async def get_audio_duration(audio_path: Path) -> float:
    """
    Get audio duration using ffprobe (same as get_video_duration).
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Duration in seconds, falls back to 5.0 if fails
    """
    return await get_video_duration(audio_path)


async def get_video_properties(video_path: Path) -> dict:
    """
    Get video properties (width, height, fps) using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with width, height, fps, or None values if extraction fails
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        lines = result.stdout.strip().split('\n')
        width = int(lines[0]) if lines[0] else None
        height = int(lines[1]) if lines[1] else None
        
        # Parse fps from fraction (e.g., "30/1" -> 30.0)
        fps = None
        if len(lines) > 2 and lines[2]:
            fps_str = lines[2].strip()
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else None
            else:
                fps = float(fps_str)
        
        return {
            "width": width,
            "height": height,
            "fps": fps
        }
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired, IndexError) as e:
        logger.warning(
            f"Failed to get video properties: {e}, will re-encode",
            extra={"video_path": str(video_path)}
        )
        return {"width": None, "height": None, "fps": None}

