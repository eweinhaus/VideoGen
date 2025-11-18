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
# 
# RECOMMENDED MODELS FOR PHOTOREALISTIC CHARACTERS (from https://replicate.com/collections/flux):
# 
# 1. FLUX1.1 Pro Ultra (BEST FOR REALISTIC PEOPLE) ⭐ RECOMMENDED
#    - black-forest-labs/flux-1.1-pro-ultra
#    - Most powerful model, best for realistic images with "raw" mode
#    - Large images up to 4 megapixels
#    - Excellent prompt following and photorealistic output
#    - Use "raw" mode for maximum realism
#    - Set REFERENCE_MODEL_CHARACTERS=black-forest-labs/flux-1.1-pro-ultra
#
# 2. FLUX1.1 Pro (GOOD BALANCE)
#    - black-forest-labs/flux-1.1-pro
#    - Fast, high-quality generation
#    - Good for professional work and commercial projects
#    - Better balance of speed and quality
#    - Set REFERENCE_MODEL_CHARACTERS=black-forest-labs/flux-1.1-pro
#
# 3. FLUX.1 Dev (OPEN SOURCE)
#    - black-forest-labs/flux-dev
#    - Open source version
#    - Good for learning and prototypes
#    - May be less photorealistic than Pro versions
#
# 4. SDXL Base (FALLBACK)
#    - stability-ai/sdxl
#    - Known working, good for scenes
#    - Less photorealistic for people than Flux
#
# Format: owner/model (Replicate will use latest version automatically)
# Note: Flux models use different parameters than SDXL (see generate_image function)

# Default models
REFERENCE_MODEL_BASE = "stability-ai/sdxl"
REFERENCE_MODEL_LATEST_VERSION = "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"
REFERENCE_MODEL_PROD = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"
REFERENCE_MODEL_DEV = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"

# Photorealistic models (using Flux 1.1 Pro Ultra for best realism)
# Based on https://replicate.com/collections/flux
# FLUX1.1 Pro Ultra is the most powerful and best for realistic images with "raw" mode
REFERENCE_MODEL_CHARACTERS_DEFAULT = "black-forest-labs/flux-1.1-pro-ultra"  # ⭐ BEST FOR REALISTIC PEOPLE
REFERENCE_MODEL_SCENES_DEFAULT = "black-forest-labs/flux-1.1-pro-ultra"  # ⭐ ALSO BEST FOR REALISTIC SCENES

# Alternative models:
# - black-forest-labs/flux-1.1-pro (faster, good balance)
# - black-forest-labs/flux-dev (open source, less photorealistic)
# - stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc (fallback)


def get_model_version(image_type: Literal["scene", "character", "object"] = "scene") -> str:
    """
    Get model version based on environment and image type.

    For CHARACTER images: Uses FLUX1.1 Pro Ultra (best for realistic people)
    For SCENE images: Uses FLUX1.1 Pro Ultra (best for realistic scenes)
    For OBJECT images: Uses SDXL (best for product photography)

    Environment Variables:
    - REFERENCE_MODEL_CHARACTERS: Model for character images (default: FLUX1.1 Pro Ultra)
      Example: REFERENCE_MODEL_CHARACTERS=black-forest-labs/flux-1.1-pro-ultra
      Alternative: REFERENCE_MODEL_CHARACTERS=black-forest-labs/flux-1.1-pro (faster)
    - REFERENCE_MODEL_SCENES: Model for scene images (default: FLUX1.1 Pro Ultra)
      Example: REFERENCE_MODEL_SCENES=black-forest-labs/flux-1.1-pro-ultra
      Alternative: REFERENCE_MODEL_SCENES=black-forest-labs/flux-1.1-pro (faster)
    - REFERENCE_MODEL_OBJECTS: Model for object images (default: SDXL for product photography)
      Example: REFERENCE_MODEL_OBJECTS=stability-ai/sdxl
    - REFERENCE_MODEL_VERSION: Legacy - applies to all images (deprecated, use specific vars)
    - REFERENCE_MODEL_DEV: Override for development (full model string)

    Returns:
        Model version string in format: owner/model or owner/model:version_hash
    """
    import os

    # Check for image-type-specific model overrides (RECOMMENDED)
    if image_type == "character":
        character_model = os.getenv("REFERENCE_MODEL_CHARACTERS", REFERENCE_MODEL_CHARACTERS_DEFAULT)
        if character_model:
            logger.info(
                f"Using character model: {character_model}",
                extra={"model": character_model, "image_type": image_type}
            )
            return character_model
    elif image_type == "object":
        # Objects use SDXL for product photography (better for clean backgrounds and precise details)
        object_model = os.getenv("REFERENCE_MODEL_OBJECTS", REFERENCE_MODEL_PROD)
        if object_model:
            logger.info(
                f"Using object model: {object_model}",
                extra={"model": object_model, "image_type": image_type}
            )
            return object_model
    else:
        scene_model = os.getenv("REFERENCE_MODEL_SCENES", REFERENCE_MODEL_SCENES_DEFAULT)
        if scene_model:
            logger.info(
                f"Using scene model: {scene_model}",
                extra={"model": scene_model, "image_type": image_type}
            )
            return scene_model
    
    # Legacy: Check for version hash override (appends to base model)
    version_hash = os.getenv("REFERENCE_MODEL_VERSION")
    if version_hash:
        return f"{REFERENCE_MODEL_BASE}:{version_hash}"
    
    # Check for full model override (for dev)
    dev_override = os.getenv("REFERENCE_MODEL_DEV")
    if dev_override and settings.environment == "development":
        return dev_override
    
    # Default: Use appropriate model for image type
    if image_type == "character":
        return REFERENCE_MODEL_CHARACTERS_DEFAULT
    return REFERENCE_MODEL_SCENES_DEFAULT


# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    raise


async def generate_image(
    prompt: str,
    image_type: Literal["scene", "character", "object"],
    image_id: str,
    job_id: UUID,
    settings_dict: Optional[Dict[str, Any]] = None,
    retry_count: int = 0
) -> Tuple[bytes, float, Decimal, int]:
    """
    Generate a single reference image with adaptive retry logic.

    Args:
        prompt: Synthesized prompt
        image_type: "scene", "character", or "object"
        image_id: Scene, character, or object ID
        job_id: Job ID for tracking
        settings_dict: Optional generation settings (uses defaults if not provided)
        retry_count: Current retry attempt (0 = first attempt, 1 = retry)

    Returns:
        Tuple of (image_bytes, generation_time_seconds, cost, final_retry_count)

    Raises:
        RetryableError: If retryable error occurs (will be retried by caller)
        GenerationError: If generation fails permanently
    """
    model_version = get_model_version(image_type)
    logger.info(
        f"Using Replicate model: {model_version} for {image_type} image {image_id}",
        extra={"job_id": str(job_id), "model_version": model_version, "image_type": image_type, "image_id": image_id}
    )
    
    # Default generation settings
    # Enhanced negative prompt for character images to prevent cartoonish results
    # AND prevent identity changes across variations (Layer 6 Safeguard)
    # AND prevent face warping/distortion (Face Clarity Enhancement)
    if image_type == "character":
        negative_prompt = (
            # Prevent cartoonish/stylized results
            "cartoon, illustration, painting, drawing, anime, manga, 3d render, cgi, "
            "digital art, stylized, artistic, abstract, fantasy art, concept art, "
            "comic book, graphic novel, animated, animation, cartoonish, "
            "blurry, static, low quality, distorted, watermark, text overlay, "
            "oversaturated, fake, artificial, plastic, doll-like, toy-like, "
            "unrealistic proportions, exaggerated features, "
            "watercolor, oil painting, sketch, line art, vector art, "
            "stylized features, exaggerated eyes, anime eyes, manga style, "
            # Prevent identity changes (Layer 6 - Identity Preservation)
            "different person, different face, different identity, "
            "different hair color, different eye color, different skin tone, "
            "different age, different gender, different ethnicity, "
            "multiple people, two people, different character, "
            "face swap, face change, identity swap, inconsistent features, "
            # NEW: Prevent face warping/distortion (Face Clarity Enhancement)
            "warped face, distorted face, blurred face, fuzzy facial features, "
            "face morphing, inconsistent face, face changing, deformed facial features, "
            "asymmetric face, face distortion, face blur, low detail face, "
            "unclear face, hazy face, soft focus face, out of focus face"
        )
    else:
        negative_prompt = (
            "blurry, static, low quality, distorted, watermark, text overlay, "
            "cartoon, illustration, painting, drawing"
        )
    
    # Check if using Flux model (different parameters than SDXL)
    # Note: Flux models may require different parameters, but Realistic Vision SDXL uses SDXL parameters
    is_flux = "flux" in model_version.lower() and "realistic" not in model_version.lower()
    
    if is_flux:
        # Flux settings (optimized for photorealistic portraits)
        # FLUX1.1 Pro Ultra API: https://replicate.com/black-forest-labs/flux-1.1-pro-ultra/api
        # Uses aspect_ratio instead of width/height
        # Use "raw" mode for maximum realism (especially for characters)
        default_settings = {
            "prompt": prompt,
            "aspect_ratio": "1:1",  # Square format (1024x1024 equivalent)
        }
        
        # Add raw mode for characters to maximize realism
        # According to Replicate docs: "Use raw mode for realism"
        if image_type == "character":
            default_settings["raw"] = True
        
        # Note: FLUX1.1 Pro Ultra doesn't support negative_prompt, guidance_scale, 
        # num_inference_steps, or scheduler parameters - these are SDXL-specific
        # The negative prompt content is already incorporated into the main prompt
    else:
        # SDXL settings (works for both base SDXL and Realistic Vision SDXL)
        # Enhanced quality settings for character images to improve face clarity
        default_settings = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": 1024,
            "height": 1024,
            "num_outputs": 1,
            "guidance_scale": 10.0 if image_type == "character" else 7.5,  # Increased from 9.0 for better face detail
            "num_inference_steps": 60 if image_type == "character" else 30,  # Increased from 50 for sharper faces
            "scheduler": "K_EULER"
        }
    
    # Note: seed is omitted - Replicate will randomize if not provided
    # If you need deterministic results, set seed to an integer
    
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
        
        # Download image bytes (increased timeout to 60s for large images)
        async with httpx.AsyncClient(timeout=60.0) as http_client:
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
        # Check if it's a 404 error (model not found) - non-retryable
        error_str = str(e).lower()
        if "404" in error_str or "not found" in error_str or "could not be found" in error_str:
            logger.error(
                f"Model not found (404) for {image_id}: {model_version}. "
                f"This usually means the model name is incorrect or the model is not available on Replicate.",
                extra={
                    "job_id": str(job_id),
                    "image_type": image_type,
                    "image_id": image_id,
                    "model_version": model_version,
                    "error": str(e)
                }
            )
            raise GenerationError(
                f"Model not found: {model_version}. "
                f"The model may not be available on Replicate or the name is incorrect. "
                f"Error: {str(e)}"
            )
        
        # Check if it's a validation error (non-retryable)
        if any(keyword in error_str for keyword in ["invalid", "validation", "bad request", "400"]):
            raise GenerationError(f"Invalid prompt or settings for {image_id}: {str(e)}")
        
        # Default to retryable for unknown errors
        raise RetryableError(f"Error generating image {image_id}: {str(e)}")


async def generate_all_references(
    job_id: UUID,
    plan: ScenePlan,
    scenes: List[Scene],
    characters: List[Character],
    objects: List['Object'],
    duration_seconds: Optional[float] = None,
    events_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> List[Dict[str, Any]]:
    """
    Generate all reference images in parallel with retry logic.
    Generates multiple variations per scene, character, and object based on config.

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
    from shared.config import settings
    # Decimal is already imported at module level, no need to import again
    
    # Get concurrency limit from environment (default: 8 for faster generation)
    import os
    concurrency = int(os.getenv("REFERENCE_GEN_CONCURRENCY", "8"))
    semaphore = asyncio.Semaphore(concurrency)
    
    # Track rate limit occurrences for adaptive concurrency reduction
    rate_limit_count = 0
    max_rate_limits = 3  # Reduce concurrency after 3 rate limits
    
    async def generate_one(
        sem: asyncio.Semaphore,
        scene_or_char: Any,
        img_type: Literal["scene", "character", "object"],
        variation_index: int = 0
    ) -> Dict[str, Any]:
        """Generate a single reference image with retry logic."""
        nonlocal rate_limit_count

        async with sem:
            # For variations, append variation index to image_id
            base_image_id = scene_or_char.id

            # Build image_id with variation suffix (e.g., "scene_1_var0", "character_1_var1")
            # For variations > 0, always add suffix for both scenes and characters
            if variation_index > 0:
                image_id = f"{base_image_id}_var{variation_index}"
            else:
                # Variation 0: use base_image_id (for backward compatibility)
                image_id = base_image_id

            # Get description - for characters, use description field or fallback to ID
            description = getattr(scene_or_char, 'description', None) or base_image_id
            
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
                # Synthesize prompt with variation support
                if img_type == "object":
                    # Objects use specialized product photography prompts
                    from .prompts import synthesize_object_prompt
                    prompt = synthesize_object_prompt(
                        obj=scene_or_char,
                        style=plan.style,
                        variation_index=variation_index
                    )
                else:
                    # Scenes and characters use standard prompt synthesis
                    # For character images, pass the Character object for enhanced prompts
                    character_obj = scene_or_char if img_type == "character" else None
                    prompt = synthesize_prompt(
                        description,
                        plan.style,
                        img_type,
                        variation_index,
                        character=character_obj
                    )
                
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
                    "scene_id": base_image_id if img_type == "scene" else None,
                    "character_id": base_image_id if img_type == "character" else None,
                    "object_id": base_image_id if img_type == "object" else None,
                    "base_character_id": base_image_id if img_type == "character" else None,
                    "base_scene_id": base_image_id if img_type == "scene" else None,
                    "base_object_id": base_image_id if img_type == "object" else None,
                    "variation_index": variation_index,
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
                    "scene_id": base_image_id if img_type == "scene" else None,
                    "character_id": base_image_id if img_type == "character" else None,
                    "object_id": base_image_id if img_type == "object" else None,
                    "variation_index": variation_index,
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
                    "scene_id": base_image_id if img_type == "scene" else None,
                    "character_id": base_image_id if img_type == "character" else None,
                    "object_id": base_image_id if img_type == "object" else None,
                    "variation_index": variation_index,
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
    
    # Get variation counts from settings
    variations_per_scene = settings.reference_variations_per_scene
    variations_per_character = settings.reference_variations_per_character  # Re-enabled with safeguards
    variations_per_object = settings.reference_variations_per_object

    # Create tasks for all images
    # Scenes: N variations per scene (configurable, default: 2)
    # Characters: N variations per character (configurable, default: 2)
    # Objects: N variations per object (configurable, default: 2)
    # IMPORTANT: Character variations use identity-preserving prompts (same person, different angles)
    total_scene_tasks = len(scenes) * variations_per_scene
    total_character_tasks = len(characters) * variations_per_character
    total_object_tasks = len(objects) * variations_per_object
    total_tasks = total_scene_tasks + total_character_tasks + total_object_tasks

    logger.info(
        f"Creating generation tasks for job {job_id}",
        extra={
            "job_id": str(job_id),
            "scenes_count": len(scenes),
            "variations_per_scene": variations_per_scene,
            "total_scene_tasks": total_scene_tasks,
            "characters_count": len(characters),
            "variations_per_character": variations_per_character,
            "total_character_tasks": total_character_tasks,
            "objects_count": len(objects),
            "variations_per_object": variations_per_object,
            "total_object_tasks": total_object_tasks,
            "total_tasks": total_tasks
        }
    )

    tasks = []
    # Generate scene references (N variations per scene)
    for scene in scenes:
        for var_idx in range(variations_per_scene):
            tasks.append(generate_one(semaphore, scene, "scene", variation_index=var_idx))

    # Generate character references (N variations per character with identity preservation)
    # Uses identity-preserving prompts to ensure SAME person across all variations
    for char in characters:
        for var_idx in range(variations_per_character):
            tasks.append(generate_one(semaphore, char, "character", variation_index=var_idx))

    # Generate object references (N variations per object for consistency)
    # Uses detailed object features to ensure SAME object across all variations
    for obj in objects:
        for var_idx in range(variations_per_object):
            tasks.append(generate_one(semaphore, obj, "object", variation_index=var_idx))
    
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
