"""
Clip normalization for composer module.

Upscales clips to 1080p and normalizes to 30 FPS.
"""
from pathlib import Path
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command
from .config import FFMPEG_THREADS, FFMPEG_PRESET, FFMPEG_CRF, OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS

logger = get_logger("composer.normalizer")


async def normalize_clip(
    clip_bytes: bytes,
    clip_index: int,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Normalize clip to 1080p, 30 FPS.
    
    Args:
        clip_bytes: Original clip file bytes
        clip_index: Clip index for naming
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to normalized clip file
        
    Raises:
        CompositionError: If normalization fails
    """
    # Write input clip to temp file
    input_path = temp_dir / f"clip_{clip_index}_input.mp4"
    output_path = temp_dir / f"clip_{clip_index}_normalized.mp4"
    
    input_path.write_bytes(clip_bytes)
    
    # FFmpeg command: upscale to 1080p, normalize to 30 FPS
    ffmpeg_cmd = [
        "ffmpeg",
        "-threads", str(FFMPEG_THREADS),
        "-i", str(input_path),
        "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:flags=lanczos,fps={OUTPUT_FPS}",
        "-c:v", "libx264",
        "-preset", FFMPEG_PRESET,
        "-crf", str(FFMPEG_CRF),
        "-y",  # Overwrite output
        str(output_path)
    ]
    
    logger.info(
        f"Normalizing clip {clip_index}",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Normalized clip not created: {output_path}")
        
        logger.info(
            f"Normalized clip {clip_index}",
            extra={"job_id": str(job_id), "clip_index": clip_index}
        )
        
        return output_path
        
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to normalize clip {clip_index}: {e}") from e

