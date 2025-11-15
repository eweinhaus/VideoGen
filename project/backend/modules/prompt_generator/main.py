"""
Prompt Generator entry point.

Provides orchestrator-facing async API for Module 6.
"""

from typing import Optional
from uuid import UUID

from shared.errors import GenerationError, ValidationError
from shared.logging import get_logger, set_job_id
from shared.models.scene import ReferenceImages, ScenePlan
from shared.models.video import ClipPrompts

from .process import process

logger = get_logger("prompt_generator")


async def process_prompt_generation(
    job_id: UUID,
    plan: ScenePlan,
    references: Optional[ReferenceImages] = None,
) -> ClipPrompts:
    """
    Generate ClipPrompts from a scene plan and optional reference images.

    Args:
        job_id: Pipeline job identifier
        plan: ScenePlan returned by Module 4
        references: Optional ReferenceImages bundle from Module 5

    Returns:
        ClipPrompts ready for Module 7 consumption
    """
    set_job_id(job_id)
    try:
        if not isinstance(job_id, UUID):
            raise ValidationError("job_id must be a UUID", job_id=job_id)
        if not isinstance(plan, ScenePlan):
            raise ValidationError("plan must be a ScenePlan model", job_id=job_id)
        if references is not None and not isinstance(references, ReferenceImages):
            raise ValidationError("references must be ReferenceImages or None", job_id=job_id)

        logger.info(
            "Starting prompt generation",
            extra={"job_id": str(job_id), "clip_count": len(plan.clip_scripts)},
        )
        clip_prompts = await process(job_id, plan, references)
        logger.info(
            "Prompt generation completed",
            extra={
                "job_id": str(job_id),
                "clip_count": clip_prompts.total_clips,
                "generation_time": clip_prompts.generation_time,
            },
        )
        return clip_prompts
    except (ValidationError, GenerationError):
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Unexpected prompt generation error",
            extra={"job_id": str(job_id)},
            exc_info=True,
        )
        raise GenerationError(str(exc), job_id=job_id) from exc
    finally:
        set_job_id(None)

