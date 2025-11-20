"""
Main entry point for composer module.

Orchestrates video composition: downloads, normalizes, handles durations,
applies transitions, syncs audio, encodes, and uploads final video.
"""
import asyncio
import time
import tempfile
import shutil
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
from typing import List, Optional
from decimal import Decimal

from shared.errors import CompositionError, RetryableError
from shared.logging import get_logger
from shared.storage import StorageClient
from shared.models.video import VideoOutput, Clips, Clip
from shared.models.scene import Transition
from api_gateway.services.event_publisher import publish_event
from api_gateway.services.sse_manager import broadcast_event
from shared.database import DatabaseClient
from shared.redis_client import RedisClient

from .config import VIDEO_OUTPUTS_BUCKET, get_output_dimensions_from_aspect_ratio
from .utils import check_ffmpeg_available, get_video_duration
from .downloader import download_all_clips, download_audio
from .normalizer import normalize_clip
from .duration_handler import handle_cascading_durations, extend_last_clip
from .transition_applier import apply_transitions
from .video_padder import pad_video_to_audio
from .audio_syncer import sync_audio
from .encoder import encode_final_video

logger = get_logger("composer.process")

db_client = DatabaseClient()
redis_client = RedisClient()


@asynccontextmanager
async def temp_directory(prefix: str):
    """
    Context manager for temporary directory with automatic cleanup.
    
    Args:
        prefix: Prefix for temp directory name
        
    Yields:
        Path to temporary directory
    """
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def publish_progress(job_id: UUID, message: str, progress: Optional[int] = None) -> None:
    """
    Publish progress event via SSE.
    
    Args:
        job_id: Job ID
        message: Progress message
        progress: Optional progress percentage (85-100 for composer)
    """
    await publish_event(
        str(job_id),
        "message",
        {
            "text": message,
            "stage": "composer"
        }
    )
    
    # Also publish progress update if provided
    if progress is not None:
        progress_data = {
            "progress": progress,
            "stage": "composer"
        }
        await publish_event(str(job_id), "progress", progress_data)
        await broadcast_event(str(job_id), "progress", progress_data)
        
        # Also update database for persistence
        try:
            await db_client.table("jobs").update({
                "progress": progress,
                "current_stage": "composer",
                "updated_at": "now()"
            }).eq("id", str(job_id)).execute()
            
            # Invalidate cache (job_id is UUID, convert to string)
            cache_key = f"job_status:{str(job_id)}"
            await redis_client.client.delete(cache_key)
        except Exception as e:
            logger.warning(f"Failed to update progress in database: {e}", extra={"job_id": str(job_id)})


async def process(
    job_id: str,
    clips: Clips,
    audio_url: str,
    transitions: List[Transition],
    beat_timestamps: Optional[List[float]] = None,
    aspect_ratio: str = "16:9",
    changed_clip_index: Optional[int] = None
) -> VideoOutput:
    """
    Main composition function.
    
    Args:
        job_id: Job identifier (string from orchestrator, converted to UUID internally)
        clips: Collection of generated video clips from Video Generator
        audio_url: Original audio file URL
        transitions: Transition definitions from Scene Planner (ignored in MVP)
        beat_timestamps: Beat timestamps from Audio Parser (optional, not used in MVP)
        aspect_ratio: Aspect ratio for final video output (default: "16:9")
        changed_clip_index: Optional index of clip that changed (for future optimization)
        
    Returns:
        VideoOutput with final video URL and metadata
        
    Raises:
        CompositionError: For permanent failures (validation, FFmpeg errors)
        RetryableError: For transient failures (network, timeouts)
        
    Note:
        FFMPEG_PRESET is set to "fast" by default for faster recomposition (15-25% faster than medium).
        Can be overridden via FFMPEG_PRESET environment variable if needed.
    """
    # Convert job_id to UUID for internal use
    job_id_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
    start_time = time.time()
    
    # Calculate output dimensions from aspect ratio
    try:
        output_width, output_height = get_output_dimensions_from_aspect_ratio(aspect_ratio)
        logger.info(
            f"Using aspect ratio '{aspect_ratio}' -> {output_width}x{output_height}",
            extra={"job_id": str(job_id_uuid), "aspect_ratio": aspect_ratio, "width": output_width, "height": output_height}
        )
    except ValueError as e:
        logger.warning(
            f"Invalid aspect ratio '{aspect_ratio}', falling back to 16:9 (1920x1080): {e}",
            extra={"job_id": str(job_id_uuid), "aspect_ratio": aspect_ratio}
        )
        output_width, output_height = 1920, 1080
        aspect_ratio = "16:9"  # Reset to default
    
    # Initialize timing tracking
    timings = {
        "download_clips": 0.0,
        "normalize_clips": 0.0,
        "handle_durations": 0.0,
        "apply_transitions": 0.0,
        "pad_video": 0.0,
        "sync_audio": 0.0,
        "encode_final": 0.0,
        "upload_final": 0.0,
        "total": 0.0
    }
    
    # Initialize compensation metrics (will be populated during duration handling)
    duration_metrics = {
        "clips_trimmed": 0,
        "total_shortfall": 0.0,
        "compensation_applied": []
    }
    total_intended = 0.0
    
    try:
        # Step 1: Input validation
        if not check_ffmpeg_available():
            raise CompositionError(
                "FFmpeg not found. Please install FFmpeg:\n"
                "  macOS: brew install ffmpeg\n"
                "  Linux: apt-get install ffmpeg or yum install ffmpeg\n"
                "  Windows: Download from https://ffmpeg.org/"
            )
        
        if len(clips.clips) < 3:
            raise CompositionError("Minimum 3 clips required for composition")
        
        for clip in clips.clips:
            if not clip.video_url:
                raise CompositionError(f"Clip {clip.clip_index} missing video_url")
            if clip.status != "success":
                raise CompositionError(
                    f"Clip {clip.clip_index} has status '{clip.status}', expected 'success'"
                )
        
        if not audio_url:
            raise CompositionError("Audio URL required for composition")
        
        # Sort clips by clip_index (guarantee correct order)
        sorted_clips = sorted(clips.clips, key=lambda c: c.clip_index)
        
        # Reindex clips to be sequential (handle missing clips from failures)
        # This allows composition to proceed even if some clips failed
        # For example, if clips 0, 1, 2, 3 exist but clip 0 failed, we'll reindex 1,2,3 to 0,1,2
        reindexed_clips = []
        for i, clip in enumerate(sorted_clips):
            # Create a copy with sequential index for composition
            # Use Pydantic model_copy() if available, otherwise create new instance
            if hasattr(clip, 'model_copy'):
                reindexed_clip = clip.model_copy(update={'clip_index': i})
            else:
                # Fallback for older Pydantic versions
                from copy import deepcopy
                reindexed_clip = deepcopy(clip)
                reindexed_clip.clip_index = i
            reindexed_clips.append(reindexed_clip)
            logger.info(
                f"Reindexed clip: original index {clip.clip_index} -> composition index {i}",
                extra={"job_id": str(job_id), "original_index": clip.clip_index, "new_index": i}
            )
        
        # Use reindexed clips for composition
        sorted_clips = reindexed_clips
        
        # Check disk space (optional, non-blocking warning)
        try:
            disk_usage = shutil.disk_usage("/")
            available_gb = disk_usage.free / (1024 ** 3)
            if available_gb < 0.5:  # Less than 500MB available
                logger.warning(
                    f"Low disk space: {available_gb:.2f} GB available (recommended: >0.5 GB)",
                    extra={"job_id": str(job_id_uuid), "available_gb": available_gb}
                )
        except Exception as e:
            # Non-blocking: log warning but continue
            logger.warning(
                f"Could not check disk space: {e}",
                extra={"job_id": str(job_id_uuid)}
            )
        
        # Set initial progress for composer stage (85% - start of stage)
        await publish_progress(job_id_uuid, "Starting composition...", 85)
        
        # Steps 2-8: Processing with temp directory context manager
        async with temp_directory(f"composer_{job_id_uuid}_") as temp_dir:
            # Step 2: Download clips and audio (parallel) - 85-88%
            await publish_progress(job_id_uuid, f"Downloading clips ({len(sorted_clips)} clips)...", 85)
            step_start = time.time()
            clip_bytes_list = await download_all_clips(sorted_clips, job_id_uuid)
            audio_bytes = await download_audio(audio_url, job_id_uuid)
            timings["download_clips"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Clips downloaded", 88)
            
            # Log download metrics
            total_download_size = sum(len(b) for b in clip_bytes_list) + len(audio_bytes)
            logger.info(
                f"Downloaded {len(clip_bytes_list)} clips and audio ({total_download_size / 1024 / 1024:.2f} MB) in {timings['download_clips']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "clips_count": len(clip_bytes_list),
                    "download_size_mb": total_download_size / 1024 / 1024,
                    "download_time": timings["download_clips"]
                }
            )
            
            # Step 3: Normalize all clips - 88-91% (PARALLEL OPTIMIZATION)
            # Performance: Parallel normalization reduces time from ~30s (sequential) to ~10-15s (parallel)
            # for 6 clips. All clips are independent operations with separate temp files, so safe to parallelize.
            await publish_progress(job_id_uuid, f"Normalizing clips to {output_width}x{output_height}, 30fps...", 88)
            step_start = time.time()
            # Parallel normalization for better performance (30-50% faster)
            normalize_tasks = [
                normalize_clip(
                    clip_bytes, clip.clip_index, temp_dir, job_id_uuid, output_width, output_height
                )
                for clip_bytes, clip in zip(clip_bytes_list, sorted_clips)
            ]
            normalized_paths = await asyncio.gather(*normalize_tasks)
            timings["normalize_clips"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Clips normalized", 91)
            
            logger.info(
                f"Normalized {len(normalized_paths)} clips in {timings['normalize_clips']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "clips_count": len(normalized_paths),
                    "normalize_time": timings["normalize_clips"]
                }
            )
            
            # Step 4: Handle duration mismatches with cascading compensation - 91-94%
            await publish_progress(job_id_uuid, "Handling duration mismatches...", 91)
            step_start = time.time()
            
            # Check feature flag for cascading compensation
            from .config import USE_CASCADING_COMPENSATION
            
            if not USE_CASCADING_COMPENSATION:
                raise CompositionError(
                    "Cascading compensation is disabled via USE_CASCADING_COMPENSATION=false. "
                    "This feature is required for proper duration handling."
                )
            
            # Use cascading compensation instead of per-clip handling
            final_clip_paths, duration_metrics = await handle_cascading_durations(
                normalized_paths,
                sorted_clips,
                temp_dir,
                job_id_uuid
            )
            
            # Safety check: ensure we have the same number of clips
            if len(final_clip_paths) != len(sorted_clips):
                raise CompositionError(
                    f"Clip count mismatch after cascading compensation: "
                    f"expected {len(sorted_clips)}, got {len(final_clip_paths)}"
                )
            
            # Check if final shortfall is acceptable
            MAX_SHORTFALL_PERCENTAGE = float(os.getenv("MAX_SHORTFALL_PERCENTAGE", "10.0"))
            EXTEND_LAST_CLIP_THRESHOLD = float(os.getenv("EXTEND_LAST_CLIP_THRESHOLD", "20.0"))
            FAIL_JOB_THRESHOLD = float(os.getenv("FAIL_JOB_THRESHOLD", "50.0"))
            MAX_LAST_CLIP_EXTENSION = float(os.getenv("MAX_LAST_CLIP_EXTENSION", "5.0"))
            
            # Use original_target_duration for total intended (before buffer was applied)
            total_intended = sum(
                (c.original_target_duration if c.original_target_duration is not None else c.target_duration)
                for c in sorted_clips
            )
            shortfall_pct = (duration_metrics["total_shortfall"] / total_intended * 100) if total_intended > 0 else 0.0
            total_shortfall = duration_metrics["total_shortfall"]
            
            if shortfall_pct >= FAIL_JOB_THRESHOLD:
                # Shortfall too large - likely generation failure
                raise CompositionError(
                    f"Shortfall too large: {total_shortfall:.2f}s ({shortfall_pct:.1f}%) - "
                    f"exceeds failure threshold ({FAIL_JOB_THRESHOLD}%)"
                )
            elif shortfall_pct >= EXTEND_LAST_CLIP_THRESHOLD:
                # Check if shortfall exceeds maximum extension limit
                if total_shortfall > MAX_LAST_CLIP_EXTENSION:
                    # Shortfall too large to extend - fail job
                    raise CompositionError(
                        f"Shortfall {total_shortfall:.2f}s ({shortfall_pct:.1f}%) exceeds maximum extension "
                        f"{MAX_LAST_CLIP_EXTENSION}s. This indicates a significant video generation failure. "
                        f"Please check video generation settings and model configuration."
                    )
                
                # Extend last clip to cover shortfall
                # Safety check: ensure we're only extending the actual last clip
                if len(final_clip_paths) == 0:
                    raise CompositionError("Cannot extend last clip: no clips available")
                
                last_clip_index = len(final_clip_paths) - 1
                expected_last_clip_index = len(sorted_clips) - 1
                
                if last_clip_index != expected_last_clip_index:
                    raise CompositionError(
                        f"Safety check failed: attempting to extend clip at index {last_clip_index}, "
                        f"but expected last clip index is {expected_last_clip_index}"
                    )
                
                logger.warning(
                    f"Large shortfall: {total_shortfall:.2f}s ({shortfall_pct:.1f}%) - extending last clip (index {last_clip_index})",
                    extra={
                        "job_id": str(job_id_uuid),
                        "total_shortfall": total_shortfall,
                        "shortfall_percentage": shortfall_pct,
                        "last_clip_index": last_clip_index,
                        "total_clips": len(final_clip_paths)
                    }
                )
                extended_path = await extend_last_clip(
                    final_clip_paths[-1],
                    total_shortfall,
                    temp_dir,
                    job_id_uuid
                )
                final_clip_paths[-1] = extended_path
            elif shortfall_pct >= MAX_SHORTFALL_PERCENTAGE:
                # Log warning but accept
                logger.warning(
                    f"Shortfall: {total_shortfall:.2f}s ({shortfall_pct:.1f}%) - within tolerance",
                    extra={
                        "job_id": str(job_id_uuid),
                        "total_shortfall": total_shortfall,
                        "shortfall_percentage": shortfall_pct
                    }
                )
            
            clips_trimmed = duration_metrics["clips_trimmed"]
            clips_looped = 0  # Always 0 with cascading compensation (backward compatibility)
            
            timings["handle_durations"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Durations handled", 94)
            
            logger.info(
                f"Handled durations: {clips_trimmed} trimmed, final shortfall: {total_shortfall:.2f}s "
                f"({shortfall_pct:.1f}%) in {timings['handle_durations']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "clips_trimmed": clips_trimmed,
                    "total_shortfall": total_shortfall,
                    "shortfall_percentage": shortfall_pct,
                    "compensation_applied": len(duration_metrics["compensation_applied"]),
                    "duration_handling_time": timings["handle_durations"]
                }
            )
            
            # Step 5: Apply transitions (with optional beat alignment)
            await publish_progress(job_id_uuid, "Applying transitions...")
            step_start = time.time()
            concatenated_path = await apply_transitions(
                final_clip_paths, transitions, temp_dir, job_id_uuid, beat_timestamps
            )
            timings["apply_transitions"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Transitions applied", 97)
            
            logger.info(
                f"Applied transitions in {timings['apply_transitions']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "transitions_time": timings["apply_transitions"]
                }
            )
            
            # Step 6: Pad video to match audio length (if needed) - 97-98%
            await publish_progress(job_id_uuid, "Padding video to match audio length...", 97)
            step_start = time.time()
            padded_video_path = await pad_video_to_audio(
                concatenated_path, audio_bytes, temp_dir, job_id_uuid, output_width, output_height
            )
            timings["pad_video"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Video padded", 98)
            
            logger.info(
                f"Padded video in {timings['pad_video']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "padding_time": timings["pad_video"]
                }
            )
            
            # Step 7: Sync audio - 98-99%
            await publish_progress(job_id_uuid, "Syncing audio with video...", 98)
            step_start = time.time()
            video_with_audio_path, sync_drift = await sync_audio(
                padded_video_path, audio_bytes, temp_dir, job_id_uuid
            )
            timings["sync_audio"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Audio synced", 99)
            
            logger.info(
                f"Synced audio (drift: {sync_drift:.3f}s) in {timings['sync_audio']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "sync_drift": sync_drift,
                    "sync_time": timings["sync_audio"]
                }
            )
            
            # Step 8: Encode final video - 99-99.5%
            await publish_progress(job_id_uuid, "Encoding final video...", 99)
            step_start = time.time()
            final_video_path = await encode_final_video(
                video_with_audio_path, temp_dir, job_id_uuid, output_width, output_height
            )
            timings["encode_final"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Video encoded", 99)
            
            logger.info(
                f"Encoded final video in {timings['encode_final']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "encode_time": timings["encode_final"]
                }
            )
            
            # Step 9: Upload final video - 99-100%
            await publish_progress(job_id_uuid, "Uploading final video...", 99)
            step_start = time.time()
            storage = StorageClient()
            final_video_bytes = final_video_path.read_bytes()
            
            # Use timestamp in filename to ensure unique URL for each recomposition
            # This prevents browser/CDN caching issues when video is regenerated
            timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
            storage_path = f"{job_id_uuid}/final_video_{timestamp}.mp4"
            
            # Calculate file size for logging
            file_size_mb = len(final_video_bytes) / (1024 * 1024)
            logger.info(
                f"Starting upload of {file_size_mb:.2f} MB video file",
                extra={"job_id": str(job_id_uuid), "file_size_mb": file_size_mb}
            )
            
            # Send periodic "still uploading" messages during long uploads
            # This helps prevent frontend timeouts by showing the upload is still active
            upload_start = time.time()
            
            async def send_periodic_updates():
                """Send periodic progress updates during upload."""
                update_count = 0
                while True:
                    await asyncio.sleep(30)  # Send update every 30 seconds
                    elapsed = time.time() - upload_start
                    update_count += 1
                    # Send message to keep connection alive and show progress
                    await publish_progress(
                        job_id_uuid,
                        f"Uploading final video... ({elapsed:.0f}s elapsed, {file_size_mb:.1f} MB)",
                        99  # Keep at 99% until upload completes
                    )
                    logger.debug(
                        f"Upload progress update: {elapsed:.1f}s elapsed",
                        extra={"job_id": str(job_id_uuid), "elapsed": elapsed, "update_count": update_count}
                    )
            
            # Start periodic update task
            update_task = asyncio.create_task(send_periodic_updates())
            
            try:
                # Perform the actual upload (this is blocking but runs in executor)
                # Use overwrite=True to handle recomposition scenarios where the file already exists
                video_url = await storage.upload_file(
                    bucket=VIDEO_OUTPUTS_BUCKET,
                    path=storage_path,
                    file_data=final_video_bytes,
                    content_type="video/mp4",
                    overwrite=True
                )
            finally:
                # Cancel the periodic update task once upload completes
                update_task.cancel()
                try:
                    await update_task
                except asyncio.CancelledError:
                    pass
            
            timings["upload_final"] = time.time() - step_start
            await publish_progress(job_id_uuid, "Upload complete", 100)
            
            logger.info(
                f"Uploaded final video to {video_url} in {timings['upload_final']:.2f}s",
                extra={
                    "job_id": str(job_id_uuid),
                    "url": video_url,
                    "upload_time": timings["upload_final"]
                }
            )
            
            # Calculate metrics before temp directory cleanup
            composition_time = time.time() - start_time
            timings["total"] = composition_time
            final_video_duration = await get_video_duration(final_video_path)
            file_size_mb = final_video_path.stat().st_size / 1024 / 1024
            
            # Get audio duration from original audio if available (or calculate from clips)
            # Use original_target_duration (before buffer was applied) for accurate audio duration
            audio_duration = sum(
                (clip.original_target_duration if clip.original_target_duration is not None else clip.target_duration)
                for clip in sorted_clips
            )
            
            # Get compensation metrics
            compensation_applied = duration_metrics.get("compensation_applied", [])
            total_shortfall = duration_metrics.get("total_shortfall", 0.0)
            shortfall_percentage = (total_shortfall / total_intended * 100) if total_intended > 0 else 0.0
        
        # Create VideoOutput after temp directory cleanup
        
        video_output = VideoOutput(
            job_id=job_id_uuid,
            video_url=video_url,
            duration=final_video_duration,
            audio_duration=audio_duration,
            sync_drift=sync_drift,
            clips_used=len(sorted_clips),
            clips_trimmed=clips_trimmed,
            clips_looped=0,  # Always 0 with cascading compensation (backward compatibility)
            compensation_applied=compensation_applied,
            total_shortfall=total_shortfall,
            shortfall_percentage=shortfall_percentage,
            transitions_applied=len(sorted_clips) - 1,  # N clips = N-1 transitions
            file_size_mb=file_size_mb,
            composition_time=composition_time,
            cost=Decimal("0.00"),  # No API calls, compute only
            status="success"
        )
        
        # Log comprehensive metrics
        logger.info(
            f"Composition complete: {file_size_mb:.2f} MB, {composition_time:.2f}s",
            extra={
                "job_id": str(job_id_uuid),
                "file_size_mb": file_size_mb,
                "composition_time": composition_time,
                "clips_used": len(sorted_clips),
                "clips_trimmed": clips_trimmed,
                "clips_looped": 0,  # Looping disabled
                "sync_drift": sync_drift,
                "video_duration": final_video_duration,
                "audio_duration": audio_duration,
                "timings": timings
            }
        )
        
        return video_output
        
    except CompositionError:
        # Permanent failure - log and re-raise
        logger.error(
            f"Composition failed",
            exc_info=True,
            extra={"job_id": str(job_id_uuid)}
        )
        raise
    except RetryableError:
        # Transient failure - log and re-raise (orchestrator will retry)
        logger.warning(
            f"Composition retryable error",
            exc_info=True,
            extra={"job_id": str(job_id_uuid)}
        )
        raise
    except Exception as e:
        # Unexpected error - wrap in CompositionError
        logger.error(
            f"Unexpected composition error: {e}",
            exc_info=True,
            extra={"job_id": str(job_id_uuid)}
        )
        raise CompositionError(f"Unexpected error during composition: {e}") from e

