"""
Duration handling for composer module.

Trims clips if too long. Short clips are handled by cascading compensation.
"""
from pathlib import Path
from typing import Tuple, List, Dict, Any
from uuid import UUID
import os

from shared.errors import CompositionError
from shared.logging import get_logger
from shared.models.video import Clip
from .utils import run_ffmpeg_command, get_video_duration
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
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    return output_path, True, False


async def handle_cascading_durations(
    clip_paths: List[Path],
    clips: List[Clip],
    temp_dir: Path,
    job_id: UUID
) -> Tuple[List[Path], Dict[str, Any]]:
    """
    Handle duration mismatches with cascading compensation.
    
    Each clip compensates for previous clip's shortfall by extending its target duration.
    If a clip is long enough to cover the extended target, it's trimmed to that duration.
    If still too short, the shortfall cascades to the next clip.
    
    Args:
        clip_paths: List of normalized clip paths (must be in same order as clips)
        clips: List of Clip objects with actual/target durations (must be sorted by clip_index)
        temp_dir: Temporary directory for output files
        job_id: Job ID for logging
        
    Returns:
        Tuple of (final_clip_paths, metrics_dict) where metrics contains:
        - clips_trimmed: Number of clips that were trimmed
        - total_shortfall: Final shortfall after all clips (in seconds)
        - compensation_applied: List of compensation events with clip_index, original_target,
          extended_target, and compensation amount
    """
    cumulative_shortfall = 0.0
    final_paths = []
    metrics = {
        "clips_trimmed": 0,
        "total_shortfall": 0.0,
        "compensation_applied": []
    }
    
    # Use original_target_duration for total intended (before buffer was applied)
    total_intended = sum(
        (c.original_target_duration if c.original_target_duration is not None else c.target_duration)
        for c in clips
    )
    logger.info(
        f"Starting cascading compensation for {len(clips)} clips, total intended duration: {total_intended:.2f}s",
        extra={"job_id": str(job_id), "clip_count": len(clips), "total_intended": total_intended}
    )
    
    for i, (clip_path, clip) in enumerate(zip(clip_paths, clips)):
        # Use original_target_duration for compensation (before buffer was applied)
        # Fallback to target_duration for backward compatibility
        target = clip.original_target_duration if clip.original_target_duration is not None else clip.target_duration
        actual = clip.actual_duration
        
        if i == 0:
            # First clip: use full actual duration, track shortfall
            shortfall = max(0.0, target - actual)
            cumulative_shortfall = shortfall
            final_paths.append(clip_path)
            
            if shortfall > 0:
                logger.info(
                    f"Clip {i} shortfall: {shortfall:.2f}s (target: {target:.2f}s, actual: {actual:.2f}s)",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "target": target,
                        "actual": actual,
                        "shortfall": shortfall
                    }
                )
        else:
            # Subsequent clips: compensate for previous shortfalls
            extended_target = target + cumulative_shortfall
            
            if actual >= extended_target:
                # Clip is long enough: trim to extended duration
                output_path = temp_dir / f"clip_{i}_compensated.mp4"
                
                logger.info(
                    f"Compensating clip {i}: extending target from {target:.2f}s to {extended_target:.2f}s "
                    f"(compensation: {cumulative_shortfall:.2f}s), trimming from {actual:.2f}s",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "original_target": target,
                        "extended_target": extended_target,
                        "actual": actual,
                        "compensation": cumulative_shortfall
                    }
                )
                
                # FFmpeg trim command (trim from end, use stream copy for speed)
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(clip_path),
                    "-t", str(extended_target),  # Trim to extended target
                    "-c", "copy",  # Stream copy (fast, no re-encoding)
                    "-y",
                    str(output_path)
                ]
                
                try:
                    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
                    
                    if not output_path.exists():
                        raise CompositionError(f"Compensated clip not created: {output_path}")
                    
                    final_paths.append(output_path)
                    metrics["clips_trimmed"] += 1
                    metrics["compensation_applied"].append({
                        "clip_index": i,
                        "original_target": target,
                        "extended_target": extended_target,
                        "compensation": cumulative_shortfall
                    })
                    cumulative_shortfall = 0.0  # Reset
                except Exception as e:
                    if isinstance(e, CompositionError):
                        raise
                    raise CompositionError(f"Failed to compensate clip {i}: {e}") from e
            else:
                # Clip still too short: use full duration, continue cascading
                remaining_shortfall = extended_target - actual
                cumulative_shortfall = remaining_shortfall
                final_paths.append(clip_path)
                
                logger.info(
                    f"Clip {i} still short after compensation: remaining shortfall {remaining_shortfall:.2f}s "
                    f"(extended target: {extended_target:.2f}s, actual: {actual:.2f}s)",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "extended_target": extended_target,
                        "actual": actual,
                        "remaining_shortfall": remaining_shortfall
                    }
                )
    
    metrics["total_shortfall"] = cumulative_shortfall
    
    total_actual = sum(c.actual_duration for c in clips)
    shortfall_pct = (cumulative_shortfall / total_intended * 100) if total_intended > 0 else 0.0
    
    logger.info(
        f"Cascading compensation complete: {metrics['clips_trimmed']} clips trimmed, "
        f"final shortfall: {cumulative_shortfall:.2f}s ({shortfall_pct:.1f}%)",
        extra={
            "job_id": str(job_id),
            "clips_trimmed": metrics["clips_trimmed"],
            "total_shortfall": cumulative_shortfall,
            "shortfall_percentage": shortfall_pct,
            "total_intended": total_intended,
            "total_actual": total_actual
        }
    )
    
    return final_paths, metrics


async def extend_last_clip(
    clip_path: Path,
    shortfall_seconds: float,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Extend last clip to cover shortfall using hybrid method.
    
    - Shortfall <2s: Freeze last frame using tpad filter
    - Shortfall ≥2s: Loop last 1-2 seconds of clip
    - Maximum extension: 5s (fail if more needed)
    
    Args:
        clip_path: Path to last clip
        shortfall_seconds: Amount of time to extend (in seconds)
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to extended clip
        
    Raises:
        CompositionError: If shortfall exceeds maximum extension or extension fails
    """
    max_extension = float(os.getenv("MAX_LAST_CLIP_EXTENSION", "5.0"))
    extension_threshold = float(os.getenv("EXTENSION_METHOD_THRESHOLD", "2.0"))
    # Option to disable looping entirely (only use freeze frames)
    disable_looping = os.getenv("DISABLE_LAST_CLIP_LOOPING", "false").lower() == "true"
    
    if shortfall_seconds > max_extension:
        raise CompositionError(
            f"Shortfall {shortfall_seconds:.2f}s exceeds maximum extension {max_extension}s"
        )
    
    output_path = temp_dir / "last_clip_extended.mp4"
    
    # If looping is disabled, always use freeze frame regardless of shortfall size
    if shortfall_seconds < extension_threshold or disable_looping:
        # Freeze last frame
        method_note = " (looping disabled)" if disable_looping and shortfall_seconds >= extension_threshold else ""
        logger.info(
            f"Extending last clip by {shortfall_seconds:.2f}s using freeze frame{method_note}",
            extra={
                "job_id": str(job_id),
                "extension_method": "freeze",
                "shortfall": shortfall_seconds,
                "looping_disabled": disable_looping
            }
        )
        
        # Get last frame and extend it using tpad filter
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(clip_path),
            "-vf", f"tpad=stop_mode=clone:stop_duration={shortfall_seconds}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-y",
            str(output_path)
        ]
    else:
        # Loop last 1-2 seconds
        logger.info(
            f"Extending last clip by {shortfall_seconds:.2f}s using loop",
            extra={"job_id": str(job_id), "extension_method": "loop", "shortfall": shortfall_seconds}
        )
        
        # Extract last segment (1-2 seconds)
        loop_duration = min(2.0, shortfall_seconds)
        loops_needed = int(shortfall_seconds / loop_duration) + 1
        
        # Extract last segment
        last_segment = temp_dir / "last_segment.mp4"
        extract_cmd = [
            "ffmpeg",
            "-sseof", f"-{loop_duration}",
            "-i", str(clip_path),
            "-t", str(loop_duration),
            "-c", "copy",
            "-y",
            str(last_segment)
        ]
        
        try:
            await run_ffmpeg_command(extract_cmd, job_id=job_id, timeout=300)
            
            if not last_segment.exists():
                raise CompositionError(f"Last segment not extracted: {last_segment}")
        except Exception as e:
            if isinstance(e, CompositionError):
                raise
            raise CompositionError(f"Failed to extract last segment: {e}") from e
        
        # Create concat file with original clip + looped segment
        concat_file = temp_dir / "last_clip_extend_concat.txt"
        with open(concat_file, "w") as f:
            f.write(f"file '{clip_path.absolute()}'\n")
            # Add looped segment multiple times
            for _ in range(loops_needed):
                f.write(f"file '{last_segment.absolute()}'\n")
        
        # Get original clip duration and calculate target
        original_duration = await get_video_duration(clip_path)
        target_duration = original_duration + shortfall_seconds
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-t", str(target_duration),
            "-c", "copy",
            "-y",
            str(output_path)
        ]
    
    try:
        await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Extended clip not created: {output_path}")
        
        output_size = output_path.stat().st_size
        if output_size < 1024:  # Less than 1KB is suspicious
            raise CompositionError(f"Extended clip too small: {output_size} bytes")
        
        logger.info(
            f"Last clip extended successfully: {shortfall_seconds:.2f}s, output size: {output_size / 1024 / 1024:.2f} MB",
            extra={
                "job_id": str(job_id),
                "shortfall": shortfall_seconds,
                "output_size_mb": output_size / 1024 / 1024
            }
        )
        
        return output_path
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to extend last clip: {e}") from e

