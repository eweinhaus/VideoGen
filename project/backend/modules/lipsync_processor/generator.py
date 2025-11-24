"""
Replicate API integration for Sync Labs LipSync 2.0 model.

Handles lipsync video generation via Replicate API with polling,
error handling, and cost tracking.
"""
import asyncio
import time
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

import replicate
import httpx

from shared.models.video import Clip
from shared.storage import StorageClient
from shared.cost_tracking import cost_tracker
from shared.errors import RetryableError, GenerationError
from shared.logging import get_logger
from shared.config import settings
from modules.lipsync_processor.config import (
    SYNC_LIPSYNC_MODEL,
    SYNC_LIPSYNC_VERSION,
    PIXVERSE_LIPSYNC_MODEL,  # Legacy support
    PIXVERSE_LIPSYNC_VERSION,  # Legacy support
    LIPSYNC_TIMEOUT_SECONDS,
    LIPSYNC_ESTIMATED_COST,
    LIPSYNC_POLL_INTERVAL,
    LIPSYNC_FAST_POLL_INTERVAL,
    LIPSYNC_FAST_POLL_THRESHOLD,
    LIPSYNC_ESTIMATED_TIME_PER_CLIP,
    LIPSYNC_TEMPERATURE,
    LIPSYNC_SYNC_MODE,
    LIPSYNC_ACTIVE_SPEAKER_DETECTION
)

logger = get_logger("lipsync_processor.generator")

# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    raise


async def download_video_from_url(url: str) -> bytes:
    """
    Download video from URL (Replicate output).
    
    Args:
        url: Video URL
        
    Returns:
        Video bytes
        
    Raises:
        RetryableError: If download fails
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            response = await http_client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Failed to download video from {url}: {e}")
        raise RetryableError(f"Video download failed: {str(e)}") from e


def get_prediction_cost(prediction) -> Optional[Decimal]:
    """
    Extract actual cost from Replicate prediction.
    
    Args:
        prediction: Replicate prediction object
        
    Returns:
        Actual cost as Decimal, or None if not available
    """
    cost = None
    
    # Check prediction.metrics
    if hasattr(prediction, 'metrics') and isinstance(prediction.metrics, dict):
        cost = prediction.metrics.get('cost')
    
    # Check prediction object directly
    if cost is None and hasattr(prediction, 'cost'):
        cost = prediction.cost
    
    # Check prediction response
    if cost is None and hasattr(prediction, 'response'):
        try:
            response_json = getattr(prediction.response, 'json', None)
            if response_json:
                response_data = response_json()
                if isinstance(response_data, dict):
                    cost = response_data.get('cost') or response_data.get('metrics', {}).get('cost')
        except Exception:
            pass
    
    if cost is not None:
        try:
            return Decimal(str(cost))
        except (ValueError, TypeError, Exception):
            logger.warning(f"Invalid cost value from prediction: {cost}")
            return None
    
    return None


async def generate_lipsync_clip(
    video_url: str,
    audio_url: str,
    clip_index: int,
    job_id: UUID,
    environment: str = "production",
    progress_callback: Optional[callable] = None,
    character_ids: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    sync_mode: Optional[str] = None,
    active_speaker_detection: Optional[bool] = None
) -> Clip:
    """
    Generate lipsynced video clip via Replicate Sync Labs LipSync 2.0 model.
    
    Args:
        video_url: URL to the video clip (must be ≤ 30s, ≤ 20MB)
        audio_url: URL to the trimmed audio file (must be ≤ 30s)
        clip_index: Index of the clip
        job_id: Job ID for logging
        environment: "production" or "development"
        progress_callback: Optional callback for progress updates
        character_ids: Optional list of character IDs to target for lipsync
                       (if None, syncs all visible characters)
        temperature: Optional temperature control (0-1, default 0.95)
                     Controls expressiveness of lipsync. Higher = more expressive.
        sync_mode: Optional sync mode (default "silence")
                   Options: "silence", "cut_off", "loop", "bounce", "remap"
        active_speaker_detection: Optional active speaker detection (default True)
                                 Automatically detects who's speaking in multi-person videos
        
    Returns:
        Clip model with lipsynced video URL
        
    Raises:
        RetryableError: If generation fails but is retryable
        GenerationError: If generation fails permanently
    """
    logger.info(
        f"Starting lipsync generation for clip {clip_index}",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "video_url": video_url,
            "audio_url": audio_url
        }
    )
    
    start_time = time.time()
    
    try:
        # Prepare input data for Replicate API
        input_data = {
            "video": video_url,
            "audio": audio_url
        }
        
        # Add sync_mode (Sync Labs LipSync 2.0 feature)
        # Controls how the model handles synchronization
        final_sync_mode = sync_mode if sync_mode is not None else LIPSYNC_SYNC_MODE
        if final_sync_mode:
            input_data["sync_mode"] = str(final_sync_mode)
            logger.info(
                f"Using sync_mode: {final_sync_mode}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "sync_mode": final_sync_mode
                }
            )
        
        # Add temperature control (Sync Labs LipSync 2.0 feature)
        # Temperature controls expressiveness: 0 = subtle, 1 = expressive
        final_temperature = temperature if temperature is not None else LIPSYNC_TEMPERATURE
        if final_temperature is not None:
            input_data["temperature"] = float(final_temperature)
            logger.info(
                f"Using temperature: {final_temperature}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "temperature": final_temperature
                }
            )
        
        # Add active speaker detection (Sync Labs LipSync 2.0 feature)
        # Automatically detects who's speaking in multi-person videos
        final_active_speaker = active_speaker_detection if active_speaker_detection is not None else LIPSYNC_ACTIVE_SPEAKER_DETECTION
        if final_active_speaker is not None:
            # Note: Check if the model accepts this parameter name
            # Some models might use different parameter names
            input_data["active_speaker_detection"] = final_active_speaker
            logger.info(
                f"Using active speaker detection: {final_active_speaker}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "active_speaker_detection": final_active_speaker
                }
            )
        
        # Add character selection if provided (if model supports it)
        # Note: Sync Labs LipSync 2.0 may support character selection
        if character_ids:
            logger.info(
                f"Character selection provided: {character_ids}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "character_ids": character_ids
                }
            )
            # Some models might support a "character_ids" or "target_faces" parameter
            # For now, we log it but don't pass it (model will sync all visible faces)
            # Future: input_data["character_ids"] = character_ids
        
        # Create prediction
        logger.info(
            f"Creating Replicate prediction for clip {clip_index}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "model": SYNC_LIPSYNC_MODEL,
                "version": SYNC_LIPSYNC_VERSION,
                "sync_mode": input_data.get("sync_mode"),
                "temperature": input_data.get("temperature"),
                "active_speaker_detection": input_data.get("active_speaker_detection")
            }
        )
        
        if SYNC_LIPSYNC_VERSION == "latest":
            prediction = client.predictions.create(
                model=SYNC_LIPSYNC_MODEL,
                input=input_data
            )
        else:
            prediction = client.predictions.create(
                version=SYNC_LIPSYNC_VERSION,
                input=input_data
            )
        
        # Poll for completion with adaptive interval
        last_progress_update = 0
        progress_update_interval = 3  # Update progress every 3 seconds
        
        while prediction.status not in ["succeeded", "failed", "canceled"]:
            elapsed = time.time() - start_time
            
            if elapsed > LIPSYNC_TIMEOUT_SECONDS:
                raise RetryableError(f"Lipsync generation timeout after {elapsed:.1f}s")
            
            # Use adaptive polling: faster when close to estimated completion
            estimated_time = LIPSYNC_ESTIMATED_TIME_PER_CLIP
            if elapsed >= estimated_time * LIPSYNC_FAST_POLL_THRESHOLD:
                poll_interval = LIPSYNC_FAST_POLL_INTERVAL
            else:
                poll_interval = LIPSYNC_POLL_INTERVAL
            
            await asyncio.sleep(poll_interval)
            
            # Reload to get latest status
            prediction.reload()
            
            # Early exit if status changed
            if prediction.status in ["succeeded", "failed", "canceled"]:
                break
            
            # Emit progress updates
            if progress_callback:
                normalized_time = min(1.0, elapsed / estimated_time)
                
                # Apply non-linear progress curve
                if normalized_time <= 0.3:
                    sub_progress_ratio = (normalized_time / 0.3) * 0.2
                elif normalized_time <= 0.7:
                    sub_progress_ratio = 0.2 + ((normalized_time - 0.3) / 0.4) * 0.5
                else:
                    sub_progress_ratio = 0.7 + ((normalized_time - 0.7) / 0.3) * 0.3
                
                sub_progress_ratio = max(0.0, min(1.0, sub_progress_ratio))
                
                if elapsed - last_progress_update >= progress_update_interval:
                    last_progress_update = elapsed
                    
                    progress_event = {
                        "event_type": "lipsync_progress",
                        "data": {
                            "clip_index": clip_index,
                            "elapsed_seconds": int(elapsed),
                            "estimated_remaining": max(0, int(estimated_time - elapsed)),
                            "sub_progress": sub_progress_ratio,
                            "estimated_total": int(estimated_time),
                            "status": prediction.status if hasattr(prediction, 'status') else "processing"
                        }
                    }
                    
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress_event)
                    else:
                        progress_callback(progress_event)
        
        # Handle result
        if prediction.status == "succeeded":
            # Get output video URL
            output = prediction.output
            
            if isinstance(output, list):
                video_output_url = output[0]
            elif isinstance(output, str):
                video_output_url = output
            else:
                raise GenerationError(f"Unexpected output format: {type(output)}")
            
            # Download lipsynced video
            logger.info(
                f"Downloading lipsynced video for clip {clip_index}",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            video_bytes = await download_video_from_url(video_output_url)
            
            # CRITICAL: Strip embedded audio from lipsynced video
            # The Replicate model generates video with embedded audio (trimmed segment starting at 0:00)
            # We need to remove this audio so the composer can use the full audio track
            # at the correct timestamp (boundary.start to boundary.end in the full track)
            # The video's lip movements are already synchronized correctly, we just need to remove the audio track
            logger.info(
                f"Stripping embedded audio from lipsynced video for clip {clip_index}",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            try:
                from modules.video_generator.generator import strip_audio_from_video_bytes
                video_bytes = await strip_audio_from_video_bytes(video_bytes, job_id=job_id)
                logger.info(
                    f"Successfully stripped audio from lipsynced video",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
            except Exception as e:
                logger.warning(
                    f"Failed to strip audio from lipsynced video, continuing with embedded audio: {e}",
                    extra={"job_id": str(job_id), "clip_index": clip_index, "error": str(e)}
                )
                # Continue with original video_bytes - composer will handle it with -map flags
            
            # Upload to Supabase Storage with versioned filename (like regular regenerations)
            storage = StorageClient()
            
            # Calculate next version number from clip_versions table
            from shared.database import DatabaseClient
            db_for_version = DatabaseClient()
            version_result = await db_for_version.table("clip_versions").select("version_number").eq(
                "job_id", str(job_id)
            ).eq("clip_index", clip_index).order("version_number", desc=True).limit(1).execute()
            
            # Calculate actual next version based on what's in DB right now
            actual_next_version = 2  # Default to version 2 if no versions exist
            if version_result.data and len(version_result.data) > 0:
                actual_next_version = version_result.data[0].get("version_number", 1) + 1
            
            # CRITICAL: Keep incrementing until we find a version that doesn't exist in storage
            # This handles cases where DB and storage are out of sync (e.g., failed uploads)
            max_attempts = 10  # Prevent infinite loop
            for attempt in range(max_attempts):
                test_path = f"{job_id}/clip_{clip_index}_v{actual_next_version}.mp4"
                
                # Check if file exists in storage (using efficient file_exists method)
                file_exists = await storage.file_exists("video-clips", test_path)
                if file_exists:
                    # File exists, increment and try next version
                    logger.info(
                        f"Version {actual_next_version} already exists in storage, trying v{actual_next_version + 1}",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_index,
                            "existing_version": actual_next_version,
                            "next_version": actual_next_version + 1
                        }
                    )
                    actual_next_version += 1
                else:
                    # File doesn't exist - we can use this version
                    break
            
            # Use versioned filename (e.g., clip_4_v2.mp4, clip_4_v3.mp4)
            clip_path = f"{job_id}/clip_{clip_index}_v{actual_next_version}.mp4"
            logger.info(
                f"Using versioned filename for lipsync (preserving previous versions)",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "version_number": actual_next_version,
                    "clip_path": clip_path
                }
            )
            
            final_url = await storage.upload_file(
                bucket="video-clips",
                path=clip_path,
                file_data=video_bytes,
                content_type="video/mp4"
            )
            
            # Get actual cost from prediction (if available)
            actual_cost = get_prediction_cost(prediction)
            if actual_cost is None:
                # Fallback to estimate
                actual_cost = LIPSYNC_ESTIMATED_COST
                logger.warning(
                    f"Cost not available, using estimate: {actual_cost}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
            
            # Track cost
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="lipsync_processor",
                api_name="sync_lipsync_2",
                cost=actual_cost
            )
            
            generation_time = time.time() - start_time
            
            logger.info(
                f"Lipsync clip {clip_index} generated successfully",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "cost": float(actual_cost),
                    "generation_time": generation_time
                }
            )
            
            # Return Clip model (metadata will be preserved by caller)
            return Clip(
                clip_index=clip_index,
                video_url=final_url,
                actual_duration=0.0,  # Will be updated from original clip
                target_duration=0.0,  # Will be updated from original clip
                original_target_duration=0.0,  # Will be updated from original clip
                duration_diff=0.0,
                status="success",
                cost=actual_cost,
                retry_count=0,
                generation_time=generation_time
            )
        else:
            # Handle errors
            error_str = str(prediction.error).lower() if prediction.error else ""
            
            if "rate limit" in error_str or "429" in error_str:
                raise RetryableError(f"Rate limit error: {prediction.error}")
            elif "timeout" in error_str:
                raise RetryableError(f"Timeout error: {prediction.error}")
            elif "network" in error_str or "connection" in error_str:
                raise RetryableError(f"Network error: {prediction.error}")
            else:
                raise GenerationError(f"Lipsync generation failed: {prediction.error}")
                
    except RetryableError:
        raise
    except GenerationError:
        raise
    except Exception as e:
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "network" in error_str or "connection" in error_str:
            raise RetryableError(f"Network error: {str(e)}") from e
        else:
            raise GenerationError(f"Lipsync generation error: {str(e)}") from e

