"""
Main entry point for Reference Generator module.

Processes ScenePlan to generate reference images for scenes and characters.
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal, Tuple
from uuid import UUID

from shared.models.scene import ScenePlan, ReferenceImages, ReferenceImage, Style
from shared.errors import ValidationError, GenerationError, BudgetExceededError
from shared.logging import get_logger
from shared.cost_tracking import cost_tracker
from shared.storage import storage
from shared.config import settings

logger = get_logger("reference_generator")

# Import will be done in functions to avoid circular imports
# from .generator import generate_all_references
# from .prompts import synthesize_prompt


async def process(
    job_id: UUID,
    plan: ScenePlan,
    duration_seconds: Optional[float] = None,
    user_uploaded_images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[ReferenceImages], List[Dict[str, Any]]]:
    """
    Generate reference images for scenes and characters.
    
    Args:
        job_id: Job ID
        plan: Scene plan from Scene Planner
        duration_seconds: Optional audio duration in seconds (for budget checks)
                         If None, budget checks may be skipped (orchestrator handles pre-flight)
        
    Returns:
        ReferenceImages object if successful (≥50% threshold AND minimum requirements met),
        None if failed (fallback to text-only mode)
        
    Raises:
        BudgetExceededError: If budget would be exceeded (if duration provided)
        GenerationError: If generation fails critically
    """
    logger.info(
        f"Starting reference generation for job {job_id}",
        extra={
            "job_id": str(job_id),
            "scenes": len(plan.scenes),
            "characters": len(plan.characters),
            "objects": len(plan.objects) if plan.objects else 0
        }
    )
    
    # Initialize event list
    events: List[Dict[str, Any]] = []
    
    # Publish stage start event
    events.append({
        "event_type": "stage_update",
        "data": {
            "stage": "reference_generator",
            "status": "started"
        }
    })
    
    # Publish initial message event so UI shows activity immediately
    events.append({
        "event_type": "message",
        "data": {
            "text": "Starting reference image generation...",
            "stage": "reference_generator"
        }
    })
    
    # Validate input
    if not plan.scenes or len(plan.scenes) == 0:
        raise ValidationError("ScenePlan must have at least 1 scene", job_id=job_id)
    if not plan.characters or len(plan.characters) == 0:
        raise ValidationError("ScenePlan must have at least 1 character", job_id=job_id)
    
    # Check for unique scene IDs
    scene_ids = {scene.id for scene in plan.scenes}
    if len(scene_ids) != len(plan.scenes):
        raise ValidationError("Scene IDs must be unique", job_id=job_id)
    
    # Check for unique character IDs
    character_ids = {char.id for char in plan.characters}
    if len(character_ids) != len(plan.characters):
        raise ValidationError("Character IDs must be unique", job_id=job_id)

    # Check for unique object IDs (objects are optional)
    if plan.objects:
        object_ids = {obj.id for obj in plan.objects}
        if len(object_ids) != len(plan.objects):
            raise ValidationError("Object IDs must be unique", job_id=job_id)

    # Validate style object
    if not plan.style:
        raise ValidationError("ScenePlan must have a style object", job_id=job_id)

    # Extract unique scenes, characters, and objects (deduplicate by ID)
    unique_scenes_list = list({scene.id: scene for scene in plan.scenes}.values())
    unique_characters_list = list({char.id: char for char in plan.characters}.values())
    unique_objects_list = list({obj.id: obj for obj in plan.objects}.values()) if plan.objects else []

    # Calculate total expected images including variations
    variations_per_scene = settings.reference_variations_per_scene
    variations_per_character = settings.reference_variations_per_character
    variations_per_object = settings.reference_variations_per_object
    
    total_images = (
        len(unique_scenes_list) * variations_per_scene +
        len(unique_characters_list) * variations_per_character +
        len(unique_objects_list) * variations_per_object
    )
    
    logger.info(
        f"Reference generator input validation for job {job_id}",
        extra={
            "job_id": str(job_id),
            "total_scenes": len(plan.scenes),
            "unique_scenes": len(unique_scenes_list),
            "total_characters": len(plan.characters),
            "unique_characters": len(unique_characters_list),
            "total_objects": len(plan.objects) if plan.objects else 0,
            "unique_objects": len(unique_objects_list),
            "total_images": total_images
        }
    )
    
    if total_images == 0:
        logger.error(
            f"No scenes or characters to generate references for job {job_id}",
            extra={"job_id": str(job_id)}
        )
        events.append({
            "event_type": "error",
            "data": {
                "stage": "reference_generator",
                "reason": "No scenes or characters in scene plan",
                "message": "Scene plan has no scenes or characters to generate references for"
            }
        })
        events.append({
            "event_type": "stage_update",
            "data": {
                "stage": "reference_generator",
                "status": "failed",
                "total_images": 0,
                "successful_images": 0,
                "failed_images": 0,
                "total_cost": 0.0,
                "total_time": 0.0,
                "failure_reason": "no_scenes_or_characters"
            }
        })
        return None, events
    
    # Import here to avoid circular imports
    from .generator import generate_all_references
    
    # Publish image generation start events
    current_image = 0
    for scene in unique_scenes_list:
        current_image += 1
        events.append({
            "event_type": "reference_generation_start",
            "data": {
                "image_type": "scene",
                "image_id": scene.id,
                "total_images": total_images,
                "current_image": current_image
            }
        })
    
    for char in unique_characters_list:
        current_image += 1
        events.append({
            "event_type": "reference_generation_start",
            "data": {
                "image_type": "character",
                "image_id": char.id,
                "total_images": total_images,
                "current_image": current_image
            }
        })

    for obj in unique_objects_list:
        current_image += 1
        events.append({
            "event_type": "reference_generation_start",
            "data": {
                "image_type": "object",
                "image_id": obj.id,
                "total_images": total_images,
                "current_image": current_image
            }
        })

    # Create events callback for SSE event publishing
    def publish_event_data(event_data: Dict[str, Any]) -> None:
        """Callback to add events to the events list."""
        events.append(event_data)
    
    # Match user-uploaded images to characters and filter out matched characters
    matched_characters = set()
    user_character_references = []
    
    if user_uploaded_images:
        logger.info(
            f"Attempting to match {len(user_uploaded_images)} user-uploaded images to characters",
            extra={
                "job_id": str(job_id),
                "user_images": [
                    {
                        "type": img.get("image_type"),
                        "title": img.get("user_title"),
                        "id": img.get("id")
                    }
                    for img in user_uploaded_images
                ],
                "characters": [
                    {
                        "id": char.id,
                        "name": getattr(char, "name", None)
                    }
                    for char in unique_characters_list
                ]
            }
        )
        matched_images = match_user_images_to_characters(user_uploaded_images, unique_characters_list)
        
        logger.info(
            f"Matched {len(matched_images)} user images to characters",
            extra={
                "job_id": str(job_id),
                "matched_count": len(matched_images),
                "matched_characters": list(matched_images.keys()),
                "unmatched_images": [
                    img.get("user_title")
                    for img in user_uploaded_images
                    if img.get("id") not in [m.get("id") for m in matched_images.values()]
                ]
            }
        )
        
        # Process matched images: copy to reference bucket and create ReferenceImage objects
        for character_id, user_image in matched_images.items():
            try:
                # Copy user image to reference bucket
                image_url = await copy_user_image_to_reference_bucket(
                    job_id, user_image, character_id
                )
                
                # Create ReferenceImage object (same format as generated)
                ref_image = ReferenceImage(
                    scene_id=None,
                    character_id=character_id,
                    object_id=None,
                    variation_index=0,  # User images use variation 0
                    image_url=image_url,
                    prompt_used="User-uploaded reference image",
                    generation_time=0.0,  # No generation time
                    cost=Decimal("0.00")  # No cost
                )
                user_character_references.append(ref_image)
                matched_characters.add(character_id)
                
                logger.info(
                    f"Matched user-uploaded image to character {character_id}",
                    extra={
                        "job_id": str(job_id),
                        "character_id": character_id,
                        "user_title": user_image["user_title"],
                        "image_type": user_image["image_type"]
                    }
                )
                
                # Publish event for user-uploaded image
                events.append({
                    "event_type": "reference_generation_complete",
                    "data": {
                        "image_type": "character",
                        "image_id": character_id,
                        "image_url": image_url,
                        "generation_time": 0.0,
                        "cost": 0.0,
                        "user_uploaded": True,
                        "total_images": total_images,
                        "completed_images": len(user_character_references)
                    }
                })
                
            except Exception as e:
                logger.error(
                    f"Failed to process user-uploaded image for character {character_id}",
                    exc_info=e,
                    extra={
                        "job_id": str(job_id),
                        "character_id": character_id,
                        "user_title": user_image.get("user_title")
                    }
                )
                # Continue processing - don't fail entire pipeline
                # The character will get a generated image instead
    
    # Filter out matched characters from generation list
    characters_to_generate = [
        char for char in unique_characters_list 
        if char.id not in matched_characters
    ]
    
    # Update total_images count: user images replace all variations for matched characters
    # Original total includes: scenes * variations + characters * variations + objects * variations
    # For matched characters: subtract their variations, add 1 user image per matched character
    matched_characters_variations = len(matched_characters) * variations_per_character
    user_images_count = len(matched_characters)  # 1 user image per matched character
    # Net change: subtract variations, add user images
    total_images = total_images - matched_characters_variations + user_images_count
    
    logger.info(
        f"User image matching complete for job {job_id}",
        extra={
            "job_id": str(job_id),
            "matched_characters": len(matched_characters),
            "characters_to_generate": len(characters_to_generate),
            "total_images_after_matching": total_images
        }
    )
    
    # Generate all images in parallel
    try:
        start_time = time.time()
        logger.info(
            f"Calling generate_all_references for job {job_id}",
            extra={
                "job_id": str(job_id),
                "scenes_count": len(unique_scenes_list),
                "characters_count": len(characters_to_generate),  # Use filtered list
                "characters_matched": len(matched_characters),
                "characters_total": len(unique_characters_list),
                "objects_count": len(unique_objects_list),
                "total_images": total_images,
                "scene_ids": [s.id for s in unique_scenes_list],
                "character_ids_to_generate": [c.id for c in characters_to_generate],  # Show which will be generated
                "character_ids_matched": list(matched_characters),  # Show which were matched
                "object_ids": [o.id for o in unique_objects_list]
            }
        )
        results = await generate_all_references(
            job_id=job_id,
            plan=plan,
            scenes=unique_scenes_list,
            characters=characters_to_generate,  # Use filtered list (exclude matched characters)
            objects=unique_objects_list,
            duration_seconds=duration_seconds,
            events_callback=publish_event_data
        )
        elapsed_time = time.time() - start_time
        # Filter out skipped variations (they're not failures, just not generated)
        non_skipped_results = [r for r in results if isinstance(r, dict) and not r.get("skipped", False)]
        successful_count = sum(1 for r in non_skipped_results if r.get("success", False))
        failed_count = len(non_skipped_results) - successful_count
        
        logger.info(
            f"generate_all_references completed for job {job_id}",
            extra={
                "job_id": str(job_id),
                "results_count": len(results),
                "successful_count": successful_count,
                "failed_count": failed_count,
                "elapsed_seconds": elapsed_time,
                "expected_images": total_images
            }
        )
        
        # Log detailed results for debugging
        if len(results) == 0:
            logger.error(
                f"generate_all_references returned empty results for job {job_id}",
                extra={
                    "job_id": str(job_id),
                    "total_images": total_images,
                    "scenes_count": len(unique_scenes_list),
                    "characters_count": len(unique_characters_list)
                }
            )
        else:
            # Log first few results for debugging
            for i, result in enumerate(results[:3]):
                logger.debug(
                    f"Result {i+1} for job {job_id}",
                    extra={
                        "job_id": str(job_id),
                        "result_index": i,
                        "success": result.get("success", False) if isinstance(result, dict) else False,
                        "image_type": result.get("image_type", "unknown") if isinstance(result, dict) else "unknown",
                        "image_id": result.get("image_id", "unknown") if isinstance(result, dict) else "unknown",
                        "error": result.get("error", None) if isinstance(result, dict) else str(result)
            }
        )
    except BudgetExceededError as e:
        logger.error(
            f"Budget exceeded during reference generation for job {job_id}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        # Publish error event
        events.append({
            "event_type": "error",
            "data": {
                "stage": "reference_generator",
                "reason": "Budget exceeded",
                "message": str(e)
            }
        })
        # Publish stage complete event (failed)
        events.append({
            "event_type": "stage_update",
            "data": {
                "stage": "reference_generator",
                "status": "failed",
                "total_images": total_images,
                "successful_images": 0,
                "failed_images": total_images,
                "total_cost": 0.0,
                "total_time": 0.0,
                "failure_reason": "budget_exceeded"
            }
        })
        return None, events
    except Exception as e:
        # Catch any other exceptions during generation
        logger.error(
            f"Unexpected error during reference generation for job {job_id}",
            exc_info=e,
            extra={"job_id": str(job_id), "error": str(e), "error_type": type(e).__name__}
        )
        # Publish error event
        events.append({
            "event_type": "error",
            "data": {
                "stage": "reference_generator",
                "reason": f"Unexpected error: {str(e)}",
                "message": str(e)
            }
        })
        # Publish stage complete event (failed)
        events.append({
            "event_type": "stage_update",
            "data": {
                "stage": "reference_generator",
                "status": "failed",
                "total_images": total_images,
                "successful_images": 0,
                "failed_images": total_images,
                "total_cost": 0.0,
                "total_time": 0.0,
                "failure_reason": "unexpected_error"
            }
        })
        return None, events
    
    # Process results and upload images
    logger.info(
        f"Processing {len(results)} results for job {job_id}",
        extra={"job_id": str(job_id), "results_count": len(results)}
    )
    
    if not results or len(results) == 0:
        logger.warning(
            f"No results returned from generate_all_references for job {job_id}",
            extra={"job_id": str(job_id), "total_images": total_images}
        )
        # Publish stage complete event (failed)
        events.append({
            "event_type": "stage_update",
            "data": {
                "stage": "reference_generator",
                "status": "failed",
                "total_images": total_images,
                "successful_images": 0,
                "failed_images": total_images,
                "total_cost": 0.0,
                "total_time": 0.0,
                "failure_reason": "no_generation_results"
            }
        })
        return None, events
    
    scene_references: List[ReferenceImage] = []
    character_references: List[ReferenceImage] = []
    object_references: List[ReferenceImage] = []
    total_cost = Decimal("0.00")
    total_generation_time = 0.0
    successful_images = 0
    scene_references_count = 0
    character_references_count = 0
    object_references_count = 0
    completed_images = 0
    
    for result in results:
        # Skip skipped variations (they're not failures, just not generated for consistency)
        if result.get("skipped", False):
            continue
        
        if not result.get("success", False):
            # Handle failed results
            events.append({
                "event_type": "reference_generation_failed",
                "data": {
                    "image_type": result.get("image_type", "unknown"),
                    "image_id": result.get("image_id", "unknown"),
                    "retry_count": result.get("retry_count", 0),
                    "reason": result.get("error", "Unknown error"),
                    "will_continue": True
                }
            })
            continue
        
        if result["success"]:
            # Upload image
            try:
                image_type = result["image_type"]
                image_id = result["image_id"]
                path = f"{job_id}/{image_type}_{image_id}.png"
                
                # Upload with overwrite=True to ensure we always generate new images
                # Users expect fresh images unless we're explicitly caching based on input hash
                await storage.upload_file(
                    bucket="reference-images",
                    path=path,
                    file_data=result["image_bytes"],
                    content_type="image/png",
                    overwrite=True
                )
                
                # Generate signed URL for the newly uploaded file
                signed_url = await storage.get_signed_url(
                    bucket="reference-images",
                    path=path,
                    expires_in=1209600  # 14 days
                )
                
                # Track cost (non-fatal - continue even if tracking fails)
                try:
                    await cost_tracker.track_cost(
                        job_id=job_id,
                        stage_name="reference_generator",
                        api_name="sdxl",
                        cost=result["cost"]
                    )
                except Exception as cost_error:
                    # Cost tracking failure shouldn't prevent image generation from succeeding
                    # This can happen in tests where job doesn't exist in database
                    logger.warning(
                        f"Failed to track cost for image {image_id}, continuing anyway",
                        extra={"job_id": str(job_id), "image_id": image_id, "error": str(cost_error)}
                    )
                
                # Create ReferenceImage object
                ref_image = ReferenceImage(
                    scene_id=result["scene_id"] if image_type == "scene" else None,
                    character_id=result["character_id"] if image_type == "character" else None,
                    object_id=result["object_id"] if image_type == "object" else None,
                    variation_index=result.get("variation_index", 0),
                    image_url=signed_url,
                    prompt_used=result["prompt"],
                    generation_time=result["generation_time"],
                    cost=result["cost"]
                )
                
                if image_type == "scene":
                    scene_references.append(ref_image)
                    scene_references_count += 1
                elif image_type == "character":
                    character_references.append(ref_image)
                    character_references_count += 1
                elif image_type == "object":
                    object_references.append(ref_image)
                    object_references_count += 1
                
                total_cost += result["cost"]
                total_generation_time += result["generation_time"]
                successful_images += 1
                completed_images += 1
                
                # Publish image generation complete event
                events.append({
                    "event_type": "reference_generation_complete",
                    "data": {
                        "image_type": result["image_type"],
                        "image_id": result["image_id"],
                        "image_url": signed_url,
                        "generation_time": result["generation_time"],
                        "cost": float(result["cost"]),
                        "retry_count": result.get("retry_count", 0),
                        "total_images": total_images,
                        "completed_images": completed_images
                    }
                })
                
            except Exception as e:
                # Storage upload failure (storage client already retried 3 times)
                logger.error(
                    f"Failed to upload reference image {result.get('image_id', 'unknown')} after retries: {str(e)}",
                    extra={"job_id": str(job_id), "image_id": result.get("image_id", "unknown"), "error": str(e)}
                )
                # Publish image generation failed event
                events.append({
                    "event_type": "reference_generation_failed",
                    "data": {
                        "image_type": result.get("image_type", "unknown"),
                        "image_id": result.get("image_id", "unknown"),
                        "retry_count": result.get("retry_count", 0),
                        "reason": f"Storage upload failed: {str(e)}",
                        "will_continue": True
                    }
                })
                # Continue processing other images (don't abort entire generation)
    
    # Merge user-uploaded character references with generated ones BEFORE threshold check
    all_character_references = user_character_references + character_references
    character_references_count += len(user_character_references)
    successful_images += len(user_character_references)  # User images count as successful
    
    # Calculate partial success threshold (AFTER merging user-uploaded images)
    success_percentage = successful_images / total_images if total_images > 0 else 0.0
    
    # Check threshold (ALL required conditions must pass)
    # If objects exist in plan, they must have at least 1 reference
    threshold_met = (
        success_percentage >= 0.5 and  # ≥50% of total images
        scene_references_count >= 1 and  # At least 1 scene reference
        character_references_count >= 1 and  # At least 1 character reference (includes user-uploaded)
        (object_references_count >= 1 if len(unique_objects_list) > 0 else True)  # Objects required if they exist
    )
    
    if not threshold_met:
        logger.warning(
            f"Partial success threshold not met for job {job_id}",
            extra={
                "job_id": str(job_id),
                "success_percentage": success_percentage,
                "scene_references": scene_references_count,
                "character_references": character_references_count,
                "user_uploaded_character_refs": len(user_character_references),
                "generated_character_refs": len(character_references),
                "object_references": object_references_count,
                "total_images": total_images,
                "successful_images": successful_images,
                "objects_required": len(unique_objects_list) > 0
            }
        )
        # Publish stage complete event (failed)
        events.append({
            "event_type": "stage_update",
            "data": {
                "stage": "reference_generator",
                "status": "failed",
                "total_images": total_images,
                "successful_images": successful_images,
                "failed_images": total_images - successful_images,
                "total_cost": float(total_cost),
                "total_time": total_generation_time,
                "failure_reason": "threshold_not_met"
            }
        })
        return None, events
    
    # Determine status
    status: Literal["success", "partial", "failed"] = "success" if successful_images == total_images else "partial"
    
    # Get model version from generator
    from .generator import get_model_version
    model_version = get_model_version()
    
    # Create ReferenceImages object
    reference_images = ReferenceImages(
        job_id=job_id,
        scene_references=scene_references,
        character_references=all_character_references,  # Use merged list
        object_references=object_references,
        total_references=len(scene_references) + len(all_character_references) + len(object_references),
        total_generation_time=total_generation_time,
        total_cost=total_cost,
        status=status,
        metadata={
            "model_version": model_version,
            "dimensions": "1024x1024",
            "format": "PNG",
            "environment": settings.environment,
            "user_uploaded_count": len(user_character_references)
        }
    )
    
    logger.info(
        f"Reference generation completed for job {job_id}",
        extra={
            "job_id": str(job_id),
            "status": status,
            "total_references": reference_images.total_references,
            "total_cost": float(total_cost),
            "total_time": total_generation_time
        }
    )
    
    # Publish stage complete event
    events.append({
        "event_type": "stage_update",
        "data": {
            "stage": "reference_generator",
            "status": "completed",
            "total_images": total_images,
            "successful_images": successful_images,
            "failed_images": total_images - successful_images,
            "total_cost": float(total_cost),
            "total_time": total_generation_time
        }
    })
    
    return reference_images, events


def match_user_images_to_characters(
    user_images: List[Dict[str, Any]],
    characters: List[Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Match user-uploaded images to characters from scene plan.
    
    Matching strategy (in priority order):
    1. Exact match (case-insensitive): user_title == character.id
    2. Name-based match: user_title == character.name (case-insensitive)
    3. Role-based match: user_title == character.role (case-insensitive) - for "main character", "protagonist", etc.
    
    Args:
        user_images: List of user-uploaded image data
        characters: List of Character objects from scene plan
        
    Returns:
        Dict mapping character_id -> user_image_data
    """
    matched = {}
    
    for user_img in user_images:
        if user_img.get("image_type") != "character":
            continue  # Only match character images for now
        
        user_title_lower = user_img["user_title"].lower().strip()
        if not user_title_lower:
            continue
        
        # Check if this user image was already matched
        already_matched = False
        for matched_char_id, matched_img in matched.items():
            if matched_img.get("id") == user_img.get("id"):
                already_matched = True
                break
        
        if already_matched:
            continue
        
        # Try exact match to character ID
        matched_char_id = None
        for char in characters:
            if char.id.lower() == user_title_lower:
                matched[char.id] = user_img
                matched_char_id = char.id
                logger.info(
                    f"Matched user image '{user_img['user_title']}' to character ID '{char.id}' (exact ID match)",
                    extra={
                        "user_title": user_img["user_title"],
                        "character_id": char.id,
                        "match_type": "exact_id"
                    }
                )
                break
        
        # Try name-based match if no exact match found
        if matched_char_id is None:
            for char in characters:
                # Skip if this character is already matched
                if char.id in matched:
                    continue
                    
                if hasattr(char, "name") and char.name:
                    if char.name.lower() == user_title_lower:
                        matched[char.id] = user_img
                        matched_char_id = char.id
                        logger.info(
                            f"Matched user image '{user_img['user_title']}' to character name '{char.name}' (name-based match)",
                            extra={
                                "user_title": user_img["user_title"],
                                "character_id": char.id,
                                "character_name": char.name,
                                "match_type": "name"
                            }
                        )
                        break
        
        # Try role-based match if no exact or name match found
        if matched_char_id is None:
            for char in characters:
                # Skip if this character is already matched
                if char.id in matched:
                    continue
                
                if hasattr(char, "role") and char.role:
                    if char.role.lower() == user_title_lower:
                        matched[char.id] = user_img
                        matched_char_id = char.id
                        logger.info(
                            f"Matched user image '{user_img['user_title']}' to character role '{char.role}' (role-based match)",
                            extra={
                                "user_title": user_img["user_title"],
                                "character_id": char.id,
                                "character_role": char.role,
                                "match_type": "role"
                            }
                        )
                        break
        
        # Log if no match found
        if matched_char_id is None:
            logger.warning(
                f"Could not match user image '{user_img['user_title']}' to any character",
                extra={
                    "user_title": user_img["user_title"],
                    "available_character_ids": [char.id for char in characters],
                    "available_character_names": [getattr(char, "name", None) for char in characters if hasattr(char, "name")],
                    "available_character_roles": [getattr(char, "role", None) for char in characters if hasattr(char, "role")]
                }
            )
    
    return matched


async def copy_user_image_to_reference_bucket(
    job_id: UUID,
    user_image: Dict[str, Any],
    character_id: str
) -> str:
    """
    Copy user-uploaded image to reference-images bucket at standard path.
    
    Format: {job_id}/character_{character_id}.png
    
    Args:
        job_id: Job ID
        user_image: User-uploaded image data
        character_id: Character ID to match
    
    Returns:
        Signed URL for the copied image
    """
    from shared.image_processing import process_user_reference_image
    from shared.database import DatabaseClient
    
    db_client = DatabaseClient()
    
    try:
        # Download original image from user_uploaded path
        original_path = user_image["storage_path"]
        file_data = await storage.download_file(
            bucket="reference-images",
            path=original_path
        )
        
        # Process image (resize to 1024x1024, convert to PNG)
        processed_image_bytes = await process_user_reference_image(
            file_data,
            target_size=(1024, 1024),
            target_format="PNG"
        )
        
        # Upload to reference-images bucket at standard path
        final_path = f"{job_id}/character_{character_id}.png"
        await storage.upload_file(
            bucket="reference-images",
            path=final_path,
            file_data=processed_image_bytes,
            content_type="image/png",
            overwrite=True
        )
        
        # Generate signed URL
        signed_url = await storage.get_signed_url(
            bucket="reference-images",
            path=final_path,
            expires_in=1209600  # 14 days
        )
        
        # Update database record with final_storage_path and matched character info
        try:
            await db_client.table("user_reference_images").update({
                "final_storage_path": final_path,
                "matched_character_id": character_id,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_image["id"]).execute()
        except Exception as db_error:
            logger.warning(
                f"Failed to update user_reference_images record: {str(db_error)}",
                extra={"job_id": str(job_id), "image_id": user_image["id"]}
            )
            # Continue - database update failure shouldn't prevent image copy
        
        logger.info(
            f"Copied user-uploaded image to reference bucket",
            extra={
                "job_id": str(job_id),
                "character_id": character_id,
                "original_path": original_path,
                "final_path": final_path
            }
        )
        
        return signed_url
        
    except Exception as e:
        logger.error(
            f"Failed to copy user image to reference bucket",
            exc_info=e,
            extra={
                "job_id": str(job_id),
                "character_id": character_id,
                "user_image_id": user_image.get("id")
            }
        )
        raise
