"""
Clip normalization for composer module.

Upscales clips to 1080p and normalizes to 30 FPS, but only if needed.
Uses stream copy when possible to avoid unnecessary re-encoding.
"""
from pathlib import Path
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command, get_video_properties
from .config import FFMPEG_THREADS, FFMPEG_PRESET, FFMPEG_CRF, OUTPUT_FPS

logger = get_logger("composer.normalizer")


async def normalize_clip(
    clip_bytes: bytes,
    clip_index: int,
    temp_dir: Path,
    job_id: UUID,
    target_width: int,
    target_height: int
) -> Path:
    """
    Normalize clip to target resolution and 30 FPS if needed.
    
    Checks video properties first and only re-encodes if resolution or FPS
    don't match target. Uses stream copy when possible for speed.
    
    Args:
        clip_bytes: Original clip file bytes
        clip_index: Clip index for naming
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        target_width: Target output width in pixels
        target_height: Target output height in pixels
        
    Returns:
        Path to normalized clip file (may be same as input if already normalized)
        
    Raises:
        CompositionError: If normalization fails
    """
    # Write input clip to temp file
    input_path = temp_dir / f"clip_{clip_index}_input.mp4"
    output_path = temp_dir / f"clip_{clip_index}_normalized.mp4"
    
    input_path.write_bytes(clip_bytes)
    
    # Check if normalization is needed
    props = await get_video_properties(input_path)
    needs_resize = (props.get("width") != target_width or props.get("height") != target_height)
    needs_fps_change = (props.get("fps") is not None and abs(props.get("fps") - OUTPUT_FPS) > 0.5)
    
    if not needs_resize and not needs_fps_change:
        # Already at target resolution and FPS, use as-is
        logger.info(
            f"Clip {clip_index} already normalized ({props.get('width')}x{props.get('height')} @ {props.get('fps')}fps), using as-is",
            extra={"job_id": str(job_id), "clip_index": clip_index}
        )
        return input_path
    
    # Build filter based on what's needed
    filters = []
    if needs_resize:
        # Use aspect-ratio-preserving scale with letterboxing/pillarboxing
        # This ensures videos maintain their aspect ratio and are padded if needed
        # force_original_aspect_ratio=decrease: scales down to fit, adds padding
        # force_original_aspect_ratio=increase: scales up to fill, may crop (we use decrease for safety)
        filters.append(
            f"scale={target_width}:{target_height}:"
            f"force_original_aspect_ratio=decrease:"
            f"flags=lanczos,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    if needs_fps_change:
        filters.append(f"fps={OUTPUT_FPS}")
    
    filter_str = ",".join(filters) if filters else None
    
    # FFmpeg command: upscale to 1080p and/or normalize to 30 FPS
    ffmpeg_cmd = [
        "ffmpeg",
        "-threads", str(FFMPEG_THREADS),
        "-i", str(input_path),
    ]
    
    if filter_str:
        ffmpeg_cmd.extend(["-vf", filter_str])
    
    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-preset", FFMPEG_PRESET,
        "-crf", str(FFMPEG_CRF),
        "-y",  # Overwrite output
        str(output_path)
    ])
    
    logger.info(
        f"Normalizing clip {clip_index} ({props.get('width')}x{props.get('height')} @ {props.get('fps')}fps → {target_width}x{target_height} @ {OUTPUT_FPS}fps)",
        extra={"job_id": str(job_id), "clip_index": clip_index, "target_width": target_width, "target_height": target_height}
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

