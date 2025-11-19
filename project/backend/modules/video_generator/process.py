"""
Main entry point for video generation.

Orchestrates parallel clip generation with retry logic and budget enforcement.
"""
import asyncio
import os
import time
import io
import random
import re
from typing import Optional, Dict, List, Union, Tuple, Callable, Any
from uuid import UUID
from decimal import Decimal

from shared.models.video import ClipPrompts, Clips, Clip, ClipPrompt
from shared.models.scene import ScenePlan
from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import BudgetExceededError, PipelineError, RetryableError
from shared.logging import get_logger
from api_gateway.services.budget_helpers import get_budget_limit

from modules.video_generator.config import get_generation_settings, get_selected_model, get_model_config
from modules.video_generator.cost_estimator import estimate_total_cost
from modules.video_generator.generator import generate_video_clip
from modules.video_generator.image_handler import download_and_upload_image
from modules.video_generator.model_validator import validate_model_config

logger = get_logger("video_generator.process")


def extract_unique_image_urls(clip_prompts: List[ClipPrompt]) -> Dict[str, str]:
    """
    Extract unique image URLs from all clip prompts.
    
    Args:
        clip_prompts: List of ClipPrompt objects
        
    Returns:
        Dict mapping: {url: priority_type} where priority_type is "character" or "scene"
        Character URLs take priority over scene URLs for same clip
    """
    unique_urls = {}  # {url: priority_type}
    
    for cp in clip_prompts:
        # Character references take priority
        if cp.character_reference_urls and len(cp.character_reference_urls) > 0:
            for char_url in cp.character_reference_urls:
                if char_url not in unique_urls:
                    unique_urls[char_url] = "character"
        
        # Scene reference
        if cp.scene_reference_url:
            if cp.scene_reference_url not in unique_urls:
                unique_urls[cp.scene_reference_url] = "scene"
        
        # Object references
        if cp.object_reference_urls and len(cp.object_reference_urls) > 0:
            for obj_url in cp.object_reference_urls:
                if obj_url not in unique_urls:
                    unique_urls[obj_url] = "object"
    
    return unique_urls


async def pre_download_images(
    unique_urls: Dict[str, str],
    job_id: UUID
) -> Dict[str, Optional[str]]:
    """
    Pre-download all unique images in parallel.
    
    Args:
        unique_urls: Dict mapping URL to priority type
        job_id: Job ID for logging
        
    Returns:
        Dict mapping original URL to Replicate-ready URL/object
    """
    logger.info(
        f"Pre-downloading {len(unique_urls)} unique reference images",
        extra={"job_id": str(job_id)}
    )
    
    async def download_one(url: str) -> Tuple[str, Optional[str]]:
        try:
            result = await download_and_upload_image(url, job_id)
            return (url, result)
        except Exception as e:
            logger.warning(
                f"Pre-download failed for {url}: {e}",
                extra={"job_id": str(job_id), "url": url}
            )
            return (url, None)
    
    # Download all images in parallel
    tasks = [download_one(url) for url in unique_urls.keys()]
    results = await asyncio.gather(*tasks)
    
    # Build cache dictionary
    image_cache = {url: result for url, result in results}
    
    successful = sum(1 for r in results if r[1] is not None)
    logger.info(
        f"Pre-download complete: {successful}/{len(unique_urls)} images downloaded",
        extra={"job_id": str(job_id), "successful": successful, "total": len(unique_urls)}
    )
    
    return image_cache


async def process(
    job_id: UUID,
    clip_prompts: ClipPrompts,
    plan: Optional[ScenePlan] = None,
    event_publisher: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    video_model: str = None,
    aspect_ratio: str = "16:9",
) -> Tuple[Clips, list[dict]]:
    """
    Generate all video clips in parallel.
    
    Args:
        job_id: Job ID
        clip_prompts: ClipPrompts from Prompt Generator
        plan: Optional ScenePlan for context
        event_publisher: Optional async callback(event_type, data) to publish events in real-time
        video_model: Video generation model to use (kling_v21, kling_v25_turbo, hailuo_23, wan_25_i2v, veo_31)
                    If None, falls back to VIDEO_MODEL environment variable
        aspect_ratio: Aspect ratio for video generation (default: "16:9")
        
    Returns:
        Clips model with all generated clips
        
    Raises:
        BudgetExceededError: If budget would be exceeded
        PipelineError: If <3 clips generated successfully
    """
    environment = settings.environment
    settings_dict = get_generation_settings(environment)
    
    # Use provided video_model or fall back to environment variable
    if video_model is None:
        selected_model_key = get_selected_model()
    else:
        selected_model_key = video_model
    
    # Validate aspect ratio before starting (fail fast if invalid)
    from shared.errors import ValidationError
    from modules.video_generator.config import get_model_config
    model_config = get_model_config(selected_model_key)
    supported_aspect_ratios = model_config.get("aspect_ratios", ["16:9"])
    if aspect_ratio not in supported_aspect_ratios:
        raise ValidationError(
            f"Aspect ratio '{aspect_ratio}' not supported for model '{selected_model_key}'. "
            f"Supported: {supported_aspect_ratios}. "
            f"This error prevents all clips from being generated."
        )
    
    # Validate model configuration before starting
    try:
        model_config = get_model_config(selected_model_key)
        is_valid, error_msg = await validate_model_config(selected_model_key, model_config)
        if not is_valid:
            logger.error(
                f"Model validation failed for {selected_model_key}: {error_msg}",
                extra={"job_id": str(job_id), "model": selected_model_key, "error": error_msg}
            )
            raise PipelineError(
                f"Model configuration invalid: {error_msg}. "
                f"Please check VIDEO_MODEL environment variable or model configuration."
            )
        logger.info(
            f"Model validation passed for {selected_model_key}",
            extra={"job_id": str(job_id), "model": selected_model_key}
        )
    except Exception as e:
        logger.warning(
            f"Model validation error (continuing anyway): {str(e)}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        # Don't fail the job if validation fails - log warning and continue
        # This allows for models that might work but validation API is unavailable
    
    # Budget check before starting
    logger.info(
        f"Estimating costs for {len(clip_prompts.clip_prompts)} clips",
        extra={"job_id": str(job_id)}
    )
    estimated_cost = estimate_total_cost(clip_prompts, environment)
    current_cost = await cost_tracker.get_total_cost(job_id)
    budget_limit = get_budget_limit(environment)
    
    logger.info(
        f"Budget check: current={current_cost}, estimated={estimated_cost}, limit={budget_limit}",
        extra={"job_id": str(job_id)}
    )
    
    if current_cost + estimated_cost > budget_limit:
        raise BudgetExceededError(
            f"Estimated cost {estimated_cost} would exceed budget {budget_limit}. "
            f"Current cost: {current_cost}"
        )
    
    # Get concurrency limit (default: 5 for optimal balance of speed and reliability)
    # Higher concurrency (8+) can cause Replicate queue delays, making clips slower
    # Lower concurrency (4-5) reduces queue contention, improving per-clip completion time
    # Replicate allows 600 predictions/min, but queue delays occur with high concurrent requests
    concurrency = int(os.getenv("VIDEO_GENERATOR_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)
    
    # Optional: Add client-side rate limiter for extra safety
    # See PRD_video_generator_weaknesses_analysis.md for implementation
    
    logger.info(
        f"Starting parallel generation: {len(clip_prompts.clip_prompts)} clips, {concurrency} concurrent",
        extra={"job_id": str(job_id)}
    )
    
    # Reference images enabled/disabled via USE_REFERENCE_IMAGES env var
    use_references = settings.use_reference_images
    if not use_references:
        logger.info(
            "Reference images disabled (USE_REFERENCE_IMAGES=false), using text-only mode",
            extra={"job_id": str(job_id)}
        )
    # Initialize image cache (always defined, even if empty)
    image_cache: Dict[str, Optional[str]] = {}
    if use_references:
        try:
            unique_urls = extract_unique_image_urls(clip_prompts.clip_prompts)
            image_cache = await pre_download_images(unique_urls, job_id)
            logger.info(
                f"Image cache ready: {len([v for v in image_cache.values() if v is not None])}/{len(image_cache)} pre-downloaded",
                extra={"job_id": str(job_id)}
            )
        except Exception as e:
            logger.warning(
                f"Failed to pre-download images, will download on-demand: {e}",
                extra={"job_id": str(job_id)}
            )
            # image_cache remains empty dict, will download on-demand
    
    # Collect events for UI (published by orchestrator)
    events: list[dict] = []
    # We intentionally do not build extra scene plan context here.
    # The prompt generator outputs are considered final and self-contained.
    
    async def generate_with_retry(
        clip_prompt: ClipPrompt,
        image_cache_param: Dict[str, Optional[str]]
    ) -> Optional[Clip]:
        """
        Generate clip with retry logic.
        
        Args:
            clip_prompt: ClipPrompt to generate
            image_cache_param: Pre-downloaded image cache
            
        Returns:
            Clip if successful, None if failed after retries
        """
        async with semaphore:
            # Emit start event for this clip
            start_event = {
                "event_type": "video_generation_start",
                "data": {
                    "clip_index": clip_prompt.clip_index,
                    "total_clips": len(clip_prompts.clip_prompts),
                }
            }
            events.append(start_event)
            # Publish immediately if event publisher is provided
            if event_publisher:
                try:
                    await event_publisher("video_generation_start", start_event["data"])
                except Exception as e:
                    logger.warning(f"Failed to publish start event: {e}", extra={"job_id": str(job_id)})
            # Download and upload images if available (optional via env)
            # Veo 3.1 supports multiple reference images (up to 3): character + scene references
            # PHASE 1: Enforce text-only mode when USE_REFERENCE_IMAGES=false
            # This defensive check ensures the flag is respected even if upstream
            # reference mapping had issues or ClipPrompt contains reference URLs
            image_url = None  # Single image (backward compatibility)
            reference_image_urls = []  # Multiple images for Veo 3.1

            if not use_references:
                # Force text-only mode - guarantee no reference images are used
                logger.debug(
                    f"Text-only mode enforced for clip {clip_prompt.clip_index}",
                    extra={"job_id": str(job_id)}
                )
                image_url = None
                reference_image_urls = []
            else:
                # Detect if clip is face-heavy (close-up, mid-shot, portrait, face-focused)
                # Face-heavy clips need ALL character references prioritized for better face clarity
                prompt_lower = clip_prompt.prompt.lower()
                camera_angle = clip_prompt.metadata.get("camera_angle", "").lower() if clip_prompt.metadata else ""
                is_medium_shot = any(term in camera_angle for term in ["medium", "mid", "waist", "bust", "chest", "shoulder", "torso"])
                
                is_face_heavy = any(keyword in prompt_lower for keyword in [
                    # Close-up shots
                    "close-up", "closeup", "portrait", "face", "headshot", "extreme close",
                    "facial", "head", "head and shoulders", "bust shot", "face fills",
                    # Mid-shots (also need clear facial features)
                    "medium shot", "mid shot", "waist-up", "waist up", "chest-up", "chest up",
                    "shoulder-up", "shoulder up", "torso shot", "upper body", "half body",
                    "from waist", "from chest", "from shoulders"
                ]) or is_medium_shot
                
                # Collect all available reference images (character + scene + object)
                # For face-heavy clips: Prioritize ALL character references before scene/objects
                # For other clips: Character references (limited), then scene, then objects
                # Veo 3.1 supports up to 3 reference images total
                collected_urls = []
                max_reference_images = 3  # Veo 3.1 limit, other models will limit further in generator
                
                # Add character reference URLs
                # FACE-HEAVY CLIPS: Use ALL character references (no artificial limit)
                # OTHER CLIPS: Limit to 2 to leave room for scene/objects
                character_refs_added = 0
                if clip_prompt.character_reference_urls:
                    if is_face_heavy:
                        # Face-heavy clips: Prioritize ALL character references
                        max_char_refs = len(clip_prompt.character_reference_urls)  # No limit for face-heavy
                        logger.info(
                            f"Face-heavy clip detected - prioritizing ALL {len(clip_prompt.character_reference_urls)} character reference(s) for clip {clip_prompt.clip_index}",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "num_character_refs": len(clip_prompt.character_reference_urls),
                                "shot_type": "mid-shot" if is_medium_shot else "close-up",
                                "camera_angle": camera_angle if camera_angle else None
                            }
                        )
                    else:
                        # Other clips: Limit to 2 to leave room for scene/objects
                        max_char_refs = min(len(clip_prompt.character_reference_urls), 2)
                    
                    for char_ref_url in clip_prompt.character_reference_urls[:max_char_refs]:
                        if len(collected_urls) >= max_reference_images:
                            break
                        cached_url = image_cache_param.get(char_ref_url)
                        if cached_url:
                            collected_urls.append(cached_url)
                            character_refs_added += 1
                            logger.debug(
                                f"Using cached character reference for clip {clip_prompt.clip_index}",
                                extra={"job_id": str(job_id), "url": char_ref_url[:50]}
                            )
                        else:
                            # Download if not cached
                            downloaded_url = await download_and_upload_image(char_ref_url, job_id)
                            if downloaded_url:
                                collected_urls.append(downloaded_url)
                                character_refs_added += 1
                                logger.debug(
                                    f"Downloaded character reference for clip {clip_prompt.clip_index}",
                                    extra={"job_id": str(job_id)}
                                )
                
                # Add scene reference URL if available and we have room (max 3 total)
                # For face-heavy clips: Only add scene if there's room after ALL characters
                if clip_prompt.scene_reference_url and len(collected_urls) < max_reference_images:
                    cached_url = image_cache_param.get(clip_prompt.scene_reference_url)
                    if cached_url:
                        collected_urls.append(cached_url)
                        logger.debug(
                            f"Using cached scene reference for clip {clip_prompt.clip_index}",
                            extra={"job_id": str(job_id)}
                        )
                    else:
                        # Download if not cached
                        downloaded_url = await download_and_upload_image(clip_prompt.scene_reference_url, job_id)
                        if downloaded_url:
                            collected_urls.append(downloaded_url)
                            logger.debug(
                                f"Downloaded scene reference for clip {clip_prompt.clip_index}",
                                extra={"job_id": str(job_id)}
                            )
                
                # Add object reference URLs if available and we have room (max 3 total)
                # For face-heavy clips: Only add objects if there's room after ALL characters and scene
                if clip_prompt.object_reference_urls and len(collected_urls) < max_reference_images:
                    remaining_slots = 3 - len(collected_urls)
                    max_obj_refs = min(len(clip_prompt.object_reference_urls), remaining_slots)
                    for obj_ref_url in clip_prompt.object_reference_urls[:max_obj_refs]:
                        if len(collected_urls) >= 3:
                            break
                        cached_url = image_cache_param.get(obj_ref_url)
                        if cached_url:
                            collected_urls.append(cached_url)
                            logger.debug(
                                f"Using cached object reference for clip {clip_prompt.clip_index}",
                                extra={"job_id": str(job_id), "url": obj_ref_url[:50]}
                            )
                        else:
                            # Download if not cached
                            downloaded_url = await download_and_upload_image(obj_ref_url, job_id)
                            if downloaded_url:
                                collected_urls.append(downloaded_url)
                                logger.debug(
                                    f"Downloaded object reference for clip {clip_prompt.clip_index}",
                                    extra={"job_id": str(job_id)}
                                )
                
                # Set both single image (backward compatibility) and multiple images
                if collected_urls:
                    reference_image_urls = collected_urls
                    image_url = collected_urls[0]  # First image for backward compatibility
                    logger.info(
                        f"Collected {len(reference_image_urls)} reference image(s) for clip {clip_prompt.clip_index} "
                        f"(face_heavy={is_face_heavy}, {character_refs_added}/{len(clip_prompt.character_reference_urls)} character refs used, "
                        f"shot_type={'mid-shot' if is_medium_shot else 'close-up' if is_face_heavy else 'wide'})",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_prompt.clip_index,
                            "num_images": len(reference_image_urls),
                            "num_character_refs": character_refs_added,
                            "total_character_refs_available": len(clip_prompt.character_reference_urls),
                            "has_character_refs": bool(clip_prompt.character_reference_urls),
                            "has_scene_ref": bool(clip_prompt.scene_reference_url),
                            "has_object_refs": bool(clip_prompt.object_reference_urls),
                            "face_heavy": is_face_heavy,
                            "shot_type": "mid-shot" if is_medium_shot else ("close-up" if is_face_heavy else "wide"),
                            "camera_angle": camera_angle if camera_angle else None
                        }
                    )
                else:
                    # No references available - text-only generation
                    logger.debug(
                        f"No reference images for clip {clip_prompt.clip_index}, using prompt-only generation",
                        extra={"job_id": str(job_id)}
                    )
                    image_url = None
                    reference_image_urls = []
            
            # Progress callback to emit events during polling (defined outside retry loop)
            async def progress_callback(progress_event):
                events.append(progress_event)
                # Publish immediately if event publisher is provided
                if event_publisher:
                    try:
                        event_type = progress_event.get("event_type", "message")
                        event_data = progress_event.get("data", {})
                        await event_publisher(event_type, event_data)
                    except Exception as e:
                        logger.warning(f"Failed to publish progress event: {e}", extra={"job_id": str(job_id)})
            
            # Retry logic
            for attempt in range(3):
                try:
                    logger.info(
                        f"Generating clip {clip_prompt.clip_index} (attempt {attempt + 1}/3)",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    
                    clip = await generate_video_clip(
                        clip_prompt=clip_prompt,
                        image_url=image_url,
                        reference_image_urls=reference_image_urls,  # Pass multiple images for Veo 3.1
                        settings=settings_dict,
                        job_id=job_id,
                        environment=environment,
                        extra_context=None,
                        progress_callback=progress_callback,
                        video_model=selected_model_key,
                        aspect_ratio=aspect_ratio,
                    )
                    
                    logger.info(
                        f"Clip {clip_prompt.clip_index} generated successfully",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    
                    # Emit completion event
                    complete_event = {
                        "event_type": "video_generation_complete",
                        "data": {
                            "clip_index": clip_prompt.clip_index,
                            "video_url": clip.video_url,
                            "duration": clip.actual_duration,
                            "cost": float(clip.cost),
                        }
                    }
                    events.append(complete_event)
                    # Publish immediately if event publisher is provided
                    if event_publisher:
                        try:
                            await event_publisher("video_generation_complete", complete_event["data"])
                        except Exception as e:
                            logger.warning(f"Failed to publish complete event: {e}", extra={"job_id": str(job_id)})
                    return clip
                    
                except RetryableError as e:
                    if attempt < 2:
                        error_msg = str(e)
                        
                        # Check if this is a content moderation error that requires fallback to Kling Turbo
                        # This happens when Veo 3.1 content moderation fails and prompt can't be sanitized
                        is_fallback_to_kling = (
                            "fallback to kling turbo" in error_msg.lower() or
                            "fallback to kling" in error_msg.lower()
                        )
                        
                        if is_fallback_to_kling and selected_model_key == "veo_31":
                            # Immediately switch to Kling Turbo (text-only) for this clip
                            logger.info(
                                f"Content moderation error detected for clip {clip_prompt.clip_index}, "
                                f"switching to Kling Turbo (text-only) immediately",
                                extra={
                                    "job_id": str(job_id),
                                    "clip_index": clip_prompt.clip_index,
                                    "original_model": selected_model_key,
                                    "fallback_model": "kling_v25_turbo",
                                    "reference_images": False
                                }
                            )
                            # Retry with Kling Turbo (text-only, no reference images)
                            clip = await generate_video_clip(
                                clip_prompt=clip_prompt,
                                image_url=None,  # No reference images for fallback
                                reference_image_urls=[],  # Empty for fallback
                                settings=settings_dict,
                                job_id=job_id,
                                environment=environment,
                                extra_context=None,
                                progress_callback=progress_callback,
                                video_model="kling_v25_turbo",  # Use fallback model
                                aspect_ratio=aspect_ratio,
                            )
                            logger.info(
                                f"Clip {clip_prompt.clip_index} generated successfully with Kling Turbo fallback",
                                extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                            )
                            # Emit completion event
                            complete_event = {
                                "event_type": "video_generation_complete",
                                "data": {
                                    "clip_index": clip_prompt.clip_index,
                                    "video_url": clip.video_url,
                                    "duration": clip.actual_duration,
                                    "cost": float(clip.cost),
                                }
                            }
                            events.append(complete_event)
                            if event_publisher:
                                try:
                                    await event_publisher("video_generation_complete", complete_event["data"])
                                except Exception as e:
                                    logger.warning(f"Failed to publish complete event: {e}", extra={"job_id": str(job_id)})
                            return clip
                        
                        # Check if this is a content moderation error that was sanitized
                        # If so, sanitize the prompt before retrying
                        if "content moderation" in error_msg.lower() or "prompt sanitized" in error_msg.lower():
                            from modules.video_generator.prompt_sanitizer import sanitize_prompt_for_content_moderation
                            
                            original_prompt = clip_prompt.prompt
                            sanitized_prompt = sanitize_prompt_for_content_moderation(original_prompt, job_id=str(job_id))
                            
                            if sanitized_prompt != original_prompt:
                                # Update the prompt for retry
                                clip_prompt.prompt = sanitized_prompt
                                logger.info(
                                    f"Sanitized prompt for clip {clip_prompt.clip_index} before retry",
                                    extra={
                                        "job_id": str(job_id),
                                        "clip_index": clip_prompt.clip_index,
                                        "attempt": attempt + 1,
                                        "original_preview": original_prompt[:100],
                                        "sanitized_preview": sanitized_prompt[:100]
                                    }
                                )
                        
                        # Parse Retry-After from error message if present
                        # Format: "Rate limit error (retry after 30s): ..."
                        retry_after = None
                        retry_after_match = re.search(r'retry after ([\d.]+)s', error_msg, re.IGNORECASE)
                        if retry_after_match:
                            try:
                                retry_after = float(retry_after_match.group(1))
                            except (ValueError, AttributeError):
                                pass
                        
                        # Use Retry-After if available, otherwise exponential backoff
                        if retry_after is not None:
                            # Add jitter (10-20% of retry_after) to desynchronize concurrent retries
                            jitter = random.uniform(0.1, 0.2) * retry_after
                            delay = retry_after + jitter
                            logger.info(
                                f"Using Retry-After header: {retry_after}s + {jitter:.1f}s jitter = {delay:.1f}s",
                                extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                            )
                        else:
                            # Exponential backoff with jitter: 2s, 4s, 8s + random 0-2s
                            base_delay = 2 * (2 ** attempt)
                            jitter = random.uniform(0, 2)
                            delay = base_delay + jitter
                        
                        logger.warning(
                            f"Clip {clip_prompt.clip_index} failed (retryable), retrying in {delay:.1f}s",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "attempt": attempt + 1,
                                "error": str(e),
                                "delay": delay
                            }
                        )
                        # Emit retry event
                        retry_event = {
                            "event_type": "video_generation_retry",
                            "data": {
                                "clip_index": clip_prompt.clip_index,
                                "attempt": attempt + 1,
                                "delay_seconds": delay,
                                "error": str(e),
                            }
                        }
                        events.append(retry_event)
                        # Publish immediately if event publisher is provided
                        if event_publisher:
                            try:
                                await event_publisher("video_generation_retry", retry_event["data"])
                            except Exception as e:
                                logger.warning(f"Failed to publish retry event: {e}", extra={"job_id": str(job_id)})
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Clip {clip_prompt.clip_index} failed after 3 retries",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "error": str(e)
                            }
                        )
                        failed_event = {
                            "event_type": "video_generation_failed",
                            "data": {
                                "clip_index": clip_prompt.clip_index,
                                "error": str(e),
                            }
                        }
                        events.append(failed_event)
                        # Publish immediately if event publisher is provided
                        if event_publisher:
                            try:
                                await event_publisher("video_generation_failed", failed_event["data"])
                            except Exception as e:
                                logger.warning(f"Failed to publish failed event: {e}", extra={"job_id": str(job_id)})
                        return None
                except Exception as e:
                    # Non-retryable error
                    logger.error(
                        f"Clip {clip_prompt.clip_index} failed (non-retryable): {e}",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_prompt.clip_index,
                            "error": str(e)
                        }
                    )
                    failed_event = {
                        "event_type": "video_generation_failed",
                        "data": {
                            "clip_index": clip_prompt.clip_index,
                            "error": str(e),
                        }
                    }
                    events.append(failed_event)
                    # Publish immediately if event publisher is provided
                    if event_publisher:
                        try:
                            await event_publisher("video_generation_failed", failed_event["data"])
                        except Exception as e:
                            logger.warning(f"Failed to publish failed event: {e}", extra={"job_id": str(job_id)})
                    return None
            
            return None
    
    # Generate all clips in parallel
    start_time = time.time()
    tasks = [generate_with_retry(cp, image_cache) for cp in clip_prompts.clip_prompts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Separate successful clips, failed clips, and track errors
    # Note: generate_with_retry returns None on failure, not an exception
    successful = []
    failed_clips = []  # List of (clip_prompt, error_info) tuples
    rate_limit_failures = 0
    
    for i, result in enumerate(results):
        clip_prompt = clip_prompts.clip_prompts[i]
        
        if isinstance(result, Exception):
            # Exception propagated (shouldn't happen, but handle it)
            error_str = str(result).lower()
            is_rate_limit = (
                "rate limit" in error_str or 
                "429" in error_str or
                "retry after" in error_str
            )
            if is_rate_limit:
                rate_limit_failures += 1
            failed_clips.append((clip_prompt, {
                "error": str(result),
                "is_rate_limit": is_rate_limit,
                "error_type": type(result).__name__
            }))
        elif result is not None:
            successful.append(result)
        else:
            # None returned - clip failed after retries
            # Check events for error classification
            error_info = {"error": "Generation failed after retries", "is_rate_limit": False, "error_type": "Unknown"}
            
            # Look for rate limit errors in events
            for event in events:
                if event.get("event_type") == "video_generation_failed":
                    event_data = event.get("data", {})
                    if event_data.get("clip_index") == clip_prompt.clip_index:
                        error_msg = event_data.get("error", "")
                        error_str = str(error_msg).lower()
                        is_rate_limit = (
                            "rate limit" in error_str or 
                            "429" in error_str or
                            "retry after" in error_str
                        )
                        if is_rate_limit:
                            rate_limit_failures += 1
                        error_info = {
                            "error": error_msg,
                            "is_rate_limit": is_rate_limit,
                            "error_type": "RetryableError" if is_rate_limit else "GenerationError"
                        }
                        break
            
            failed_clips.append((clip_prompt, error_info))
    
    failed = len(failed_clips)
    total_generation_time = time.time() - start_time
    
    logger.info(
        f"Generation complete: {len(successful)} successful, {failed} failed (rate_limit: {rate_limit_failures})",
        extra={
            "job_id": str(job_id),
            "successful": len(successful),
            "failed": failed,
            "rate_limit_failures": rate_limit_failures,
            "total_time": total_generation_time
        }
    )
    
    # Validate minimum clips (configurable)
    min_clips = int(os.getenv("VIDEO_GENERATOR_MIN_CLIPS", "3"))
    require_all_clips = os.getenv("VIDEO_GENERATOR_REQUIRE_ALL_CLIPS", "false").lower() == "true"
    auto_retry_on_failure = os.getenv("VIDEO_GENERATOR_AUTO_RETRY_ON_FAILURE", "true").lower() == "true"
    expected_clips = len(clip_prompts.clip_prompts)
    
    # Determine if we need to retry failed clips
    # Retry if:
    # 1. We have insufficient clips (< min_clips), OR
    # 2. require_all_clips=true and we don't have all clips yet
    needs_retry = (
        len(failed_clips) > 0 and 
        auto_retry_on_failure and 
        (len(successful) < min_clips or (require_all_clips and len(successful) < expected_clips))
    )
    
    # If we need to retry, try automatic retry (regardless of error type)
    # This prevents the "Insufficient clips" crash by giving failed clips another chance
    retry_successful = []  # Initialize to avoid NameError in error messages
    if needs_retry:
        retry_reason = (
            f"require_all_clips=true and {len(successful)}/{expected_clips} clips" 
            if require_all_clips and len(successful) < expected_clips
            else f"insufficient clips ({len(successful)} < {min_clips})"
        )
        logger.warning(
            f"{retry_reason} with {len(failed_clips)} failures. "
            f"Attempting automatic retry with reduced concurrency... (rate_limit_failures: {rate_limit_failures})",
            extra={
                "job_id": str(job_id),
                "successful": len(successful),
                "min_required": min_clips,
                "expected_clips": expected_clips if require_all_clips else None,
                "require_all_clips": require_all_clips,
                "total_failures": len(failed_clips),
                "rate_limit_failures": rate_limit_failures
            }
        )
        
        # Reduce concurrency for retry (half of original, minimum 2)
        retry_concurrency = max(2, concurrency // 2)
        retry_semaphore = asyncio.Semaphore(retry_concurrency)
        
        logger.info(
            f"Retrying {len(failed_clips)} failed clips with reduced concurrency: {retry_concurrency}",
            extra={"job_id": str(job_id), "retry_concurrency": retry_concurrency}
        )
        
        # Retry only the failed clips
        async def retry_failed_clip(clip_prompt: ClipPrompt, error_info: dict) -> Optional[Clip]:
            async with retry_semaphore:
                try:
                    # Check if this is a content moderation error that should fallback to Kling Turbo
                    error_str = error_info.get("error", "").lower()
                    is_content_moderation = (
                        "content moderation" in error_str or 
                        "flagged as sensitive" in error_str or
                        "e005" in error_str
                    )
                    
                    # Determine which model to use for retry
                    retry_model = selected_model_key
                    use_reference_images_retry = use_references
                    
                    if is_content_moderation and selected_model_key == "veo_31":
                        # Fallback to Kling Turbo for content moderation errors
                        # Kling Turbo doesn't support reference images, so use text-only
                        retry_model = "kling_v25_turbo"
                        use_reference_images_retry = False
                        logger.info(
                            f"Retrying clip {clip_prompt.clip_index} with Kling Turbo (text-only) "
                            f"due to content moderation error",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "original_model": selected_model_key,
                                "fallback_model": retry_model,
                                "reference_images": False
                            }
                        )
                    
                    # Re-download images if needed (only if not using fallback model)
                    image_url = None  # Single image (backward compatibility)
                    reference_image_urls = []  # Multiple images for Veo 3.1
                    
                    if use_reference_images_retry:
                        # Detect if clip is face-heavy (same logic as main generation)
                        prompt_lower = clip_prompt.prompt.lower()
                        camera_angle = clip_prompt.metadata.get("camera_angle", "").lower() if clip_prompt.metadata else ""
                        is_medium_shot = any(term in camera_angle for term in ["medium", "mid", "waist", "bust", "chest", "shoulder", "torso"])
                        
                        is_face_heavy = any(keyword in prompt_lower for keyword in [
                            "close-up", "closeup", "portrait", "face", "headshot", "extreme close",
                            "facial", "head", "head and shoulders", "bust shot", "face fills",
                            "medium shot", "mid shot", "waist-up", "waist up", "chest-up", "chest up",
                            "shoulder-up", "shoulder up", "torso shot", "upper body", "half body",
                            "from waist", "from chest", "from shoulders"
                        ]) or is_medium_shot
                        
                        collected_urls = []
                        max_reference_images = 3  # Veo 3.1 limit
                        
                        # Add character reference URLs
                        # FACE-HEAVY CLIPS: Use ALL character references (no artificial limit)
                        # OTHER CLIPS: Limit to 2 to leave room for scene/objects
                        if clip_prompt.character_reference_urls:
                            if is_face_heavy:
                                # Face-heavy clips: Prioritize ALL character references
                                max_char_refs = len(clip_prompt.character_reference_urls)  # No limit for face-heavy
                            else:
                                # Other clips: Limit to 2 to leave room for scene/objects
                                max_char_refs = min(len(clip_prompt.character_reference_urls), 2)
                            
                            for char_ref_url in clip_prompt.character_reference_urls[:max_char_refs]:
                                if len(collected_urls) >= max_reference_images:
                                    break
                                cached_url = image_cache.get(char_ref_url)
                                if cached_url:
                                    collected_urls.append(cached_url)
                                else:
                                    downloaded_url = await download_and_upload_image(char_ref_url, job_id)
                                    if downloaded_url:
                                        collected_urls.append(downloaded_url)
                        
                        # Add scene reference URL if available and we have room (max 3 total)
                        # For face-heavy clips: Only add scene if there's room after ALL characters
                        if clip_prompt.scene_reference_url and len(collected_urls) < max_reference_images:
                            cached_url = image_cache.get(clip_prompt.scene_reference_url)
                            if cached_url:
                                collected_urls.append(cached_url)
                            else:
                                downloaded_url = await download_and_upload_image(clip_prompt.scene_reference_url, job_id)
                                if downloaded_url:
                                    collected_urls.append(downloaded_url)
                        
                        if collected_urls:
                            reference_image_urls = collected_urls
                            image_url = collected_urls[0]  # First image for backward compatibility
                    else:
                        # Text-only mode for fallback (no reference images)
                        logger.debug(
                            f"Using text-only mode for clip {clip_prompt.clip_index} (fallback model)",
                            extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                        )
                    
                    # Generate with fallback model (text-only if content moderation error)
                    clip = await generate_video_clip(
                        clip_prompt=clip_prompt,
                        image_url=image_url,
                        reference_image_urls=reference_image_urls,  # Empty for fallback
                        settings=settings_dict,
                        job_id=job_id,
                        environment=environment,
                        extra_context=None,
                        progress_callback=None,  # Skip progress updates for retries
                        video_model=retry_model,  # Use fallback model if content moderation error
                        aspect_ratio=aspect_ratio,
                    )
                    
                    logger.info(
                        f"Retry successful for clip {clip_prompt.clip_index}",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    return clip
                except Exception as e:
                    logger.warning(
                        f"Retry failed for clip {clip_prompt.clip_index}: {e}",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index, "error": str(e)}
                    )
                    return None
        
        # Retry failed clips with reduced concurrency
        retry_tasks = [retry_failed_clip(cp, err) for cp, err in failed_clips]
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        
        # Add successful retries to successful list
        retry_successful = [r for r in retry_results if r is not None and not isinstance(r, Exception)]
        successful.extend(retry_successful)
        
        retry_failed = len(failed_clips) - len(retry_successful)
        logger.info(
            f"Retry complete: {len(retry_successful)} additional clips succeeded, {retry_failed} still failed",
            extra={
                "job_id": str(job_id),
                "retry_successful": len(retry_successful),
                "retry_failed": retry_failed,
                "total_successful": len(successful)
            }
        )
    
    # Final validation after retry - with dynamic fallback
    allow_partial_failure = os.getenv("VIDEO_GENERATOR_ALLOW_PARTIAL_FAILURE", "true").lower() == "true"
    
    # Calculate final failed count (after retry)
    final_failed_count = len(failed_clips) - len(retry_successful)
    
    if require_all_clips:
        # Require ALL clips to succeed before composition
        if len(successful) < expected_clips:
            raise PipelineError(
                f"Not all clips generated: {len(successful)}/{expected_clips} successful. "
                f"All clips must succeed when VIDEO_GENERATOR_REQUIRE_ALL_CLIPS=true. "
                f"Failed clips: {final_failed_count}"
            )
    else:
        # Check if we have ANY successful clips
        if len(successful) == 0:
            # Absolute failure - no clips generated at all
            # Build detailed error message with per-clip failure information
            error_details = []
            error_summary = {
                "total_clips": len(clip_prompts.clip_prompts),
                "successful": 0,
                "failed": len(failed_clips),
                "rate_limit_failures": rate_limit_failures,
                "failed_clips": []
            }
            
            for clip_prompt, error_info in failed_clips:
                clip_error = {
                    "clip_index": clip_prompt.clip_index,
                    "error": error_info.get("error", "Unknown error"),
                    "error_type": error_info.get("error_type", "Unknown"),
                    "is_rate_limit": error_info.get("is_rate_limit", False),
                    "prompt_preview": clip_prompt.prompt[:100] + "..." if len(clip_prompt.prompt) > 100 else clip_prompt.prompt
                }
                error_summary["failed_clips"].append(clip_error)
                
                # Build human-readable error details
                error_type_label = "Rate Limit" if error_info.get("is_rate_limit") else error_info.get("error_type", "Error")
                error_details.append(
                    f"Clip {clip_prompt.clip_index}: {error_type_label} - {error_info.get('error', 'Unknown error')}"
                )
            
            # Create detailed error message
            base_message = (
                f"Complete failure: 0 clips generated successfully out of {len(clip_prompts.clip_prompts)} clips. "
                f"All clips failed."
            )
            
            if rate_limit_failures > 0:
                base_message += f" {rate_limit_failures} clip(s) failed due to rate limits."
            
            detailed_message = base_message + "\n\nFailed clips:\n" + "\n".join(error_details)
            
            # Create error with detailed information
            error = PipelineError(detailed_message, job_id=job_id)
            # Attach structured error data for API response
            error.error_details = error_summary
            raise error
        elif len(successful) < min_clips:
            # Insufficient clips, but we have at least 1
            if allow_partial_failure:
                # SAFETY VALVE: Continue with fewer clips instead of crashing
                logger.warning(
                    f"Insufficient clips ({len(successful)} < {min_clips}), but continuing with partial success "
                    f"(VIDEO_GENERATOR_ALLOW_PARTIAL_FAILURE=true). Video quality may be reduced.",
                    extra={
                        "job_id": str(job_id),
                        "successful": len(successful),
                        "min_required": min_clips,
                        "total_clips": len(clip_prompts.clip_prompts)
                    }
                )
                # Continue execution - don't crash
            else:
                # Strict mode: crash on insufficient clips
                # Build detailed error message with per-clip failure information
                error_details = []
                error_summary = {
                    "total_clips": len(clip_prompts.clip_prompts),
                    "successful": len(successful),
                    "failed": final_failed_count,
                    "min_required": min_clips,
                    "rate_limit_failures": rate_limit_failures,
                    "failed_clips": []
                }
                
                # Only include failed clips that weren't retried successfully
                for clip_prompt, error_info in failed_clips:
                    # Skip if this clip was retried successfully
                    if any(c.clip_index == clip_prompt.clip_index for c in retry_successful):
                        continue
                    
                    clip_error = {
                        "clip_index": clip_prompt.clip_index,
                        "error": error_info.get("error", "Unknown error"),
                        "error_type": error_info.get("error_type", "Unknown"),
                        "is_rate_limit": error_info.get("is_rate_limit", False),
                        "prompt_preview": clip_prompt.prompt[:100] + "..." if len(clip_prompt.prompt) > 100 else clip_prompt.prompt
                    }
                    error_summary["failed_clips"].append(clip_error)
                    
                    # Build human-readable error details
                    error_type_label = "Rate Limit" if error_info.get("is_rate_limit") else error_info.get("error_type", "Error")
                    error_details.append(
                        f"Clip {clip_prompt.clip_index}: {error_type_label} - {error_info.get('error', 'Unknown error')}"
                    )
                
                rate_limit_msg = f" ({rate_limit_failures} rate limit failures detected)" if rate_limit_failures > 0 else ""
                base_message = (
                    f"Insufficient clips generated: {len(successful)} < {min_clips} (minimum required). "
                    f"Failed clips: {final_failed_count}.{rate_limit_msg} "
                    f"Set VIDEO_GENERATOR_ALLOW_PARTIAL_FAILURE=true to continue with fewer clips. "
                    f"Set VIDEO_GENERATOR_AUTO_RETRY_ON_FAILURE=false to disable automatic retry."
                )
                
                if error_details:
                    detailed_message = base_message + "\n\nFailed clips:\n" + "\n".join(error_details)
                else:
                    detailed_message = base_message
                
                # Create error with detailed information
                error = PipelineError(detailed_message, job_id=job_id)
                # Attach structured error data for API response
                error.error_details = error_summary
                raise error
    
    # Calculate total cost and check budget
    total_cost = sum(c.cost for c in successful)
    current_total = await cost_tracker.get_total_cost(job_id)
    budget_limit = get_budget_limit(environment)
    
    # Mid-generation budget check (warn if exceeded, but don't fail)
    if current_total > budget_limit:
        logger.warning(
            f"Budget exceeded during generation: {current_total} > {budget_limit}",
            extra={
                "job_id": str(job_id),
                "current_cost": float(current_total),
                "budget_limit": float(budget_limit)
            }
        )
    
    logger.info(
        f"Video generation complete: {len(successful)} clips, ${total_cost} total cost",
        extra={
            "job_id": str(job_id),
            "total_clips": len(successful),
            "total_cost": float(total_cost),
            "current_total_cost": float(current_total),
            "generation_time": total_generation_time
        }
    )
    
    return Clips(
        job_id=job_id,
        clips=successful,
        total_clips=len(clip_prompts.clip_prompts),
        successful_clips=len(successful),
        failed_clips=failed,
        total_cost=total_cost,
        total_generation_time=total_generation_time
    ), events

