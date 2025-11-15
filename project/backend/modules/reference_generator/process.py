"""
Main entry point for Reference Generator module.

Processes ScenePlan to generate reference images for scenes and characters.
"""

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
    duration_seconds: Optional[float] = None
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
        extra={"job_id": str(job_id), "scenes": len(plan.scenes), "characters": len(plan.characters)}
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
    
    # Validate style object
    if not plan.style:
        raise ValidationError("ScenePlan must have a style object", job_id=job_id)
    
    # Extract unique scenes and characters (deduplicate by ID)
    unique_scenes_list = list({scene.id: scene for scene in plan.scenes}.values())
    unique_characters_list = list({char.id: char for char in plan.characters}.values())
    
    total_images = len(unique_scenes_list) + len(unique_characters_list)
    
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
    
    # Create events callback for SSE event publishing
    def publish_event_data(event_data: Dict[str, Any]) -> None:
        """Callback to add events to the events list."""
        events.append(event_data)
    
    # Generate all images in parallel
    try:
        results = await generate_all_references(
            job_id=job_id,
            plan=plan,
            scenes=unique_scenes_list,
            characters=unique_characters_list,
            duration_seconds=duration_seconds,
            events_callback=publish_event_data
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
                "status": "completed",
                "total_images": total_images,
                "successful_images": 0,
                "failed_images": total_images,
                "total_cost": 0.0,
                "total_time": 0.0
            }
        })
        return None, events
    
    # Process results and upload images
    scene_references: List[ReferenceImage] = []
    character_references: List[ReferenceImage] = []
    total_cost = Decimal("0.00")
    total_generation_time = 0.0
    successful_images = 0
    scene_references_count = 0
    character_references_count = 0
    completed_images = 0
    
    for result in results:
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
                
                await storage.upload_file(
                    bucket="reference-images",
                    path=path,
                    file_data=result["image_bytes"],
                    content_type="image/png"
                )
                
                # Generate signed URL
                signed_url = await storage.get_signed_url(
                    bucket="reference-images",
                    path=path,
                    expires_in=1209600  # 14 days
                )
                
                # Track cost
                await cost_tracker.track_cost(
                    job_id=job_id,
                    stage_name="reference_generator",
                    api_name="sdxl",
                    cost=result["cost"]
                )
                
                # Create ReferenceImage object
                ref_image = ReferenceImage(
                    scene_id=result["scene_id"] if image_type == "scene" else None,
                    character_id=result["character_id"] if image_type == "character" else None,
                    image_url=signed_url,
                    prompt_used=result["prompt"],
                    generation_time=result["generation_time"],
                    cost=result["cost"]
                )
                
                if image_type == "scene":
                    scene_references.append(ref_image)
                    scene_references_count += 1
                else:
                    character_references.append(ref_image)
                    character_references_count += 1
                
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
    
    # Calculate partial success threshold
    success_percentage = successful_images / total_images if total_images > 0 else 0.0
    
    # Check threshold (ALL three conditions must pass)
    threshold_met = (
        success_percentage >= 0.5 and  # ≥50% of total images
        scene_references_count >= 1 and  # At least 1 scene reference
        character_references_count >= 1  # At least 1 character reference
    )
    
    if not threshold_met:
        logger.warning(
            f"Partial success threshold not met for job {job_id}",
            extra={
                "job_id": str(job_id),
                "success_percentage": success_percentage,
                "scene_references": scene_references_count,
                "character_references": character_references_count,
                "total_images": total_images,
                "successful_images": successful_images
            }
        )
        # Publish stage complete event (failed)
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
        character_references=character_references,
        total_references=len(scene_references) + len(character_references),
        total_generation_time=total_generation_time,
        total_cost=total_cost,
        status=status,
        metadata={
            "model_version": model_version,
            "dimensions": "1024x1024",
            "format": "PNG",
            "environment": settings.environment
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
