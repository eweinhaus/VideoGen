"""
Duration handling for composer module.

Trims clips if too long, loops clips if too short.
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
    Handle clip duration mismatch (trim or loop).
    
    Args:
        clip_path: Path to normalized clip
        clip: Clip object with actual/target durations
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Tuple of (output_path, was_trimmed, was_looped)
    """
    duration_diff = clip.actual_duration - clip.target_duration
    tolerance = DURATION_TOLERANCE
    
    # If duration is close enough, use as-is
    if abs(duration_diff) <= tolerance:
        logger.debug(
            f"Clip {clip.clip_index} duration OK ({clip.actual_duration:.2f}s vs {clip.target_duration:.2f}s)",
            extra={"job_id": str(job_id), "clip_index": clip.clip_index}
        )
        return clip_path, False, False
    
    output_path = temp_dir / f"clip_{clip.clip_index}_duration_fixed.mp4"
    
    # If too long: trim from end
    if duration_diff > tolerance:
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
    
    # If too short: loop entire clip
    else:
        loops_needed = int(clip.target_duration / clip.actual_duration) + 1
        logger.info(
            f"Looping clip {clip.clip_index} {loops_needed}x times ({clip.actual_duration:.2f}s → {clip.target_duration:.2f}s)",
            extra={"job_id": str(job_id), "clip_index": clip.clip_index, "loops": loops_needed}
        )
        
        # Create concat file for FFmpeg
        concat_file = temp_dir / f"clip_{clip.clip_index}_concat.txt"
        with open(concat_file, "w") as f:
            for _ in range(loops_needed):
                f.write(f"file '{clip_path.absolute()}\n")
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-t", str(clip.target_duration),  # Trim to exact target
            "-c", "copy",
            "-y",
            str(output_path)
        ]
        
        try:
            await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
            
            if not output_path.exists():
                raise CompositionError(f"Looped clip not created: {output_path}")
            
            return output_path, False, True
        except Exception as e:
            if isinstance(e, CompositionError):
                raise
            raise CompositionError(f"Failed to loop clip {clip.clip_index}: {e}") from e

