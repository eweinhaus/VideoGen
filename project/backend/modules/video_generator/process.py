"""
Main entry point for video generation.

Orchestrates parallel clip generation with retry logic and budget enforcement.
"""
import asyncio
import os
import time
from typing import Optional, Tuple
from uuid import UUID
from decimal import Decimal

from shared.models.video import ClipPrompts, Clips, Clip, ClipPrompt
from shared.models.scene import ScenePlan
from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import BudgetExceededError, PipelineError, RetryableError
from shared.logging import get_logger
from api_gateway.services.budget_helpers import get_budget_limit

from modules.video_generator.config import get_generation_settings
from modules.video_generator.cost_estimator import estimate_total_cost
from modules.video_generator.generator import generate_video_clip
from modules.video_generator.image_handler import download_and_upload_image

logger = get_logger("video_generator.process")


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
    
    # Get concurrency limit (default: 3 for safety, avoid rate limits)
    # Replicate allows 600 predictions/min, so 3 concurrent is conservative
    concurrency = int(os.getenv("VIDEO_GENERATOR_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)
    
    # Optional: Add client-side rate limiter for extra safety
    # See PRD_video_generator_weaknesses_analysis.md for implementation
    
    logger.info(
        f"Starting parallel generation: {len(clip_prompts.clip_prompts)} clips, {concurrency} concurrent",
        extra={"job_id": str(job_id)}
    )
    
    # Collect events for UI (published by orchestrator)
    events: list[dict] = []
    # We intentionally do not build extra scene plan context here.
    # The prompt generator outputs are considered final and self-contained.
    
    async def generate_with_retry(clip_prompt: ClipPrompt) -> Optional[Clip]:
        """
        Generate clip with retry logic.
        
        Args:
            clip_prompt: ClipPrompt to generate
            
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
            # Download and upload image if available
            # Priority: Character reference images > Scene reference images
            # Character reference images are used for character appearance consistency
            # Scene reference images are used for scene/background consistency
            image_url = None
            
            # Prioritize character reference images (for character appearance)
            if clip_prompt.character_reference_urls and len(clip_prompt.character_reference_urls) > 0:
                character_ref_url = clip_prompt.character_reference_urls[0]  # Use first character reference
                logger.debug(
                    f"Using character reference image for clip {clip_prompt.clip_index}",
                    extra={"job_id": str(job_id), "character_ref_url": character_ref_url}
                )
                image_url = await download_and_upload_image(
                    character_ref_url,
                    job_id
                )
                if not image_url:
                    logger.warning(
                        f"Character reference image download failed for clip {clip_prompt.clip_index}, falling back to scene reference",
                        extra={"job_id": str(job_id)}
                    )
                    # Fall through to scene reference if character reference download fails
                    if clip_prompt.scene_reference_url:
                        logger.debug(
                            f"Using scene reference image for clip {clip_prompt.clip_index}",
                            extra={"job_id": str(job_id)}
                        )
                        image_url = await download_and_upload_image(
                            clip_prompt.scene_reference_url,
                            job_id
                        )
                        if not image_url:
                            logger.warning(
                                f"Scene reference image download failed for clip {clip_prompt.clip_index}, proceeding text-only",
                                extra={"job_id": str(job_id)}
                            )
            # Use scene reference images if no character reference available
            elif clip_prompt.scene_reference_url:
                logger.debug(
                    f"Using scene reference image for clip {clip_prompt.clip_index}",
                    extra={"job_id": str(job_id)}
                )
                image_url = await download_and_upload_image(
                    clip_prompt.scene_reference_url,
                    job_id
                )
                if not image_url:
                    logger.warning(
                        f"Scene reference image download failed for clip {clip_prompt.clip_index}, proceeding text-only",
                        extra={"job_id": str(job_id)}
                    )
            else:
                # No references available - text-only generation
                logger.debug(
                    f"No reference images for clip {clip_prompt.clip_index}, using prompt-only generation",
                    extra={"job_id": str(job_id)}
                )
                image_url = None
            
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
    tasks = [generate_with_retry(cp) for cp in clip_prompts.clip_prompts]
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
    if len(successful) < min_clips:
        raise PipelineError(
            f"Insufficient clips generated: {len(successful)} < {min_clips} (minimum required). "
            f"Failed clips: {failed}"
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

