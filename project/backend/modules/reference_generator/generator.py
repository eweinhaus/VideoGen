"""
SDXL image generation via Replicate API.

Handles parallel generation, retry logic, and cost tracking.
"""

import asyncio
import time
from decimal import Decimal
from typing import Dict, Any, List, Literal, Tuple, Optional, Callable
from uuid import UUID
import httpx

import replicate
from shared.config import settings
from shared.models.scene import ScenePlan, Scene, Character
from shared.errors import RetryableError, GenerationError, RateLimitError, ValidationError
from shared.retry import retry_with_backoff
from shared.logging import get_logger

logger = get_logger("reference_generator.generator")

# Model version constants
# Using base model name (will use latest version)
# Format: owner/model or owner/model:version_hash
# To pin a specific version, use: stability-ai/sdxl:VERSION_HASH
# To use latest: stability-ai/sdxl (default)
# Cost: ~$0.005 per image
# Speed: ~8-10s per image
# Note: If you need to pin a specific version, set REFERENCE_MODEL_VERSION env var
# Example: REFERENCE_MODEL_VERSION=39ed52f2-78e6-43c4-bc99-403f850fe245
# Verified model name from Replicate API
# Model: stability-ai/sdxl
# Latest version (verified working): 7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc
# Note: Must use version hash format - base name without version returns 404
REFERENCE_MODEL_BASE = "stability-ai/sdxl"
REFERENCE_MODEL_LATEST_VERSION = "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"
# Must use version hash format - base name without version returns 404
REFERENCE_MODEL_PROD = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"
REFERENCE_MODEL_DEV = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"  # Same for consistency


def get_model_version() -> str:
    """
    Get model version based on environment.
    
    Supports:
    - REFERENCE_MODEL_VERSION env var: Pin to specific version hash
      Example: REFERENCE_MODEL_VERSION=39ed52f2-78e6-43c4-bc99-403f850fe245
    - REFERENCE_MODEL_DEV env var: Override for development (full model string)
      Example: REFERENCE_MODEL_DEV=stability-ai/sdxl:VERSION_HASH
    
    Returns:
        Model version string in format: owner/model or owner/model:version_hash
    """
    import os
    
    # Check for version hash override (appends to base model)
    version_hash = os.getenv("REFERENCE_MODEL_VERSION")
    if version_hash:
        return f"{REFERENCE_MODEL_BASE}:{version_hash}"
    
    # Check for full model override (for dev)
    dev_override = os.getenv("REFERENCE_MODEL_DEV")
    if dev_override and settings.environment == "development":
        return dev_override
    
    # Default: Use base model (latest version)
    return REFERENCE_MODEL_PROD


# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    raise


async def generate_image(
    prompt: str,
    image_type: Literal["scene", "character"],
    image_id: str,
    job_id: UUID,
    settings_dict: Optional[Dict[str, Any]] = None,
    retry_count: int = 0
) -> Tuple[bytes, float, Decimal, int]:
    """
    Generate a single reference image with adaptive retry logic.
    
    Args:
        prompt: Synthesized prompt
        image_type: "scene" or "character"
        image_id: Scene or character ID
        job_id: Job ID for tracking
        settings_dict: Optional generation settings (uses defaults if not provided)
        retry_count: Current retry attempt (0 = first attempt, 1 = retry)
        
    Returns:
        Tuple of (image_bytes, generation_time_seconds, cost, final_retry_count)
        
    Raises:
        RetryableError: If retryable error occurs (will be retried by caller)
        GenerationError: If generation fails permanently
    """
    model_version = get_model_version()
    logger.info(
        f"Using Replicate model: {model_version} for {image_type} image {image_id}",
        extra={"job_id": str(job_id), "model_version": model_version, "image_type": image_type, "image_id": image_id}
    )
    
    # Default generation settings
    default_settings = {
        "prompt": prompt,
        "negative_prompt": "blurry, static, low quality, distorted, watermark, text overlay",
        "width": 1024,
        "height": 1024,
        "num_outputs": 1,
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "scheduler": "K_EULER"
        # Note: seed is omitted - Replicate will randomize if not provided
        # If you need deterministic results, set seed to an integer
    }
    
    generation_settings = settings_dict or default_settings
    generation_settings["prompt"] = prompt  # Ensure prompt is set
    
    # Remove seed if it's None (Replicate doesn't accept null for seed)
    if "seed" in generation_settings and generation_settings["seed"] is None:
        del generation_settings["seed"]
    
    start_time = time.time()
    
    try:
        logger.info(
            f"Generating {image_type} image {image_id} for job {job_id} (attempt {retry_count + 1})",
            extra={"job_id": str(job_id), "image_type": image_type, "image_id": image_id, "retry_count": retry_count}
        )
        
        # Call Replicate API with timeout
        output = await asyncio.wait_for(
            asyncio.to_thread(
                client.run,
                model_version,
                input=generation_settings
            ),
            timeout=120.0  # 120s timeout per image
        )
        
        generation_time = time.time() - start_time
        
        # Handle output (may be a list or single FileOutput/URL)
        # Replicate returns FileOutput objects that have a .url property
        if isinstance(output, list):
            output_item = output[0] if len(output) > 0 else None
        else:
            output_item = output
        
        if not output_item:
            raise GenerationError(f"No output returned from Replicate API for {image_id}")
        
        # Extract URL from FileOutput object or use string directly
        # FileOutput objects have a .url property and can be converted to strings
        try:
            if hasattr(output_item, 'url'):
                # FileOutput object - get the URL (which is a string)
                output_url = output_item.url
            else:
                # Try converting to string (FileOutput objects can be converted)
                output_url = str(output_item)
        except Exception as e:
            logger.error(f"Failed to extract URL from Replicate output: {e}", extra={"job_id": str(job_id), "output_type": type(output_item)})
            raise GenerationError(f"Failed to extract URL from Replicate output for {image_id}: {str(e)}")
        
        # Ensure output_url is a string
        if not isinstance(output_url, str):
            output_url = str(output_url)
        
        if not output_url:
            raise GenerationError(f"No output URL returned from Replicate API for {image_id}")
        
        # Download image bytes
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.get(output_url)
            response.raise_for_status()
            image_bytes = response.content
        
        # Extract cost from API response (if available)
        # Replicate API doesn't always return cost in response, so use estimate
        cost = Decimal("0.005")  # Default estimate per image
        
        # Try to extract cost from response metadata if available
        # Note: Replicate API response structure may vary
        if hasattr(output, "cost") or (isinstance(output, dict) and "cost" in output):
            try:
                cost_value = output.cost if hasattr(output, "cost") else output.get("cost")
                if cost_value:
                    cost = Decimal(str(cost_value))
                    logger.info(f"Extracted cost from API response: {cost}")
            except Exception as e:
                logger.warning(f"Failed to extract cost from API response, using estimate: {str(e)}")
        
        logger.info(
            f"Generated {image_type} image {image_id} in {generation_time:.2f}s",
            extra={
                "job_id": str(job_id),
                "image_type": image_type,
                "image_id": image_id,
                "generation_time": generation_time,
                "cost": float(cost),
                "retry_count": retry_count
            }
        )
        
        return image_bytes, generation_time, cost, retry_count
        
    except asyncio.TimeoutError:
        generation_time = time.time() - start_time
        logger.error(
            f"Timeout generating {image_type} image {image_id} after {generation_time:.2f}s",
            extra={"job_id": str(job_id), "image_type": image_type, "image_id": image_id, "retry_count": retry_count}
        )
        raise GenerationError(f"Timeout generating image {image_id} after 120s")
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limit error - retryable with adaptive backoff
            retry_after_header = e.response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    retry_after = int(retry_after_header)
                except ValueError:
                    # Adaptive backoff: 2s → 5s → 10s
                    retry_after = 2 if retry_count == 0 else (5 if retry_count == 1 else 10)
            else:
                # Adaptive backoff: 2s → 5s → 10s
                retry_after = 2 if retry_count == 0 else (5 if retry_count == 1 else 10)
            
            logger.warning(
                f"Rate limit exceeded for {image_id}, retry after {retry_after}s",
                extra={"job_id": str(job_id), "image_type": image_type, "image_id": image_id, "retry_count": retry_count, "retry_after": retry_after}
            )
            raise RateLimitError(
                f"Rate limit exceeded for {image_id}",
                retry_after=retry_after,
                job_id=job_id
            )
        elif e.response.status_code >= 400 and e.response.status_code < 500:
            # Client errors (4xx) - non-retryable
            raise GenerationError(f"Client error generating image {image_id}: {str(e)}")
        else:
            # Server errors (5xx) - retryable
            raise RetryableError(f"Server error generating image {image_id}: {str(e)}")
        
    except httpx.RequestError as e:
        # Network error - retryable
        raise RetryableError(f"Network error generating image {image_id}: {str(e)}")
        
    except Exception as e:
        # Check if it's a validation error (non-retryable)
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ["invalid", "validation", "bad request", "400"]):
            raise GenerationError(f"Invalid prompt or settings for {image_id}: {str(e)}")
        
        # Default to retryable for unknown errors
        raise RetryableError(f"Error generating image {image_id}: {str(e)}")


async def generate_all_references(
    job_id: UUID,
    plan: ScenePlan,
    scenes: List[Scene],
    characters: List[Character],
    duration_seconds: Optional[float] = None,
    events_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> List[Dict[str, Any]]:
    """
    Generate all reference images in parallel with retry logic.
    
    Args:
        job_id: Job ID
        plan: Scene plan
        scenes: List of unique scenes
        characters: List of unique characters
        duration_seconds: Optional audio duration for budget checks
        events_callback: Optional callback to publish SSE events
        
    Returns:
        List of result dictionaries with success/failure info
    """
    from .prompts import synthesize_prompt
    from shared.errors import BudgetExceededError
    from shared.cost_tracking import cost_tracker
    # Decimal is already imported at module level, no need to import again
    
    # Get concurrency limit from environment (default: 6)
    import os
    concurrency = int(os.getenv("REFERENCE_GEN_CONCURRENCY", "6"))
    semaphore = asyncio.Semaphore(concurrency)
    
    # Track rate limit occurrences for adaptive concurrency reduction
    rate_limit_count = 0
    max_rate_limits = 3  # Reduce concurrency after 3 rate limits
    
    async def generate_one(
        sem: asyncio.Semaphore,
        scene_or_char: Any,
        img_type: Literal["scene", "character"]
    ) -> Dict[str, Any]:
        """Generate a single reference image with retry logic."""
        nonlocal rate_limit_count
        
        async with sem:
            image_id = scene_or_char.id
            description = scene_or_char.description
            
            # Check budget before generation (if duration provided)
            if duration_seconds:
                duration_minutes = duration_seconds / 60.0
                budget_limit = Decimal(str(duration_minutes * 200.0))
                estimated_cost = Decimal("0.005")  # Per image
                
                can_proceed = await cost_tracker.check_budget(
                    job_id=job_id,
                    new_cost=estimated_cost,
                    limit=budget_limit
                )
                if not can_proceed:
                    error_msg = f"Budget would be exceeded for {image_id}"
                    logger.warning(error_msg, extra={"job_id": str(job_id), "image_id": image_id})
                    if events_callback:
                        events_callback({
                            "event_type": "error",
                            "data": {
                                "image_type": img_type,
                                "image_id": image_id,
                                "reason": "Budget exceeded",
                                "budget_limit": float(budget_limit)
                            }
                        })
                    raise BudgetExceededError(error_msg, job_id=job_id)
            
            try:
                # Synthesize prompt
                prompt = synthesize_prompt(description, plan.style, img_type)
                
                # Generate image (first attempt)
                retry_count = 0
                try:
                    image_bytes, gen_time, cost, final_retry_count = await generate_image(
                        prompt=prompt,
                        image_type=img_type,
                        image_id=image_id,
                        job_id=job_id,
                        retry_count=retry_count
                    )
                    retry_count = final_retry_count
                except (RateLimitError, RetryableError) as e:
                    # Retry once with adaptive backoff
                    if isinstance(e, RateLimitError):
                        rate_limit_count += 1
                        retry_after = e.retry_after or (2 if retry_count == 0 else 5)
                        logger.warning(
                            f"Rate limit for {image_id}, waiting {retry_after}s before retry",
                            extra={"job_id": str(job_id), "image_id": image_id, "retry_after": retry_after}
                        )
                        if events_callback:
                            events_callback({
                                "event_type": "reference_generation_retry",
                                "data": {
                                    "image_type": img_type,
                                    "image_id": image_id,
                                    "retry_count": 1,
                                    "max_retries": 1,
                                    "reason": "Rate limit exceeded"
                                }
                            })
                        await asyncio.sleep(retry_after)
                    else:
                        # Other retryable errors: wait 2s
                        await asyncio.sleep(2)
                    
                    retry_count = 1
                    image_bytes, gen_time, cost, final_retry_count = await generate_image(
                        prompt=prompt,
                        image_type=img_type,
                        image_id=image_id,
                        job_id=job_id,
                        retry_count=retry_count
                    )
                    retry_count = final_retry_count
                
                return {
                    "success": True,
                    "image_type": img_type,
                    "image_id": image_id,
                    "scene_id": image_id if img_type == "scene" else None,
                    "character_id": image_id if img_type == "character" else None,
                    "image_bytes": image_bytes,
                    "generation_time": gen_time,
                    "cost": cost,
                    "prompt": prompt,
                    "retry_count": retry_count
                }
                
            except BudgetExceededError:
                # Re-raise budget errors
                raise
            except GenerationError as e:
                # Non-retryable error
                logger.error(
                    f"Failed to generate {img_type} image {image_id}: {str(e)}",
                    extra={"job_id": str(job_id), "image_type": img_type, "image_id": image_id, "error": str(e)}
                )
                return {
                    "success": False,
                    "image_type": img_type,
                    "image_id": image_id,
                    "scene_id": image_id if img_type == "scene" else None,
                    "character_id": image_id if img_type == "character" else None,
                    "error": str(e),
                    "retry_count": retry_count
                }
            except Exception as e:
                # Unexpected error
                logger.error(
                    f"Unexpected error generating {img_type} image {image_id}: {str(e)}",
                    extra={"job_id": str(job_id), "image_type": img_type, "image_id": image_id, "error": str(e)}
                )
                return {
                    "success": False,
                    "image_type": img_type,
                    "image_id": image_id,
                    "scene_id": image_id if img_type == "scene" else None,
                    "character_id": image_id if img_type == "character" else None,
                    "error": str(e),
                    "retry_count": retry_count
                }
    
    # Reduce concurrency if rate limits persist
    if rate_limit_count >= max_rate_limits:
        logger.warning(
            f"Rate limits persistent, reducing concurrency from {concurrency} to 2",
            extra={"job_id": str(job_id), "rate_limit_count": rate_limit_count}
        )
        concurrency = 2
        semaphore = asyncio.Semaphore(concurrency)
    
    # Create tasks for all images
    logger.info(
        f"Creating generation tasks for job {job_id}",
        extra={
            "job_id": str(job_id),
            "scenes_count": len(scenes),
            "characters_count": len(characters),
            "total_tasks": len(scenes) + len(characters)
        }
    )
    
    tasks = []
    for scene in scenes:
        tasks.append(generate_one(semaphore, scene, "scene"))
    for char in characters:
        tasks.append(generate_one(semaphore, char, "character"))
    
    if len(tasks) == 0:
        logger.warning(
            f"No tasks created for job {job_id} - scenes and characters lists are empty",
            extra={"job_id": str(job_id), "scenes": len(scenes), "characters": len(characters)}
        )
        return []
    
    logger.info(
        f"Starting parallel generation for {len(tasks)} images for job {job_id}",
        extra={"job_id": str(job_id), "task_count": len(tasks)}
    )
    
    # Generate all images in parallel (continue on failures)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info(
        f"Parallel generation completed for job {job_id}",
        extra={
            "job_id": str(job_id),
            "results_count": len(results),
            "successful_count": sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
        }
    )
    
    # Process results (handle exceptions from gather)
    processed_results = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Exception in parallel generation: {str(result)}")
            processed_results.append({
                "success": False,
                "error": str(result),
                "retry_count": 0
            })
        else:
            processed_results.append(result)
    
    return processed_results
