"""
Transition application for composer module.

Applies transitions between clips (MVP: simple cuts only).
"""
from pathlib import Path
from typing import List
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from shared.models.scene import Transition
from .utils import run_ffmpeg_command

logger = get_logger("composer.transition_applier")


async def apply_transitions(
    clip_paths: List[Path],
    transitions: List[Transition],
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Apply transitions between clips (MVP: cuts only).
    
    Args:
        clip_paths: List of normalized clip paths (in order)
        transitions: List of transition definitions (ignored in MVP)
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to concatenated video with transitions
    """
    # MVP: Simple concatenation (cuts only)
    # Create concat file for FFmpeg
    concat_file = temp_dir / "clips_concat.txt"
    with open(concat_file, "w") as f:
        for clip_path in clip_paths:
            f.write(f"file '{clip_path.absolute()}'\n")
    
    output_path = temp_dir / "clips_concatenated.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",  # Stream copy (fast, no re-encoding)
        "-y",
        str(output_path)
    ]
    
    logger.info(
        f"Concatenating {len(clip_paths)} clips with cuts",
        extra={"job_id": str(job_id), "clip_count": len(clip_paths)}
    )
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Concatenated video not created: {output_path}")
        
        return output_path
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to concatenate clips: {e}") from e

