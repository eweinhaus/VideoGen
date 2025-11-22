"""
FastAPI router integration and job processing entry point.

Main entry point called by API Gateway orchestrator.
"""

from uuid import UUID
from shared.models.audio import AudioAnalysis
from shared.models.scene import ScenePlan
from shared.errors import ValidationError, GenerationError
from shared.logging import get_logger, set_job_id
from shared.validation import validate_prompt

from .planner import plan_scenes

logger = get_logger("scene_planner")


async def process_scene_planning(
    job_id: UUID,
    user_prompt: str,
    audio_data: AudioAnalysis
) -> ScenePlan:
    """
    Main entry point for scene planning processing.
    
    Called by API Gateway orchestrator to generate scene plan from
    user prompt and audio analysis data.
    
    Args:
        job_id: Job ID
        user_prompt: User's creative prompt (50-3000 characters)
        audio_data: AudioAnalysis from Module 3 (Audio Parser)
        
    Returns:
        ScenePlan Pydantic model
        
    Raises:
        ValidationError: If inputs are invalid
        GenerationError: If scene planning fails
    """
    # Set job_id in context for logging
    set_job_id(job_id)
    
    try:
        # Validate inputs
        if not isinstance(job_id, UUID):
            raise ValidationError(f"Invalid job_id: {job_id}", job_id=job_id)
        
        # Validate prompt
        validate_prompt(user_prompt, min_length=50, max_length=3000)
        
        if not audio_data:
            raise ValidationError("audio_data is required", job_id=job_id)
        
        if not isinstance(audio_data, AudioAnalysis):
            raise ValidationError(
                f"audio_data must be AudioAnalysis model, got {type(audio_data)}",
                job_id=job_id
            )
        
        if not audio_data.clip_boundaries:
            raise ValidationError(
                "audio_data must have clip_boundaries",
                job_id=job_id
            )
        
        logger.info(
            f"Processing scene planning",
            extra={
                "job_id": str(job_id),
                "user_prompt_length": len(user_prompt),
                "clip_count": len(audio_data.clip_boundaries),
                "bpm": audio_data.bpm,
                "mood": audio_data.mood.primary
            }
        )
        
        # Call planner
        scene_plan = await plan_scenes(
            job_id=job_id,
            user_prompt=user_prompt,
            audio_data=audio_data
        )
        
        logger.info(
            f"Scene planning complete",
            extra={
                "job_id": str(job_id),
                "characters": len(scene_plan.characters),
                "scenes": len(scene_plan.scenes),
                "clips": len(scene_plan.clip_scripts)
            }
        )
        
        return scene_plan
        
    except ValidationError:
        raise
    except GenerationError:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in scene planning: {str(e)}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        raise GenerationError(
            f"Unexpected error in scene planning: {str(e)}",
            job_id=job_id
        ) from e
    finally:
        # Clear job_id from context
        set_job_id(None)

