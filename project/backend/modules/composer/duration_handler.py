"""
Duration handling for composer module.

Trims clips if too long. Clips that are too short are used as-is (no looping).
"""
from pathlib import Path
from typing import Tuple
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from shared.models.video import Clip
from .utils import run_ffmpeg_command
from .config import DURATION_TOLERANCE

logger = get_logger("composer.duration_handler")


async def handle_clip_duration(
    clip_path: Path,
    clip: Clip,
    temp_dir: Path,
    job_id: UUID
) -> Tuple[Path, bool, bool]:
    """
    Handle clip duration mismatch (trim if too long, use as-is if too short).
    
    Clips are concatenated as-is without looping. If a clip is shorter than
    its target duration, it will be used at its actual length.
    
    Args:
        clip_path: Path to normalized clip
        clip: Clip object with actual/target durations
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Tuple of (output_path, was_trimmed, was_looped)
        Note: was_looped will always be False as looping is disabled
    """
    duration_diff = clip.actual_duration - clip.target_duration
    tolerance = DURATION_TOLERANCE
    
    # If duration is close enough or too short, use as-is (no looping)
    if duration_diff <= tolerance:
        if duration_diff < -tolerance:
            logger.info(
                f"Clip {clip.clip_index} is shorter than target ({clip.actual_duration:.2f}s vs {clip.target_duration:.2f}s), using as-is",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index}
            )
        else:
            logger.debug(
                f"Clip {clip.clip_index} duration OK ({clip.actual_duration:.2f}s vs {clip.target_duration:.2f}s)",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index}
            )
        return clip_path, False, False
    
    # If too long: trim from end
    output_path = temp_dir / f"clip_{clip.clip_index}_duration_fixed.mp4"
    logger.info(
        f"Trimming clip {clip.clip_index} from {clip.actual_duration:.2f}s to {clip.target_duration:.2f}s",
        extra={"job_id": str(job_id), "clip_index": clip.clip_index}
    )
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(clip_path),
        "-t", str(clip.target_duration),  # Trim to target duration
        "-c", "copy",  # Stream copy (fast, no re-encoding)
        "-y",
        str(output_path)
    ]
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Trimmed clip not created: {output_path}")
        
        return output_path, True, False
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to trim clip {clip.clip_index}: {e}") from e

