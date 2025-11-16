"""
Main entry point for video generation.

Orchestrates parallel clip generation with retry logic and budget enforcement.
"""
import asyncio
import os
import time
import io
from typing import Optional, Dict, List, Union, Tuple
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
            char_url = cp.character_reference_urls[0]
            if char_url not in unique_urls:
                unique_urls[char_url] = "character"
        
        # Scene reference (only if no character ref for this clip)
        if cp.scene_reference_url:
            if cp.scene_reference_url not in unique_urls:
                unique_urls[cp.scene_reference_url] = "scene"
    
    return unique_urls


async def pre_download_images(
    unique_urls: Dict[str, str],
    job_id: UUID
) -> Dict[str, Optional[Union[str, io.BytesIO]]]:
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
    
    async def download_one(url: str) -> Tuple[str, Optional[Union[str, io.BytesIO]]]:
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
) -> Tuple[Clips, list[dict]]:
    """
    Generate all video clips in parallel.
    
    Args:
        job_id: Job ID
        clip_prompts: ClipPrompts from Prompt Generator
        
    Returns:
        Clips model with all generated clips
        
    Raises:
        BudgetExceededError: If budget would be exceeded
        PipelineError: If <3 clips generated successfully
    """
    environment = settings.environment
    settings_dict = get_generation_settings(environment)
    
    # Validate model configuration before starting
    try:
        selected_model_key = get_selected_model()
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
    image_cache: Dict[str, Optional[Union[str, io.BytesIO]]] = {}
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
        image_cache_param: Dict[str, Optional[Union[str, io.BytesIO]]]
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
            events.append({
                "event_type": "video_generation_start",
                "data": {
                    "clip_index": clip_prompt.clip_index,
                    "total_clips": len(clip_prompts.clip_prompts),
                }
            })
            # Download and upload image if available (optional via env)
            # Priority: Character reference images > Scene reference images
            image_url = None
            
            if use_references and clip_prompt.character_reference_urls and len(clip_prompt.character_reference_urls) > 0:
                character_ref_url = clip_prompt.character_reference_urls[0]
                image_url = image_cache_param.get(character_ref_url)
                
                if image_url:
                    logger.debug(
                        f"Using cached character reference for clip {clip_prompt.clip_index}",
                        extra={"job_id": str(job_id)}
                    )
                else:
                    # Fallback: try to download now (in case pre-download failed)
                    logger.warning(
                        f"Character reference not in cache for clip {clip_prompt.clip_index}, downloading now",
                        extra={"job_id": str(job_id)}
                    )
                    image_url = await download_and_upload_image(character_ref_url, job_id)
                    
                    if not image_url and clip_prompt.scene_reference_url:
                        # Try scene reference as fallback
                        image_url = image_cache_param.get(clip_prompt.scene_reference_url)
                        if not image_url:
                            image_url = await download_and_upload_image(clip_prompt.scene_reference_url, job_id)
            
            # Use scene reference images if no character reference available
            elif use_references and clip_prompt.scene_reference_url:
                image_url = image_cache_param.get(clip_prompt.scene_reference_url)
                
                if image_url:
                    logger.debug(
                        f"Using cached scene reference for clip {clip_prompt.clip_index}",
                        extra={"job_id": str(job_id)}
                    )
                else:
                    # Fallback: try to download now
                    logger.warning(
                        f"Scene reference not in cache for clip {clip_prompt.clip_index}, downloading now",
                        extra={"job_id": str(job_id)}
                    )
                    image_url = await download_and_upload_image(clip_prompt.scene_reference_url, job_id)
            
            else:
                # No references available - text-only generation
                logger.debug(
                    f"No reference images for clip {clip_prompt.clip_index}, using prompt-only generation",
                    extra={"job_id": str(job_id)}
                )
                image_url = None
            
            # Progress callback to emit events during polling (defined outside retry loop)
            def progress_callback(progress_event):
                events.append(progress_event)
            
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
                        settings=settings_dict,
                        job_id=job_id,
                        environment=environment,
                        extra_context=None,
                        progress_callback=progress_callback,
                    )
                    
                    logger.info(
                        f"Clip {clip_prompt.clip_index} generated successfully",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    
                    # Emit completion event
                    events.append({
                        "event_type": "video_generation_complete",
                        "data": {
                            "clip_index": clip_prompt.clip_index,
                            "video_url": clip.video_url,
                            "duration": clip.actual_duration,
                            "cost": float(clip.cost),
                        }
                    })
                    return clip
                    
                except RetryableError as e:
                    if attempt < 2:
                        delay = 2 * (2 ** attempt)  # 2s, 4s, 8s
                        logger.warning(
                            f"Clip {clip_prompt.clip_index} failed (retryable), retrying in {delay}s",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "attempt": attempt + 1,
                                "error": str(e)
                            }
                        )
                        # Emit retry event
                        events.append({
                            "event_type": "video_generation_retry",
                            "data": {
                                "clip_index": clip_prompt.clip_index,
                                "attempt": attempt + 1,
                                "delay_seconds": delay,
                                "error": str(e),
                            }
                        })
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
                        events.append({
                            "event_type": "video_generation_failed",
                            "data": {
                                "clip_index": clip_prompt.clip_index,
                                "error": str(e),
                            }
                        })
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
                    events.append({
                        "event_type": "video_generation_failed",
                        "data": {
                            "clip_index": clip_prompt.clip_index,
                            "error": str(e),
                        }
                    })
                    return None
            
            return None
    
    # Generate all clips in parallel
    start_time = time.time()
    tasks = [generate_with_retry(cp, image_cache) for cp in clip_prompts.clip_prompts]
    results = await asyncio.gather(*tasks)
    
    # Filter successful clips
    successful = [r for r in results if r is not None]
    failed = len(results) - len(successful)
    
    total_generation_time = time.time() - start_time
    
    logger.info(
        f"Generation complete: {len(successful)} successful, {failed} failed",
        extra={
            "job_id": str(job_id),
            "successful": len(successful),
            "failed": failed,
            "total_time": total_generation_time
        }
    )
    
    # Validate minimum clips (configurable)
    min_clips = int(os.getenv("VIDEO_GENERATOR_MIN_CLIPS", "3"))
    require_all_clips = os.getenv("VIDEO_GENERATOR_REQUIRE_ALL_CLIPS", "false").lower() == "true"
    
    if require_all_clips:
        # Require ALL clips to succeed before composition
        expected_clips = len(clip_prompts.clip_prompts)
        if len(successful) < expected_clips:
            raise PipelineError(
                f"Not all clips generated: {len(successful)}/{expected_clips} successful. "
                f"All clips must succeed when VIDEO_GENERATOR_REQUIRE_ALL_CLIPS=true. "
                f"Failed clips: {failed}"
            )
    else:
        # Only require minimum clips (default behavior)
        if len(successful) < min_clips:
            raise PipelineError(
                f"Insufficient clips generated: {len(successful)} < {min_clips} (minimum required). "
                f"Failed clips: {failed}. "
                f"Set VIDEO_GENERATOR_REQUIRE_ALL_CLIPS=true to require all clips to succeed."
            )
    
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

