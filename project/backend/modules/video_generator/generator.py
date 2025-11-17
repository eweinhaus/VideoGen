"""
Replicate API integration for video clip generation.

Handles single video clip generation via Replicate API with polling,
error handling, and cost tracking.
"""
import asyncio
import time
import subprocess
import tempfile
import os
from typing import Optional, Callable, Dict, Any
from uuid import UUID
from decimal import Decimal
from email.utils import parsedate_to_datetime
from datetime import datetime

import replicate
import httpx

from shared.models.video import Clip, ClipPrompt
from shared.storage import StorageClient
from shared.cost_tracking import cost_tracker
from shared.errors import RetryableError, GenerationError
from shared.logging import get_logger
from shared.config import settings
from modules.video_generator.config import (
    SVD_MODEL, COGVIDEOX_MODEL, get_generation_settings,
    get_selected_model, get_model_config, get_model_replicate_string
)
from modules.video_generator.model_validator import get_latest_version_hash, validate_model_config
from modules.video_generator.cost_estimator import estimate_clip_cost
from replicate.exceptions import ModelError

logger = get_logger("video_generator.generator")

# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    raise


def parse_retry_after_header(headers: dict) -> Optional[float]:
    """
    Parse Retry-After header from API response.
    
    Args:
        headers: Response headers dict
        
    Returns:
        Seconds to wait, or None if not present
    """
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if not retry_after:
        return None
    
    try:
        # Retry-After can be seconds (int) or HTTP date
        return float(retry_after)
    except ValueError:
        # Try parsing as HTTP date
        try:
            retry_date = parsedate_to_datetime(retry_after)
            wait_seconds = (retry_date - datetime.now()).total_seconds()
            return max(0, wait_seconds)
        except Exception:
            return None


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


def calculate_num_frames(target_duration: float, fps: int) -> int:
    """
    Calculate number of frames for target duration.
    
    Args:
        target_duration: Target duration in seconds
        fps: Frames per second
        
    Returns:
        Number of frames (int)
    """
    return int(target_duration * fps)


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
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Failed to download video from {url}: {e}")
        raise RetryableError(f"Video download failed: {str(e)}") from e


def get_video_duration(video_bytes: bytes) -> float:
    """
    Get video duration using ffprobe or similar.
    
    Args:
        video_bytes: Video file bytes
        
    Returns:
        Duration in seconds
        
    Note: Uses ffprobe subprocess. Falls back to default if unavailable.
    """
    tmp_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        
        # Use ffprobe to get duration
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                tmp_path
            ],
            capture_output=True,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        return duration
    except FileNotFoundError:
        logger.warning("ffprobe not found, using default duration estimate")
        return 5.0  # Default estimate
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.warning(f"Failed to get video duration: {e}, using estimate")
        return 5.0  # Default estimate
    except Exception as e:
        logger.warning(f"Unexpected error getting video duration: {e}, using estimate")
        return 5.0  # Default estimate
    finally:
        # Clean up temporary file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary file {tmp_path}: {e}")


async def generate_video_clip(
    clip_prompt: ClipPrompt,
    image_url: Optional[str],
    settings: dict,
    job_id: UUID,
    environment: str = "production",
    extra_context: Optional[str] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    video_model: str = None,
) -> Clip:
    """
    Generate single video clip via Replicate.
    
    Args:
        clip_prompt: ClipPrompt with prompt, duration, etc.
        image_url: Replicate file URL (or None for text-only)
        settings: Generation settings (resolution, fps, etc.)
        job_id: Job ID for logging
        environment: "production" or "development"
        video_model: Video generation model to use (kling_v21, kling_v25_turbo, hailuo_23, wan_25_i2v, veo_31)
                    If None, falls back to VIDEO_MODEL environment variable
        
    Returns:
        Clip model with video URL, duration, cost, etc.
        
    Raises:
        RetryableError: If generation fails but is retryable
        GenerationError: If generation fails permanently
        TimeoutError: If generation times out (>120s)
    """
    # Get selected model and its configuration
    if video_model is None:
        selected_model_key = get_selected_model()
    else:
        selected_model_key = video_model
    model_config = get_model_config(selected_model_key)
    
    # Log model configuration for debugging
    replicate_string = model_config.get("replicate_string", "unknown")
    model_version = model_config.get("version", "unknown")
    logger.info(
        f"Using video model: {selected_model_key} (replicate: {replicate_string}, version: {model_version[:20] if isinstance(model_version, str) and len(model_version) > 20 else model_version})",
        extra={
            "job_id": str(job_id),
            "model": selected_model_key,
            "replicate_string": replicate_string,
            "version": model_version[:20] if isinstance(model_version, str) and len(model_version) > 20 else model_version,
            "clip_index": clip_prompt.clip_index
        }
    )

    # Prepare input data based on model configuration
    # All models support prompt and duration, but parameter names may vary
    input_data = {
        "prompt": clip_prompt.prompt,
    }

    # Map duration to model-specific format
    target_duration = clip_prompt.duration
    if selected_model_key.startswith("kling"):
        # Kling models support 5 or 10 seconds
        if target_duration <= 7.5:
            input_data["duration"] = 5
        else:
            input_data["duration"] = 10
    else:
        # Other models may accept duration as-is or need different mapping
        # For now, use closest supported value (5 or 10)
        if target_duration <= 7.5:
            input_data["duration"] = 5
        else:
            input_data["duration"] = 10

    # Map resolution based on model's supported resolutions
    resolution = settings.get("resolution", "1024x576")
    supported_resolutions = model_config.get("resolutions", ["1080p"])

    if "1080p" in supported_resolutions:
        if "1080" in resolution or resolution == "1080p":
            input_data["resolution"] = "1080p"
        elif "720" in resolution or resolution == "720p":
            input_data["resolution"] = "720p" if "720p" in supported_resolutions else "1080p"
        else:
            input_data["resolution"] = "1080p" if environment == "production" else ("720p" if "720p" in supported_resolutions else "1080p")
    elif "720p" in supported_resolutions:
        input_data["resolution"] = "720p"
    elif "variable" in supported_resolutions:
        # Models with variable resolution may not need resolution parameter
        pass

    # Add image if available (parameter name varies by model)
    # Kling and most I2V models use "start_image" or "image"
    if image_url and model_config.get("type") in ["image-to-video", "text-and-image-to-video"]:
        # Try start_image first (Kling format)
        input_data["start_image"] = image_url

    # Get model version string for Replicate
    # Extract version from model config - don't use default fallback to avoid wrong model version
    model_version = model_config.get("version")
    if not model_version:
        raise GenerationError(
            f"No version specified for model {selected_model_key}. "
            f"Please check VIDEO_MODEL configuration."
        )
    use_fallback = False
    
    try:
        # Start prediction
        logger.info(
            f"Starting video generation for clip {clip_prompt.clip_index}",
            extra={"job_id": str(job_id), "target_duration": clip_prompt.duration, "resolution": input_data.get("resolution")}
        )
        
        # Create prediction - Replicate API
        # For models with "latest" version, dynamically retrieve latest hash or use model= parameter
        # For models with pinned version hashes, use version parameter
        if model_version == "latest":
            # For models with "latest" version, try to get the latest version hash dynamically
            replicate_string = model_config.get("replicate_string", "kwaivgi/kling-v2.1")
            try:
                # Try to get latest version hash dynamically
                latest_hash = await get_latest_version_hash(replicate_string)
                if latest_hash:
                    # Use version parameter with dynamically retrieved hash
                    logger.info(
                        f"Using dynamically retrieved latest version hash for {replicate_string}: {latest_hash}",
                        extra={"job_id": str(job_id), "model": selected_model_key, "version_hash": latest_hash}
                    )
                    prediction = client.predictions.create(
                        version=latest_hash,
                        input=input_data
                    )
                else:
                    # Fallback: Use model= parameter (Replicate will use latest)
                    logger.warning(
                        f"Could not retrieve latest version hash for {replicate_string}, using model= parameter",
                        extra={"job_id": str(job_id), "model": selected_model_key}
                    )
                    prediction = client.predictions.create(
                        model=replicate_string,
                        input=input_data
                    )
            except Exception as e:
                # Fallback to model= parameter if dynamic retrieval fails
                logger.warning(
                    f"Error retrieving latest version hash for {replicate_string}, falling back to model=: {str(e)}",
                    extra={"job_id": str(job_id), "model": selected_model_key, "error": str(e)}
                )
                prediction = client.predictions.create(
                    model=replicate_string,
                    input=input_data
                )
        else:
            # For models with pinned version hashes, use version parameter
            # Note: Version hash must match the model's replicate_string
            logger.info(
                f"Using pinned version hash for {selected_model_key}: {model_version[:8]}...",
                extra={"job_id": str(job_id), "model": selected_model_key, "version_hash": model_version}
            )
            try:
                prediction = client.predictions.create(
                    version=model_version,  # Version hash from config
                    input=input_data
                )
            except Exception as e:
                error_str = str(e).lower()
                if "invalid version" in error_str or "not permitted" in error_str or "422" in error_str:
                    # Version hash might be invalid/expired, raise clearer error
                    replicate_string = model_config.get("replicate_string", "unknown")
                    raise GenerationError(
                        f"Invalid model version or permission denied: {replicate_string}:{model_version[:16]}... "
                        f"Error: {str(e)}. Please check your model version configuration or API token permissions."
                    ) from e
                raise
        
        # Poll for completion (fixed 3-second interval)
        start_time = time.time()
        poll_interval = 3  # Fixed 3-second polling
        
        # Get model-specific generation time estimate from config
        try:
            model_key = selected_model_key  # Already retrieved at start of function
            config = get_model_config(model_key)
            estimated_clip_time = config.get("generation_time_avg_seconds", 90)  # Default to 90s if not in config
            logger.debug(
                f"Using model-specific estimated clip time: {estimated_clip_time}s for {model_key}",
                extra={"job_id": str(job_id), "model": model_key, "estimated_time": estimated_clip_time}
            )
        except Exception as e:
            # Fallback to environment-based estimate
            estimated_clip_time = 90 if environment == "production" else 60
            logger.warning(
                f"Failed to get model-specific time estimate, using fallback: {estimated_clip_time}s",
                extra={"job_id": str(job_id), "error": str(e), "environment": environment}
            )
        
        last_progress_update = 0  # Track last progress update time (for throttling)
        progress_update_interval = 3  # Update progress every 3 seconds (more frequent than before)
        
        while prediction.status not in ["succeeded", "failed", "canceled"]:
            await asyncio.sleep(poll_interval)
            
            elapsed = time.time() - start_time
            # Kling model can take longer - increase timeout to 240s (4 minutes) for reliable generation
            # Some clips may take 150-200s, so 240s provides buffer
            timeout_seconds = int(os.getenv("VIDEO_GENERATION_TIMEOUT_SECONDS", "240"))
            if elapsed > timeout_seconds:
                # Wrap TimeoutError as RetryableError so it can be retried
                raise RetryableError(f"Clip generation timeout after {elapsed:.1f}s")
            
            # Reload to get latest status
            prediction.reload()
            
            # Emit progress updates during polling (more frequent updates)
            if progress_callback:
                # Calculate sub-progress: estimate completion based on elapsed time
                # Use a more sophisticated estimation that accounts for typical generation phases
                # Early phase (0-30%): slower, model initialization
                # Middle phase (30-70%): steady generation
                # Late phase (70-100%): encoding/finalization
                
                # Normalized time (0-1) based on estimated clip time
                normalized_time = min(1.0, elapsed / estimated_clip_time)
                
                # Apply non-linear progress curve (accounts for initialization and encoding phases)
                # Early phase: slower progress (0-30% of time = 0-20% progress)
                # Middle phase: steady (30-70% of time = 20-70% progress)
                # Late phase: slower (70-100% of time = 70-100% progress)
                if normalized_time <= 0.3:
                    # Early phase: slower progress
                    sub_progress_ratio = (normalized_time / 0.3) * 0.2
                elif normalized_time <= 0.7:
                    # Middle phase: steady progress
                    sub_progress_ratio = 0.2 + ((normalized_time - 0.3) / 0.4) * 0.5
                else:
                    # Late phase: slower progress (encoding)
                    sub_progress_ratio = 0.7 + ((normalized_time - 0.7) / 0.3) * 0.3
                
                # Clamp to [0, 1]
                sub_progress_ratio = max(0.0, min(1.0, sub_progress_ratio))
                
                # Update progress more frequently (every 3 seconds instead of 10)
                if elapsed - last_progress_update >= progress_update_interval:
                    last_progress_update = elapsed
                    
                    # Try to get more accurate timing from prediction if available
                    prediction_elapsed = None
                    if hasattr(prediction, 'created_at') and prediction.created_at:
                        try:
                            from datetime import datetime, timezone
                            if isinstance(prediction.created_at, str):
                                created_at = datetime.fromisoformat(prediction.created_at.replace('Z', '+00:00'))
                            else:
                                created_at = prediction.created_at
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=timezone.utc)
                            now = datetime.now(timezone.utc)
                            prediction_elapsed = (now - created_at).total_seconds()
                        except Exception:
                            pass  # Fall back to local elapsed time
                    
                    # Use prediction elapsed time if available, otherwise use local elapsed
                    effective_elapsed = prediction_elapsed if prediction_elapsed is not None else elapsed
                    
                    progress_event = {
                        "event_type": "video_generation_progress",
                        "data": {
                            "clip_index": clip_prompt.clip_index,
                            "elapsed_seconds": int(effective_elapsed),
                            "estimated_remaining": max(0, int(estimated_clip_time - effective_elapsed)),
                            "sub_progress": sub_progress_ratio,
                            "estimated_total": int(estimated_clip_time),
                            "status": prediction.status if hasattr(prediction, 'status') else "processing",
                        }
                    }
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress_event)
                    else:
                        progress_callback(progress_event)
        
        # Handle result
        if prediction.status == "succeeded":
            # Get video output from Replicate
            # Output may be FileOutput object, URL string, or list
            output = prediction.output
            
            # Handle different output formats
            if isinstance(output, list):
                # Multiple outputs - take first video
                video_output = output[0]
            else:
                video_output = output
            
            # FileOutput objects have .read() method, URLs are strings
            if hasattr(video_output, 'read'):
                # FileOutput object - read bytes directly
                logger.info(
                    f"Reading video from Replicate FileOutput",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
                video_bytes = video_output.read()
            elif isinstance(video_output, str):
                # URL string - download from URL
                logger.info(
                    f"Downloading video from Replicate URL",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index, "url": video_output}
                )
                video_bytes = await download_video_from_url(video_output)
            else:
                raise GenerationError(f"Unexpected output format: {type(video_output)}")
            
            # Get actual duration
            actual_duration = get_video_duration(video_bytes)
            
            # Upload to Supabase Storage
            storage = StorageClient()
            clip_path = f"{job_id}/clip_{clip_prompt.clip_index}.mp4"
            
            # Delete existing file if it exists (handles retry scenarios)
            try:
                await storage.delete_file("video-clips", clip_path)
                logger.debug(
                    f"Deleted existing clip file before upload",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
            except Exception:
                # File doesn't exist or delete failed - that's okay, continue with upload
                pass
            
            logger.info(
                f"Uploading video to Supabase Storage",
                extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
            )
            final_url = await storage.upload_file(
                bucket="video-clips",
                path=clip_path,
                file_data=video_bytes,
                content_type="video/mp4"
            )
            
            # Get actual cost from Replicate prediction (if available)
            actual_cost = get_prediction_cost(prediction)
            if actual_cost is None:
                # Fallback to estimate if cost not available - use model-specific estimate
                from modules.video_generator.config import estimate_clip_cost as estimate_clip_cost_model
                logger.warning(
                    f"Cost not available in prediction, using estimate for model {selected_model_key}",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index, "model": selected_model_key}
                )
                cost = estimate_clip_cost_model(actual_duration, selected_model_key)
            else:
                cost = actual_cost
                logger.info(
                    f"Using actual cost from Replicate: {cost}",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
            
            # Track cost with model-specific API name
            api_name = selected_model_key if not use_fallback else "fallback_model"
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="video_generator",
                api_name=api_name,
                cost=cost
            )
            
            generation_time = time.time() - start_time
            
            logger.info(
                f"Clip {clip_prompt.clip_index} generated successfully",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "duration": actual_duration,
                    "cost": float(cost),
                    "generation_time": generation_time
                }
            )
            
            return Clip(
                clip_index=clip_prompt.clip_index,
                video_url=final_url,
                actual_duration=actual_duration,
                target_duration=clip_prompt.duration,
                duration_diff=actual_duration - clip_prompt.duration,
                status="success",
                cost=cost,
                retry_count=0,
                generation_time=generation_time
            )
        else:
            # Check if we should try fallback model
            if not use_fallback and "unavailable" in str(prediction.error).lower():
                logger.warning(
                    f"Kling unavailable, trying fallback model",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
                use_fallback = True
                model_version = SVD_MODEL_VERSION  # Fallback to seedance
                # Retry with fallback (would need to be called from retry logic)
                raise RetryableError(f"Model unavailable, try fallback: {prediction.error}")
            
            raise GenerationError(f"Clip generation failed: {prediction.error}")
            
    except RetryableError:
        raise
    except ModelError as e:
        # Replicate-specific model error
        error_str = str(e).lower()
        error_logs = getattr(e.prediction, 'logs', '') if hasattr(e, 'prediction') else ''
        error_logs_str = str(error_logs).lower() if error_logs else ''
        
        # Check for retryable conditions
        if "rate limit" in error_str or "429" in error_str or "429" in error_logs_str:
            # Parse Retry-After header if available
            retry_after = None
            try:
                if hasattr(e, 'prediction') and hasattr(e.prediction, 'response'):
                    response = e.prediction.response
                    if hasattr(response, 'headers'):
                        headers = response.headers
                        if isinstance(headers, dict):
                            retry_after = parse_retry_after_header(headers)
            except Exception:
                # If header parsing fails, continue without retry_after
                pass
            
            if retry_after:
                logger.info(f"Rate limit hit, waiting {retry_after}s from Retry-After header")
                raise RetryableError(f"Rate limit error (retry after {retry_after}s): {str(e)}") from e
            else:
                raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str or "timed out" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "unavailable" in error_str or "unavailable" in error_logs_str:
            # Model unavailable - try fallback
            raise RetryableError(f"Model unavailable, try fallback: {str(e)}") from e
        else:
            # Non-retryable model error
            raise GenerationError(f"Model error: {str(e)}") from e
    except Exception as e:
        # Classify other errors
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str or "timed out" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "network" in error_str or "connection" in error_str:
            raise RetryableError(f"Network error: {str(e)}") from e
        else:
            raise GenerationError(f"Generation error: {str(e)}") from e

