"""
Lipsync processor main orchestration.

Orchestrates lipsync processing for multiple video clips.
"""
import asyncio
import tempfile
from typing import List, Optional, Callable, Dict, Any
from uuid import UUID
from pathlib import Path
from decimal import Decimal

from shared.models.video import Clip, Clips
from shared.models.audio import ClipBoundary, AudioAnalysis
from shared.storage import StorageClient
from shared.logging import get_logger
from shared.errors import RetryableError, GenerationError
from modules.lipsync_processor.audio_trimmer import trim_audio_to_clip
from modules.lipsync_processor.generator import generate_lipsync_clip
from modules.clip_regenerator.data_loader import load_audio_data_from_job_stages
from modules.video_generator.image_handler import parse_supabase_url

logger = get_logger("lipsync_processor.process")


async def process_single_clip_lipsync(
    clip: Clip,
    clip_index: int,
    audio_url: str,
    job_id: UUID,
    environment: str = "production",
    event_publisher: Optional[Callable[[str, Dict[str, Any]], None]] = None
) -> Clip:
    """
    Apply lipsync to a single video clip.
    
    This function processes a single clip through the lipsync model,
    trimming the audio to match the clip's boundaries and generating
    a lipsynced version of the clip.
    
    Args:
        clip: Clip object with video to lipsync
        clip_index: Index of the clip
        audio_url: URL to original audio file
        job_id: Job ID
        environment: "production" or "development"
        event_publisher: Optional callback for SSE events
        
    Returns:
        Clip object with lipsynced video (replaces original clip)
        
    Raises:
        GenerationError: If processing fails critically
    """
    logger.info(
        f"Starting lipsync processing for single clip {clip_index}",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "environment": environment
        }
    )
    
    # Load clip boundaries from audio analysis
    audio_analysis = await load_audio_data_from_job_stages(job_id)
    if not audio_analysis:
        raise GenerationError(
            f"Audio analysis not found for job {job_id}. Cannot determine clip boundaries."
        )
    
    clip_boundaries = audio_analysis.clip_boundaries
    if not clip_boundaries:
        raise GenerationError(
            f"Clip boundaries not found in audio analysis for job {job_id}"
        )
    
    if clip_index >= len(clip_boundaries):
        raise GenerationError(
            f"Clip boundary not found for clip_index {clip_index}. "
            f"Total boundaries: {len(clip_boundaries)}"
        )
    
    boundary = clip_boundaries[clip_index]
    
    # Download original audio
    storage = StorageClient()
    logger.info(
        f"Downloading original audio for lipsync processing",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    try:
        # Parse Supabase URL to get bucket and path
        bucket, path = parse_supabase_url(audio_url)
        audio_bytes = await storage.download_file(bucket, path)
    except Exception as e:
        raise GenerationError(f"Failed to download audio file: {str(e)}") from e
    
    # Publish start event
    if event_publisher:
        try:
            if asyncio.iscoroutinefunction(event_publisher):
                await event_publisher("lipsync_started", {
                    "clip_index": clip_index,
                    "job_id": str(job_id)
                })
            else:
                event_publisher("lipsync_started", {
                    "clip_index": clip_index,
                    "job_id": str(job_id)
                })
        except Exception as e:
            logger.warning(f"Failed to publish start event: {e}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            logger.info(
                f"Processing lipsync for clip {clip_index}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "start": boundary.start,
                    "end": boundary.end,
                    "duration": boundary.duration
                }
            )
            
            # Step 1: Trim audio to clip boundaries
            trimmed_audio_bytes, duration = await trim_audio_to_clip(
                audio_bytes=audio_bytes,
                start_time=boundary.start,
                end_time=boundary.end,
                job_id=job_id,
                temp_dir=temp_path
            )
            
            # Step 2: Upload trimmed audio to temporary storage
            trimmed_audio_path = f"{job_id}/audio_trimmed_{clip_index}.mp3"
            trimmed_audio_url = await storage.upload_file(
                bucket="audio-uploads",
                path=trimmed_audio_path,
                file_data=trimmed_audio_bytes,
                content_type="audio/mpeg"
            )
            
            # Step 3: Create progress callback
            async def progress_callback(event_data: Dict[str, Any]) -> None:
                """Progress callback for lipsync generation."""
                if event_publisher:
                    try:
                        if asyncio.iscoroutinefunction(event_publisher):
                            await event_publisher("lipsync_progress", event_data)
                        else:
                            event_publisher("lipsync_progress", event_data)
                    except Exception as e:
                        logger.warning(f"Failed to publish progress event: {e}")
            
            # Step 4: Generate lipsynced clip
            lipsynced_clip = await generate_lipsync_clip(
                video_url=clip.video_url,
                audio_url=trimmed_audio_url,
                clip_index=clip_index,
                job_id=job_id,
                environment=environment,
                progress_callback=progress_callback
            )
            
            # Preserve original clip metadata
            lipsynced_clip.actual_duration = clip.actual_duration
            lipsynced_clip.target_duration = clip.target_duration
            lipsynced_clip.original_target_duration = clip.original_target_duration
            lipsynced_clip.duration_diff = clip.duration_diff
            lipsynced_clip.clip_index = clip.clip_index  # Preserve clip_index
            
            # Publish completion event
            if event_publisher:
                try:
                    if asyncio.iscoroutinefunction(event_publisher):
                        await event_publisher("lipsync_complete", {
                            "clip_index": clip_index,
                            "video_url": lipsynced_clip.video_url,
                            "cost": str(lipsynced_clip.cost),
                            "generation_time": lipsynced_clip.generation_time
                        })
                    else:
                        event_publisher("lipsync_complete", {
                            "clip_index": clip_index,
                            "video_url": lipsynced_clip.video_url,
                            "cost": str(lipsynced_clip.cost),
                            "generation_time": lipsynced_clip.generation_time
                        })
                except Exception as e:
                    logger.warning(f"Failed to publish completion event: {e}")
            
            # Cleanup: Delete trimmed audio (optional, can keep for debugging)
            try:
                await storage.delete_file("audio-uploads", trimmed_audio_path)
            except Exception:
                pass
            
            logger.info(
                f"Lipsync processing complete for clip {clip_index}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "cost": float(lipsynced_clip.cost),
                    "generation_time": lipsynced_clip.generation_time
                }
            )
            
            return lipsynced_clip
            
        except Exception as e:
            logger.error(
                f"Failed to process lipsync for clip {clip_index}: {e}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            
            # Publish failure event
            if event_publisher:
                try:
                    if asyncio.iscoroutinefunction(event_publisher):
                        await event_publisher("lipsync_failed", {
                            "clip_index": clip_index,
                            "error": str(e),
                            "using_fallback": True
                        })
                    else:
                        event_publisher("lipsync_failed", {
                            "clip_index": clip_index,
                            "error": str(e),
                            "using_fallback": True
                        })
                except Exception as e2:
                    logger.warning(f"Failed to publish failure event: {e2}")
            
            # Re-raise the error - don't fallback to original clip for single-clip processing
            # The caller should handle the error
            raise


async def process_lipsync_clips(
    clips: Clips,
    audio_url: str,
    job_id: UUID,
    environment: str = "production",
    event_publisher: Optional[Callable[[str, Dict[str, Any]], None]] = None
) -> Clips:
    """
    Apply lipsync to multiple video clips.
    
    Args:
        clips: Clips object with generated video clips
        audio_url: URL to original audio file
        job_id: Job ID
        environment: "production" or "development"
        event_publisher: Optional callback for SSE events
        
    Returns:
        Clips object with lipsynced clips (replaces original clips)
        
    Raises:
        GenerationError: If processing fails critically
    """
    logger.info(
        f"Starting lipsync processing for {len(clips.clips)} clips",
        extra={
            "job_id": str(job_id),
            "num_clips": len(clips.clips),
            "environment": environment
        }
    )
    
    # Load clip boundaries from audio analysis
    audio_analysis = await load_audio_data_from_job_stages(job_id)
    if not audio_analysis:
        raise GenerationError(
            f"Audio analysis not found for job {job_id}. Cannot determine clip boundaries."
        )
    
    clip_boundaries = audio_analysis.clip_boundaries
    if not clip_boundaries:
        raise GenerationError(
            f"Clip boundaries not found in audio analysis for job {job_id}"
        )
    
    if len(clips.clips) != len(clip_boundaries):
        logger.warning(
            f"Mismatch: {len(clips.clips)} clips but {len(clip_boundaries)} boundaries",
            extra={
                "job_id": str(job_id),
                "num_clips": len(clips.clips),
                "num_boundaries": len(clip_boundaries)
            }
        )
        # Use minimum to avoid index errors
        num_to_process = min(len(clips.clips), len(clip_boundaries))
    else:
        num_to_process = len(clips.clips)
    
    # Download original audio
    storage = StorageClient()
    logger.info(
        f"Downloading original audio for lipsync processing",
        extra={"job_id": str(job_id)}
    )
    try:
        # Parse Supabase URL to get bucket and path
        bucket, path = parse_supabase_url(audio_url)
        audio_bytes = await storage.download_file(bucket, path)
    except Exception as e:
        raise GenerationError(f"Failed to download audio file: {str(e)}") from e
    
    # Process each clip
    lipsynced_clips = []
    total_cost = Decimal("0.00")
    total_generation_time = 0.0
    successful_clips = 0
    failed_clips = 0
    
    # Publish start event
    if event_publisher:
        try:
            if asyncio.iscoroutinefunction(event_publisher):
                await event_publisher("lipsync_started", {
                    "total_clips": num_to_process,
                    "job_id": str(job_id)
                })
            else:
                event_publisher("lipsync_started", {
                    "total_clips": num_to_process,
                    "job_id": str(job_id)
                })
        except Exception as e:
            logger.warning(f"Failed to publish start event: {e}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for i in range(num_to_process):
            clip = clips.clips[i]
            boundary = clip_boundaries[i]
            
            try:
                logger.info(
                    f"Processing lipsync for clip {i}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "start": boundary.start,
                        "end": boundary.end,
                        "duration": boundary.duration
                    }
                )
                
                # Step 1: Trim audio to clip boundaries
                trimmed_audio_bytes, duration = await trim_audio_to_clip(
                    audio_bytes=audio_bytes,
                    start_time=boundary.start,
                    end_time=boundary.end,
                    job_id=job_id,
                    temp_dir=temp_path
                )
                
                # Step 2: Upload trimmed audio to temporary storage
                trimmed_audio_path = f"{job_id}/audio_trimmed_{i}.mp3"
                trimmed_audio_url = await storage.upload_file(
                    bucket="audio-uploads",
                    path=trimmed_audio_path,
                    file_data=trimmed_audio_bytes,
                    content_type="audio/mpeg"
                )
                
                # Step 3: Create progress callback
                async def progress_callback(event_data: Dict[str, Any]) -> None:
                    """Progress callback for lipsync generation."""
                    if event_publisher:
                        try:
                            if asyncio.iscoroutinefunction(event_publisher):
                                await event_publisher("lipsync_progress", event_data)
                            else:
                                event_publisher("lipsync_progress", event_data)
                        except Exception as e:
                            logger.warning(f"Failed to publish progress event: {e}")
                
                # Step 4: Generate lipsynced clip
                lipsynced_clip = await generate_lipsync_clip(
                    video_url=clip.video_url,
                    audio_url=trimmed_audio_url,
                    clip_index=i,
                    job_id=job_id,
                    environment=environment,
                    progress_callback=progress_callback
                )
                
                # Preserve original clip metadata
                lipsynced_clip.actual_duration = clip.actual_duration
                lipsynced_clip.target_duration = clip.target_duration
                lipsynced_clip.original_target_duration = clip.original_target_duration
                lipsynced_clip.duration_diff = clip.duration_diff
                
                lipsynced_clips.append(lipsynced_clip)
                total_cost += lipsynced_clip.cost
                total_generation_time += lipsynced_clip.generation_time
                successful_clips += 1
                
                # Publish completion event
                if event_publisher:
                    try:
                        if asyncio.iscoroutinefunction(event_publisher):
                            await event_publisher("lipsync_complete", {
                                "clip_index": i,
                                "video_url": lipsynced_clip.video_url,
                                "cost": str(lipsynced_clip.cost),
                                "generation_time": lipsynced_clip.generation_time
                            })
                        else:
                            event_publisher("lipsync_complete", {
                                "clip_index": i,
                                "video_url": lipsynced_clip.video_url,
                                "cost": str(lipsynced_clip.cost),
                                "generation_time": lipsynced_clip.generation_time
                            })
                    except Exception as e:
                        logger.warning(f"Failed to publish completion event: {e}")
                
                # Cleanup: Delete trimmed audio (optional, can keep for debugging)
                try:
                    await storage.delete_file("audio-uploads", trimmed_audio_path)
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(
                    f"Failed to process lipsync for clip {i}: {e}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                
                # Fallback: Use original clip
                logger.warning(
                    f"Using original clip {i} as fallback (lipsync failed)",
                    extra={"job_id": str(job_id), "clip_index": i}
                )
                lipsynced_clips.append(clip)  # Use original clip
                failed_clips += 1
                
                # Publish failure event
                if event_publisher:
                    try:
                        if asyncio.iscoroutinefunction(event_publisher):
                            await event_publisher("lipsync_failed", {
                                "clip_index": i,
                                "error": str(e),
                                "using_fallback": True
                            })
                        else:
                            event_publisher("lipsync_failed", {
                                "clip_index": i,
                                "error": str(e),
                                "using_fallback": True
                            })
                    except Exception as e2:
                        logger.warning(f"Failed to publish failure event: {e2}")
    
    logger.info(
        f"Lipsync processing complete: {successful_clips} successful, {failed_clips} failed",
        extra={
            "job_id": str(job_id),
            "successful_clips": successful_clips,
            "failed_clips": failed_clips,
            "total_cost": float(total_cost),
            "total_generation_time": total_generation_time
        }
    )
    
    # Return updated Clips object
    return Clips(
        job_id=clips.job_id,
        clips=lipsynced_clips,
        total_clips=len(lipsynced_clips),
        successful_clips=successful_clips,
        failed_clips=failed_clips,
        total_cost=total_cost,
        total_generation_time=total_generation_time
    )

