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
from typing import Optional, Callable, Dict, Any, List
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
    get_selected_model, get_model_config, get_model_replicate_string,
    get_duration_buffer_multiplier
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


async def strip_audio_from_video_bytes(video_bytes: bytes, job_id: UUID = None) -> bytes:
    """
    Strip audio track from video bytes using FFmpeg.
    
    This ensures video-only clips regardless of what the model generates.
    We use original audio in the composer, not AI-generated audio.
    
    Args:
        video_bytes: Video file bytes (with or without audio)
        job_id: Job ID for logging
        
    Returns:
        Video bytes without audio track
        
    Raises:
        RetryableError: If audio stripping fails
        GenerationError: If FFmpeg is not available
    """
    import shutil
    
    # Check if FFmpeg is available
    if not shutil.which("ffmpeg"):
        logger.warning(
            "FFmpeg not available, cannot strip audio. Video may contain audio from model.",
            extra={"job_id": str(job_id) if job_id else None}
        )
        # Return original bytes if FFmpeg not available (better than failing)
        return video_bytes
    
    # Use temporary files for input and output
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as input_file:
        input_path = input_file.name
        input_file.write(video_bytes)
    
    output_path = None
    try:
        # Create output temp file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output_file:
            output_path = output_file.name
        
        # FFmpeg command to strip audio: -an flag removes all audio streams
        # -c:v copy: Copy video stream without re-encoding (faster, preserves quality)
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "copy",  # Copy video (no re-encoding)
            "-an",  # Remove all audio streams
            "-y",  # Overwrite output file
            output_path
        ]
        
        logger.info(
            "Stripping audio from video clip",
            extra={"job_id": str(job_id) if job_id else None}
        )
        
        # Run FFmpeg command
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"Failed to strip audio from video: {error_msg}",
                extra={"job_id": str(job_id) if job_id else None, "error": error_msg}
            )
            # Return original bytes if stripping fails (better than failing the job)
            logger.warning(
                "Returning original video bytes (audio stripping failed)",
                extra={"job_id": str(job_id) if job_id else None}
            )
            return video_bytes
        
        # Read output file
        with open(output_path, "rb") as f:
            video_without_audio = f.read()
        
        logger.info(
            "Audio stripped from video clip successfully",
            extra={
                "job_id": str(job_id) if job_id else None,
                "original_size": len(video_bytes),
                "stripped_size": len(video_without_audio)
            }
        )
        
        return video_without_audio
        
    except asyncio.TimeoutError:
        logger.error(
            "Audio stripping timeout after 60s",
            extra={"job_id": str(job_id) if job_id else None}
        )
        return video_bytes  # Return original on timeout
    except Exception as e:
        logger.error(
            f"Error stripping audio from video: {e}",
            extra={"job_id": str(job_id) if job_id else None, "error": str(e)}
        )
        return video_bytes  # Return original on error
    finally:
        # Clean up temp files
        try:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if output_path and os.path.exists(output_path):
                os.unlink(output_path)
        except Exception as e:
            logger.warning(f"Failed to delete temporary files: {e}")


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


def map_to_nearest_valid_duration(target_duration: float, valid_durations: list) -> int:
    """
    Map target duration to nearest valid duration value.
    
    Args:
        target_duration: Target duration in seconds
        valid_durations: List of valid duration values (e.g., [4, 6, 8])
        
    Returns:
        Nearest valid duration as integer
    """
    if not valid_durations:
        return int(round(target_duration))
    
    # Find the closest valid duration
    closest = min(valid_durations, key=lambda x: abs(x - target_duration))
    return int(closest)


async def generate_video_clip(
    clip_prompt: ClipPrompt,
    image_url: Optional[str],
    reference_image_urls: Optional[List[str]] = None,  # Multiple images for Veo 3.1
    settings: dict = None,
    job_id: UUID = None,
    environment: str = "production",
    extra_context: Optional[str] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    video_model: str = None,
    aspect_ratio: str = "16:9",
    temperature: Optional[float] = None,  # LLM-determined temperature for video generation
    seed: Optional[int] = None,  # Seed for reproducible generation (reused for precise changes)
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
        aspect_ratio: Aspect ratio for video generation (default: "16:9")
        temperature: Optional temperature (0.0-1.0) for video generation randomness.
                    Lower = more deterministic, Higher = more creative variation.
                    Only used for models that support it (e.g., Veo 3.1).
        seed: Optional seed for reproducible generation. If provided, same seed + same inputs
              produces identical output. Only used for models that support it (e.g., Veo 3.1).
        
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
    
    # Validate aspect ratio
    from shared.errors import ValidationError
    supported_aspect_ratios = model_config.get("aspect_ratios", ["16:9"])
    if aspect_ratio not in supported_aspect_ratios:
        raise ValidationError(
            f"Aspect ratio '{aspect_ratio}' not supported for model '{selected_model_key}'. "
            f"Supported: {supported_aspect_ratios}"
        )
    
    # Get parameter name and mapping
    aspect_ratio_param = model_config.get("aspect_ratio_parameter", "aspect_ratio")
    resolution_mapping = model_config.get("resolution_mapping", {})
    
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

    # Extract original target duration (preserve for Part 2 compensation algorithm)
    original_target_duration = clip_prompt.duration
    target_duration = clip_prompt.duration

    # Get buffer multiplier for continuous models
    buffer_multiplier = get_duration_buffer_multiplier()

    # Get model configuration to determine duration support type
    duration_support_type = model_config.get("duration_support", "discrete")  # Default to discrete for safety

    # Calculate buffer duration based on model type
    if duration_support_type == "continuous":
        # Continuous models: Apply percentage buffer (25% default, capped at 10s)
        requested_duration = min(target_duration * buffer_multiplier, 10.0)
        
        # For continuous models, use the calculated duration directly
        input_data["duration"] = requested_duration
        
        buffer_strategy = "percentage"
        logger.info(
            f"Buffer calculation for clip {clip_prompt.clip_index} (continuous model)",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_prompt.clip_index,
                "original_target_duration": original_target_duration,
                "requested_duration": requested_duration,
                "buffer_strategy": buffer_strategy,
                "buffer_multiplier": buffer_multiplier,
                "model": selected_model_key
            }
        )
    elif selected_model_key == "veo_31":
        # Veo 3.1: Discrete duration support (4s/6s/8s) - map to nearest valid value
        # Apply buffer first, then map to nearest valid duration
        requested_duration = min(target_duration * buffer_multiplier, 8.0)  # Cap at 8s (max for Veo 3.1)
        supported_durations = model_config.get("supported_durations", [4, 6, 8])
        mapped_duration = map_to_nearest_valid_duration(requested_duration, supported_durations)
        input_data["duration"] = mapped_duration
        
        buffer_strategy = "nearest_valid"
        logger.info(
            f"Buffer calculation for clip {clip_prompt.clip_index} (Veo 3.1 discrete model)",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_prompt.clip_index,
                "original_target_duration": original_target_duration,
                "requested_duration": requested_duration,
                "mapped_duration": mapped_duration,
                "buffer_strategy": buffer_strategy,
                "buffer_multiplier": buffer_multiplier,
                "valid_durations": supported_durations,
                "model": selected_model_key
            }
        )
    elif selected_model_key.startswith("kling"):
        # Kling models: Discrete duration support (5s/10s) - use maximum buffer strategy
        if target_duration <= 5.0:
            input_data["duration"] = 5  # No buffer possible for ≤5s targets
            buffer_strategy = "maximum"
            logger.warning(
                f"Buffer cannot be applied for target {target_duration}s (Kling only supports 5s/10s)",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "target_duration": target_duration,
                    "requested": 5,
                    "buffer_strategy": "none_possible"
                }
            )
        else:
            input_data["duration"] = 10  # Maximum buffer for >5s targets
            buffer_strategy = "maximum"
            logger.info(
                f"Buffer calculation for clip {clip_prompt.clip_index} (discrete model, maximum buffer)",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "original_target_duration": original_target_duration,
                    "requested_duration": 10,
                    "buffer_strategy": buffer_strategy,
                    "model": selected_model_key
                }
            )
    else:
        # Other discrete models: Similar to Kling (maximum buffer strategy)
        if target_duration <= 5.0:
            input_data["duration"] = 5
            buffer_strategy = "maximum"
            logger.warning(
                f"Buffer cannot be applied for target {target_duration}s ({selected_model_key} only supports 5s/10s)",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "target_duration": target_duration,
                    "requested": 5,
                    "buffer_strategy": "none_possible",
                    "model": selected_model_key
                }
            )
        else:
            input_data["duration"] = 10  # Maximum buffer for >5s targets
            buffer_strategy = "maximum"
            logger.info(
                f"Buffer calculation for clip {clip_prompt.clip_index} (discrete model, maximum buffer)",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "original_target_duration": original_target_duration,
                    "requested_duration": 10,
                    "buffer_strategy": buffer_strategy,
                    "model": selected_model_key
                }
            )

    # Map aspect ratio based on model's parameter requirements
    # This takes precedence over default resolution logic
    if aspect_ratio_param == "resolution" and resolution_mapping:
        # Use resolution mapping (e.g., "16:9" -> "1080p")
        mapped_value = resolution_mapping.get(aspect_ratio, "1080p")
        input_data[aspect_ratio_param] = mapped_value
        logger.info(
            f"Using aspect ratio '{aspect_ratio}' mapped to resolution '{mapped_value}'",
            extra={
                "job_id": str(job_id),
                "aspect_ratio": aspect_ratio,
                "mapped_resolution": mapped_value,
                "model": selected_model_key
            }
        )
    elif aspect_ratio_param in ["aspect_ratio", "ratio"]:
        # Use aspect ratio directly
        input_data[aspect_ratio_param] = aspect_ratio
        
        # For models that support both aspect_ratio and resolution (e.g., Veo 3.1),
        # also set resolution for highest quality
        supported_resolutions = model_config.get("resolutions", ["1080p"])
        if "resolution" in model_config.get("parameter_names", {}):
            # Set resolution to highest quality available (1080p preferred)
            if "1080p" in supported_resolutions:
                input_data["resolution"] = "1080p"  # Always use 1080p for highest quality
            elif "720p" in supported_resolutions:
                input_data["resolution"] = "720p"
        
        logger.info(
            f"Using aspect ratio '{aspect_ratio}' with resolution '{input_data.get('resolution', 'default')}'",
            extra={
                "job_id": str(job_id),
                "aspect_ratio": aspect_ratio,
                "resolution": input_data.get("resolution"),
                "model": selected_model_key
            }
        )
    else:
        # Fall back to default resolution logic if aspect ratio not supported or not provided
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

    # IMPORTANT: We do NOT pass audio parameters to any model
    # All models generate video-only clips. Original audio is synced in composer.
    # This ensures we use the user's original audio file, not AI-generated audio.
    
    # Add image(s) if available (parameter name varies by model)
    # Use parameter name from model config (e.g., "start_image" for Kling, "image" for Veo3)
    # Veo 3.1 supports multiple reference images (up to 3) via "reference_images" parameter
    # Face Clarity Enhancement: Prioritize character references for face-heavy clips
    if model_config.get("type") in ["image-to-video", "text-and-image-to-video"]:
        parameter_names = model_config.get("parameter_names", {})
        supports_multiple = model_config.get("supports_multiple_images", False)
        max_images = model_config.get("max_reference_images", 1)
        
        # Detect if clip is face-heavy (close-up, mid-shot, portrait, face-focused)
        # Mid-shots and close-ups both need clear facial features - apply same face preservation rules
        # This helps prioritize character reference images for better face preservation
        prompt_lower = clip_prompt.prompt.lower()
        
        # Check camera angle from metadata if available (more reliable than parsing prompt)
        camera_angle = clip_prompt.metadata.get("camera_angle", "").lower() if clip_prompt.metadata else ""
        is_medium_shot = any(term in camera_angle for term in ["medium", "mid", "waist", "bust", "chest", "shoulder", "torso"])
        
        # Check prompt text for face-heavy keywords (close-up, mid-shot, portrait, etc.)
        is_face_heavy = any(keyword in prompt_lower for keyword in [
            # Close-up shots
            "close-up", "closeup", "portrait", "face", "headshot", "extreme close",
            "facial", "head", "head and shoulders", "bust shot", "face fills",
            # Mid-shots (also need clear facial features)
            "medium shot", "mid shot", "waist-up", "waist up", "chest-up", "chest up",
            "shoulder-up", "shoulder up", "torso shot", "upper body", "half body",
            "from waist", "from chest", "from shoulders"
        ]) or is_medium_shot
        
        # Check if we have multiple images and model supports it (e.g., Veo 3.1)
        if supports_multiple and reference_image_urls and len(reference_image_urls) > 0:
            # Use multiple images parameter (e.g., "reference_images" for Veo 3.1)
            reference_images_param = parameter_names.get("reference_images", "reference_images")
            
            # For face-heavy clips, prioritize character references
            if is_face_heavy and image_url and max_images >= 2:
                # Use character reference first, then scene reference (if different from character ref)
                # Note: reference_image_urls contains all images in order: [char_refs..., scene_ref, object_refs...]
                # image_url should be the scene reference if available, otherwise it's the first character ref
                
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Processing face-heavy clip reference images for {selected_model_key}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                        "num_reference_urls": len(reference_image_urls) if reference_image_urls else 0,
                        "image_url_preview": image_url[:100] if image_url else None,
                        "first_ref_preview": reference_image_urls[0][:100] if reference_image_urls else None,
                        "max_images": max_images,
                        "checkpoint": "generator_face_heavy_processing"
                    }
                )

                if reference_image_urls and len(reference_image_urls) > 0:
                    # Check if image_url is different from the first character reference
                    # If they're the same, it means there's no scene reference, so just use character refs
                    if image_url != reference_image_urls[0]:
                        # image_url is scene reference, reference_image_urls[0] is character reference
                        # Explicitly prioritize: [Character Ref 1, Scene Ref]
                        limited_images = [reference_image_urls[0], image_url]
                        
                        # If we have room for more images (e.g., max_images=3), try to add them
                        # We skip reference_image_urls[0] (already added) and try others
                        if max_images > 2:
                            for ref in reference_image_urls[1:]:
                                # Don't duplicate the scene reference (image_url) or first char ref
                                if ref != image_url and len(limited_images) < max_images:
                                    limited_images.append(ref)
                    else:
                        # No scene reference, just use character references
                        limited_images = reference_image_urls[:max_images]
                else:
                    # Fallback: use image_url if no reference_image_urls
                    limited_images = [image_url]
                
                limited_images = limited_images[:max_images]
                
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Face-heavy clip - Using character ref first, then scene ref (if available)",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                        "character_ref_url": reference_image_urls[0][:100] if reference_image_urls else None,
                        "scene_ref_url": image_url[:100] if image_url and (not reference_image_urls or image_url != reference_image_urls[0]) else None,
                        "final_images_count": len(limited_images),
                        "has_scene_ref": image_url != reference_image_urls[0] if reference_image_urls else False,
                        "all_reference_urls": [url[:100] for url in reference_image_urls[:3]] if reference_image_urls else [],
                        "final_limited_urls": [url[:100] for url in limited_images[:3]],
                        "checkpoint": "generator_face_heavy_final"
                    }
                )
                
                # SOLUTION 2 CRITICAL CHECKPOINT: Log final reference images passed to Replicate API
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Final reference images passed to Replicate API for clip {clip_prompt.clip_index}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index,
                        "model": selected_model_key,
                        "is_face_heavy": is_face_heavy,
                        "max_images": max_images,
                        "limited_images_count": len(limited_images),
                        "limited_images_urls": [url[:100] for url in limited_images],
                        "image_url_used": image_url[:100] if image_url else None,
                        "reference_image_urls_used": [url[:100] for url in reference_image_urls[:5]] if reference_image_urls else [],
                        "checkpoint": "generator_replicate_api_input"
                    }
                )
            else:
                # Default: use character references (or scene if no character refs)
                # For single image models, this will be handled in the elif branch
                limited_images = reference_image_urls[:max_images]
                
                # SOLUTION 2 LOGGING: Log non-face-heavy clip handling
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Non-face-heavy clip - using reference_image_urls as-is (up to {max_images} images)",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                        "limited_images_count": len(limited_images),
                        "limited_images_urls": [url[:100] for url in limited_images],
                        "checkpoint": "generator_non_face_heavy"
                    }
                )
            
            input_data[reference_images_param] = limited_images
            logger.info(
                f"SOLUTION 2 CHECKPOINT: Using {len(limited_images)} reference image(s) via '{reference_images_param}' parameter for {selected_model_key} "
                f"(face_heavy={is_face_heavy}, shot_type={'mid-shot' if is_medium_shot else 'close-up' if is_face_heavy else 'wide'})",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                    "model": selected_model_key,
                    "parameter": reference_images_param,
                    "num_images": len(limited_images),
                    "max_images": max_images,
                    "face_heavy": is_face_heavy,
                    "camera_angle": camera_angle if camera_angle else None,
                    "shot_type": "mid-shot" if is_medium_shot else ("close-up" if is_face_heavy else "wide"),
                    "checkpoint": "generator_replicate_input_set"
                }
            )
        elif image_url:
            # Single image parameter - prioritize character reference for face-heavy clips
            image_param = parameter_names.get("image", "start_image")  # Default to "start_image" for backward compatibility
            
            # For face-heavy clips with character references, use character reference as primary
            if is_face_heavy and reference_image_urls and len(reference_image_urls) > 0:
                # Use character reference instead of scene reference for face-heavy clips
                primary_image = reference_image_urls[0]  # Character reference
                input_data[image_param] = primary_image
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Using character reference for face-heavy clip (close-up or mid-shot) via '{image_param}' parameter for {selected_model_key}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                        "model": selected_model_key,
                        "image_param": image_param,
                        "face_heavy": True,
                        "using_character_ref": True,
                        "primary_image_preview": primary_image[:100] if primary_image else None,
                        "camera_angle": camera_angle if camera_angle else None,
                        "shot_type": "mid-shot" if is_medium_shot else "close-up",
                        "checkpoint": "generator_single_image_face_heavy"
                    }
                )
            else:
                # Default: use scene reference (or image_url which may now be character ref after Solution 3 fix)
                input_data[image_param] = image_url
                logger.info(
                    f"SOLUTION 2 CHECKPOINT: Using image_url (may be character or scene ref after Solution 3 fix) via '{image_param}' parameter for {selected_model_key}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index if hasattr(clip_prompt, 'clip_index') else None,
                        "model": selected_model_key,
                        "image_param": image_param,
                        "face_heavy": False,
                        "image_url_preview": image_url[:100] if image_url else None,
                        "has_character_refs": bool(reference_image_urls),
                        "checkpoint": "generator_single_image_default"
                    }
                )
                logger.debug(
                    f"Using single image parameter '{image_param}' for model {selected_model_key}",
                    extra={"job_id": str(job_id), "model": selected_model_key, "image_param": image_param}
                )

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
        # Ensure no audio parameters are passed (we use original audio in composer)
        # Remove any audio-related parameters if they somehow got added
        audio_params = [k for k in input_data.keys() if "audio" in k.lower()]
        if audio_params:
            logger.warning(
                f"Removing audio parameters from input_data: {audio_params}",
                extra={"job_id": str(job_id), "model": selected_model_key, "removed_params": audio_params}
            )
            for param in audio_params:
                del input_data[param]
        
        # Add temperature and seed for Veo 3.1 (only models that support these parameters)
        if selected_model_key == "veo_31":
            if temperature is not None:
                # Validate temperature range
                temperature = max(0.0, min(1.0, float(temperature)))
                input_data["temperature"] = temperature
                logger.info(
                    f"Using LLM-determined temperature: {temperature}",
                    extra={
                        "job_id": str(job_id),
                        "model": selected_model_key,
                        "temperature": temperature,
                        "clip_index": clip_prompt.clip_index
                    }
                )
            
            if seed is not None:
                # Validate seed is integer
                try:
                    seed = int(seed)
                    input_data["seed"] = seed
                    logger.info(
                        f"Using seed for reproducible generation: {seed}",
                        extra={
                            "job_id": str(job_id),
                            "model": selected_model_key,
                            "seed": seed,
                            "clip_index": clip_prompt.clip_index
                        }
                    )
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid seed value: {seed}, skipping seed parameter",
                        extra={"job_id": str(job_id), "model": selected_model_key, "seed": seed}
                    )
        elif temperature is not None or seed is not None:
            # Log that temperature/seed are not supported for this model
            logger.debug(
                f"Temperature/seed parameters not supported for {selected_model_key}, skipping",
                extra={
                    "job_id": str(job_id),
                    "model": selected_model_key,
                    "temperature": temperature,
                    "seed": seed
                }
            )
        
        # Start prediction
        logger.info(
            f"Starting video generation for clip {clip_prompt.clip_index} (video-only, no audio)",
            extra={
                "job_id": str(job_id),
                "model": selected_model_key,
                "target_duration": clip_prompt.duration,
                "resolution": input_data.get("resolution"),
                "aspect_ratio": aspect_ratio,
                "has_image": image_url is not None,
                "input_params": list(input_data.keys()),
                "audio_generation": False,  # Explicitly log that we're not generating audio
                "temperature": input_data.get("temperature"),
                "seed": input_data.get("seed")
            }
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
                # Log detailed error information for debugging
                logger.error(
                    f"Failed to create prediction for {selected_model_key}",
                    extra={
                        "job_id": str(job_id),
                        "model": selected_model_key,
                        "replicate_string": model_config.get("replicate_string", "unknown"),
                        "version": model_version[:20] if isinstance(model_version, str) and len(model_version) > 20 else model_version,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "input_params": list(input_data.keys()),
                        "clip_index": clip_prompt.clip_index
                    }
                )
                if "invalid version" in error_str or "not permitted" in error_str or "422" in error_str:
                    # Version hash might be invalid/expired, raise clearer error
                    replicate_string = model_config.get("replicate_string", "unknown")
                    raise GenerationError(
                        f"Invalid model version or permission denied: {replicate_string}:{model_version[:16]}... "
                        f"Error: {str(e)}. Please check your model version configuration or API token permissions."
                    ) from e
                raise
        
        # Poll for completion with adaptive interval (faster when close to completion)
        start_time = time.time()
        base_poll_interval = 3  # Base polling interval (3 seconds)
        fast_poll_interval = 1  # Fast polling when close to completion (1 second)
        fast_poll_threshold = 0.8  # Switch to fast polling at 80% of estimated time
        
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
            elapsed = time.time() - start_time
            
            # Kling model can take longer - increase timeout to 240s (4 minutes) for reliable generation
            # Some clips may take 150-200s, so 240s provides buffer
            timeout_seconds = int(os.getenv("VIDEO_GENERATION_TIMEOUT_SECONDS", "240"))
            if elapsed > timeout_seconds:
                # Wrap TimeoutError as RetryableError so it can be retried
                raise RetryableError(f"Clip generation timeout after {elapsed:.1f}s")
            
            # Use adaptive polling: faster when close to estimated completion
            if elapsed >= estimated_clip_time * fast_poll_threshold:
                poll_interval = fast_poll_interval
            else:
                poll_interval = base_poll_interval
            
            await asyncio.sleep(poll_interval)
            
            # Reload to get latest status (check immediately after sleep for faster completion detection)
            prediction.reload()
            
            # Early exit: if status changed to success/failure, skip remaining loop
            if prediction.status in ["succeeded", "failed", "canceled"]:
                break
            
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
            
            # IMPORTANT: Strip audio from video to ensure video-only clips
            # Some models (like Veo 3.1) generate audio by default, but we use original audio in composer
            video_bytes = await strip_audio_from_video_bytes(video_bytes, job_id=job_id)
            
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
            
            # Fire-and-forget thumbnail generation (async, non-blocking)
            try:
                from modules.video_generator.thumbnail_generator import generate_clip_thumbnail
                asyncio.create_task(
                    generate_clip_thumbnail(
                        clip_url=final_url,
                        job_id=job_id,
                        clip_index=clip_prompt.clip_index
                    )
                )
                logger.debug(
                    f"Started thumbnail generation task for clip {clip_prompt.clip_index}",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
            except Exception as e:
                # Don't fail video generation if thumbnail task creation fails
                logger.warning(
                    f"Failed to start thumbnail generation task: {e}",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
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
            
            # Build metadata dict with seed if available
            clip_metadata = {}
            if seed is not None:
                clip_metadata["generation_seed"] = seed
            
            return Clip(
                clip_index=clip_prompt.clip_index,
                video_url=final_url,
                actual_duration=actual_duration,
                target_duration=clip_prompt.duration,  # This is the original target (before buffer)
                original_target_duration=original_target_duration,  # Preserved for Part 2 compensation
                duration_diff=actual_duration - clip_prompt.duration,
                status="success",
                cost=cost,
                retry_count=0,
                generation_time=generation_time,
                metadata=clip_metadata
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
            
            # Check for content moderation/safety filter errors
            error_str = str(prediction.error).lower()
            if "flagged as sensitive" in error_str or "e005" in error_str or "sensitive" in error_str:
                # Content moderation error - try sanitizing prompt and retry
                from modules.video_generator.prompt_sanitizer import sanitize_prompt_for_content_moderation
                
                logger.warning(
                    f"Content moderation error for clip {clip_prompt.clip_index}, attempting prompt sanitization",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index,
                        "error": str(prediction.error),
                        "prompt_preview": clip_prompt.prompt[:100] if clip_prompt.prompt else None,
                        "has_reference_images": bool(reference_image_urls or image_url)
                    }
                )
                
                # Sanitize the prompt
                sanitized_prompt = sanitize_prompt_for_content_moderation(clip_prompt.prompt, job_id=str(job_id))
                
                # If prompt was modified, make it retryable so we can try again with sanitized version
                if sanitized_prompt != clip_prompt.prompt:
                    logger.info(
                        f"Prompt sanitized for clip {clip_prompt.clip_index}, will retry with sanitized version",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_prompt.clip_index,
                            "original_preview": clip_prompt.prompt[:100],
                            "sanitized_preview": sanitized_prompt[:100]
                        }
                    )
                    # Raise as RetryableError so it can be retried with sanitized prompt
                    # The retry logic will need to use the sanitized prompt
                    raise RetryableError(
                        f"Content moderation error (prompt sanitized, retryable): {prediction.error}"
                    )
                else:
                    # Prompt couldn't be sanitized - try fallback to Kling Turbo (text-only, no reference images)
                    logger.warning(
                        f"Content moderation error for clip {clip_prompt.clip_index} - prompt could not be sanitized, "
                        f"will fallback to Kling Turbo (text-only)",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_prompt.clip_index,
                            "error": str(prediction.error),
                            "fallback_model": "kling_v25_turbo"
                        }
                    )
                    # Raise as RetryableError with special marker for content moderation fallback
                    raise RetryableError(
                        f"Content moderation error (fallback to Kling Turbo): {prediction.error}"
                    )
            
            # Check for transient infrastructure errors before raising GenerationError
            error_str = str(prediction.error).lower()
            if "internal error" in error_str or "code 13" in error_str or "try again later" in error_str:
                # Transient infrastructure error - should be retryable
                logger.warning(
                    f"Transient infrastructure error for clip {clip_prompt.clip_index}, marking as retryable",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_prompt.clip_index,
                        "error": str(prediction.error)
                    }
                )
                raise RetryableError(f"Internal error (transient, retryable): {prediction.error}")
            
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
        elif "internal error" in error_str or "code 13" in error_str or "try again later" in error_str:
            # Transient infrastructure error - should be retryable
            logger.warning(
                f"Transient infrastructure error detected, marking as retryable",
                extra={
                    "job_id": str(job_id) if job_id else None,
                    "error": str(e),
                    "error_type": "infrastructure_error"
                }
            )
            raise RetryableError(f"Internal error (transient, retryable): {str(e)}") from e
        elif "flagged as sensitive" in error_str or "e005" in error_str or "sensitive" in error_str:
            # Content moderation error - provide clearer message
            logger.error(
                f"Content moderation error detected",
                extra={
                    "job_id": str(job_id) if job_id else None,
                    "error": str(e),
                    "error_type": "content_moderation"
                }
            )
            raise GenerationError(
                f"Content moderation: The prompt or reference images were flagged as sensitive "
                f"by Veo 3.1's safety filters. Please modify the prompt or use different reference images. "
                f"Error: {str(e)}"
            ) from e
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
        elif "internal error" in error_str or "code 13" in error_str or "try again later" in error_str:
            # Transient infrastructure error - should be retryable
            raise RetryableError(f"Internal error (transient, retryable): {str(e)}") from e
        elif "flagged as sensitive" in error_str or "e005" in error_str or "sensitive" in error_str:
            # Content moderation error - provide clearer message
            raise GenerationError(
                f"Content moderation: The prompt or reference images were flagged as sensitive "
                f"by Veo 3.1's safety filters. Please modify the prompt or use different reference images. "
                f"Error: {str(e)}"
            ) from e
        else:
            raise GenerationError(f"Generation error: {str(e)}") from e

