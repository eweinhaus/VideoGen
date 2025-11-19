"""
Regeneration process orchestration.

Main orchestration function for regenerating a single clip based on user instruction.
Handles template matching, LLM modification, and video generation.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from uuid import UUID
from decimal import Decimal

from shared.models.video import Clip, ClipPrompt, Clips, VideoOutput
from shared.logging import get_logger
from shared.config import settings
from shared.database import DatabaseClient
from shared.errors import GenerationError, ValidationError, CompositionError, RetryableError

from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clip_prompts_from_job_stages,
    load_scene_plan_from_job_stages,
    load_transitions_from_job_stages,
    load_beat_timestamps_from_job_stages,
    get_audio_url,
    get_aspect_ratio
)
from modules.clip_regenerator.template_matcher import match_template, apply_template
from modules.clip_regenerator.llm_modifier import modify_prompt_with_llm, estimate_llm_cost
from modules.clip_regenerator.context_builder import build_llm_context
from modules.clip_regenerator.status_manager import update_job_status
from modules.clip_regenerator.cost_tracker import track_regeneration_cost
from modules.video_generator.generator import generate_video_clip
from modules.video_generator.config import get_generation_settings
from modules.video_generator.cost_estimator import estimate_clip_cost
from modules.composer.process import process as composer_process
from modules.analytics.tracking import track_regeneration_async

logger = get_logger("clip_regenerator.process")


@dataclass
class RegenerationResult:
    """Result of clip regeneration."""
    
    clip: Clip
    modified_prompt: str
    template_used: Optional[str]
    cost: Decimal
    video_output: Optional[VideoOutput] = None  # Added for recomposition result


async def _get_job_config(job_id: UUID) -> Dict[str, str]:
    """
    Get job configuration (video_model, aspect_ratio) from database.
    
    These are stored in job_stages metadata or can be retrieved from Redis job data.
    For now, we'll try to get from job_stages metadata, or use defaults.
    
    Args:
        job_id: Job ID
        
    Returns:
        Dictionary with video_model and aspect_ratio
    """
    db = DatabaseClient()
    
    # Try to get from job_stages metadata (video_generator stage)
    try:
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "video_generator").execute()
        
        if result.data and len(result.data) > 0:
            metadata = result.data[0].get("metadata")
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
            
            # Check if video_model and aspect_ratio are in metadata
            video_model = metadata.get("video_model") or metadata.get("model")
            aspect_ratio = metadata.get("aspect_ratio")
            
            if video_model and aspect_ratio:
                return {
                    "video_model": video_model,
                    "aspect_ratio": aspect_ratio
                }
    except Exception as e:
        logger.warning(
            f"Failed to get job config from job_stages: {e}",
            extra={"job_id": str(job_id)}
        )
    
    # Fallback to defaults
    return {
        "video_model": settings.video_model if hasattr(settings, 'video_model') else "kling_v21",
        "aspect_ratio": "16:9"
    }


async def regenerate_clip(
    job_id: UUID,
    clip_index: int,
    user_instruction: str,
    user_id: Optional[UUID] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    event_publisher: Optional[callable] = None
) -> RegenerationResult:
    """
    Regenerate a single clip based on user instruction.
    
    Steps:
    1. Load original clip data from job_stages.metadata
    2. Check for template match
    3. If template: Apply transformation
    4. If no template: Call LLM to modify prompt
    5. Generate new clip (reuse Video Generator)
    6. Return new clip URL
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to regenerate (0-based)
        user_instruction: User's modification instruction
        conversation_history: Optional conversation history
        event_publisher: Optional async callback(event_type, data) to publish events
        
    Returns:
        RegenerationResult with new clip, modified prompt, template used, and cost
        
    Raises:
        ValidationError: If clip_index is invalid or data loading fails
        GenerationError: If video generation fails
    """
    if conversation_history is None:
        conversation_history = []
    
    environment = settings.environment
    
    logger.info(
        f"Starting clip regeneration",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "instruction": user_instruction
        }
    )
    
    # Publish regeneration_started event
    if event_publisher:
        await event_publisher("regeneration_started", {
            "sequence": 1,
            "clip_index": clip_index,
            "instruction": user_instruction
        })
    
    # Step 1: Load original clip data from job_stages.metadata
    logger.debug(
        f"Loading clips from job_stages",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    clips = await load_clips_from_job_stages(job_id)
    if not clips:
        logger.error(
            f"Failed to load clips from job_stages",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "stage": "data_loading"
            }
        )
        raise ValidationError(
            f"Failed to load clips for job {job_id}. "
            "The job may not have completed video generation yet, or the clips data in the database is incomplete or corrupted. "
            "Please ensure the job has completed successfully before attempting to regenerate clips."
        )
    
    logger.debug(
        f"Clips loaded successfully",
        extra={
            "job_id": str(job_id),
            "total_clips": len(clips.clips),
            "successful_clips": clips.successful_clips,
            "failed_clips": clips.failed_clips
        }
    )
    
    logger.debug(
        f"Loading clip prompts from job_stages",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
    if not clip_prompts:
        logger.error(
            f"Failed to load clip prompts from job_stages",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": len(clips.clips),
                "stage": "data_loading"
            }
        )
        raise ValidationError(
            f"Failed to load clip prompts for job {job_id}. "
            "The prompt data may be missing or incomplete in the database. "
            "This is required to regenerate the clip with your modifications."
        )
    
    logger.debug(
        f"Clip prompts loaded successfully",
        extra={
            "job_id": str(job_id),
            "total_prompts": len(clip_prompts.clip_prompts),
            "total_clips": clips.total_clips
        }
    )
    
    logger.debug(
        f"Loading scene plan from job_stages",
        extra={"job_id": str(job_id)}
    )
    scene_plan = await load_scene_plan_from_job_stages(job_id)
    if not scene_plan:
        logger.warning(
            f"No scene plan found for job {job_id}, proceeding without context",
            extra={"job_id": str(job_id)}
        )
    else:
        logger.debug(
            f"Scene plan loaded successfully",
            extra={
                "job_id": str(job_id),
                "characters_count": len(scene_plan.characters) if scene_plan.characters else 0,
                "scenes_count": len(scene_plan.scenes) if scene_plan.scenes else 0
            }
        )
    
    # Validate clip_index and find the clip
    # Note: We find by clip_index, not position, because incomplete clips may have been filtered out
    logger.debug(
        f"Validating clip_index",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "total_clips": len(clips.clips),
            "available_clip_indices": [c.clip_index for c in clips.clips]
        }
    )
    
    # Find clip by clip_index (not by position, since incomplete clips may have been filtered)
    original_clip = None
    for clip in clips.clips:
        if clip.clip_index == clip_index:
            original_clip = clip
            break
    
    if original_clip is None:
        available_indices = [c.clip_index for c in clips.clips]
        logger.error(
            f"Clip not found: clip_index does not exist in loaded clips",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": len(clips.clips),
                "available_clip_indices": available_indices
            }
        )
        raise ValidationError(
            f"Clip with index {clip_index} not found. "
            f"Available clip indices: {available_indices if available_indices else 'none'}. "
            f"The requested clip may be incomplete or not yet generated. "
            f"Only complete clips can be regenerated."
        )
    logger.debug(
        f"Original clip retrieved",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "clip_status": original_clip.status,
            "clip_duration": original_clip.target_duration,
            "clip_url": original_clip.video_url
        }
    )
    
    # Validate clip_index against clip_prompts
    logger.debug(
        f"Validating clip_index against clip_prompts",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "total_prompts": len(clip_prompts.clip_prompts),
            "prompts_range": f"0-{len(clip_prompts.clip_prompts) - 1}"
        }
    )
    if clip_index >= len(clip_prompts.clip_prompts):
        logger.error(
            f"Clip prompt not found: index out of bounds",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_prompts": len(clip_prompts.clip_prompts),
                "total_clips": len(clips.clips),
                "data_mismatch": True
            }
        )
        raise ValidationError(
            f"Clip prompt not found for index {clip_index}. Total prompts: {len(clip_prompts.clip_prompts)}"
        )
    
    original_prompt = clip_prompts.clip_prompts[clip_index]
    logger.debug(
        f"Original prompt retrieved",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "prompt_length": len(original_prompt.prompt),
            "has_negative_prompt": bool(original_prompt.negative_prompt),
            "has_scene_reference": bool(original_prompt.scene_reference_url),
            "character_references_count": len(original_prompt.character_reference_urls) if original_prompt.character_reference_urls else 0
        }
    )
    
    # Get job configuration (video_model, aspect_ratio)
    logger.debug(
        f"Loading job configuration",
        extra={"job_id": str(job_id)}
    )
    job_config = await _get_job_config(job_id)
    video_model = job_config["video_model"]
    aspect_ratio = job_config["aspect_ratio"]
    logger.debug(
        f"Job configuration loaded",
        extra={
            "job_id": str(job_id),
            "video_model": video_model,
            "aspect_ratio": aspect_ratio,
            "environment": environment
        }
    )
    
    # Step 2: Check for template match
    logger.debug(
        f"Checking for template match",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "instruction": user_instruction[:100]  # First 100 chars for logging
        }
    )
    template_match = match_template(user_instruction)
    
    if template_match:
        # Step 3: Apply template transformation
        modified_prompt = apply_template(original_prompt.prompt, template_match)
        cost_estimate = estimate_clip_cost(original_clip.target_duration, environment)
        
        logger.info(
            f"Template matched: {template_match.template_id}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "template_id": template_match.template_id
            }
        )
        
        # Publish template_matched event
        if event_publisher:
            await event_publisher("template_matched", {
                "sequence": 2,
                "template_id": template_match.template_id,
                "transformation": template_match.transformation
            })
    else:
        # Step 4: LLM modification
        if not scene_plan:
            # Create minimal context if scene plan not available
            context = {
                "original_prompt": original_prompt.prompt,
                "style_info": "Not specified",
                "character_names": [],
                "scene_locations": [],
                "mood": "Not specified",
                "user_instruction": user_instruction,
                "recent_conversation": ""
            }
        else:
            context = build_llm_context(
                original_prompt.prompt,
                scene_plan,
                user_instruction,
                conversation_history
            )
        
        modified_prompt = await modify_prompt_with_llm(
            original_prompt.prompt,
            user_instruction,
            context,
            conversation_history,
            job_id=job_id
        )
        cost_estimate = estimate_llm_cost() + estimate_clip_cost(original_clip.target_duration, environment)
        
        logger.info(
            f"Prompt modified via LLM",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "original_length": len(original_prompt.prompt),
                "modified_length": len(modified_prompt)
            }
        )
    
    # Publish prompt_modified event
    if event_publisher:
        await event_publisher("prompt_modified", {
            "sequence": 3,
            "modified_prompt": modified_prompt,
            "template_used": template_match.template_id if template_match else None
        })
    
    # Step 5: Generate new clip
    # Create new ClipPrompt with modified prompt
    new_clip_prompt = ClipPrompt(
        clip_index=clip_index,
        prompt=modified_prompt,
        negative_prompt=original_prompt.negative_prompt,
        duration=original_prompt.duration,
        scene_reference_url=original_prompt.scene_reference_url,
        character_reference_urls=original_prompt.character_reference_urls,
        metadata=original_prompt.metadata
    )
    
    # Get generation settings
    settings_dict = get_generation_settings(environment)
    
    # Publish video_generating event
    if event_publisher:
        await event_publisher("video_generating", {
            "sequence": 4,
            "progress": 10,  # Start of video generation (10-60% range)
            "clip_index": clip_index
        })
    
    # Generate single clip
    logger.info(
        f"Starting video clip generation",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "video_model": video_model,
            "aspect_ratio": aspect_ratio,
            "target_duration": new_clip_prompt.duration,
            "has_scene_reference": bool(new_clip_prompt.scene_reference_url),
            "has_character_references": bool(new_clip_prompt.character_reference_urls),
            "modified_prompt_length": len(modified_prompt),
            "template_used": template_match.template_id if template_match else None
        }
    )
    try:
        new_clip = await generate_video_clip(
            clip_prompt=new_clip_prompt,
            image_url=new_clip_prompt.scene_reference_url,
            settings=settings_dict,
            job_id=job_id,
            environment=environment,
            video_model=video_model,
            aspect_ratio=aspect_ratio
        )
        
        logger.info(
            f"Clip regenerated successfully",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "new_clip_url": new_clip.video_url,
                "new_clip_status": new_clip.status,
                "new_clip_duration": new_clip.actual_duration,
                "cost": str(cost_estimate),
                "template_used": template_match.template_id if template_match else None
            }
        )
        
        # Track regeneration success (for analytics) - non-blocking
        if user_id:
            track_regeneration_async(
                job_id=job_id,
                user_id=user_id,
                clip_index=clip_index,
                instruction=user_instruction,
                template_id=template_match.template_id if template_match else None,
                cost=cost_estimate,
                success=True
            )
        
        return RegenerationResult(
            clip=new_clip,
            modified_prompt=modified_prompt,
            template_used=template_match.template_id if template_match else None,
            cost=cost_estimate
        )
        
    except Exception as e:
        # Track regeneration failure (for analytics) - non-blocking
        if user_id:
            # Use cost estimate calculated earlier (template or LLM path)
            track_regeneration_async(
                job_id=job_id,
                user_id=user_id,
                clip_index=clip_index,
                instruction=user_instruction,
                template_id=template_match.template_id if template_match else None,
                cost=cost_estimate,
                success=False
            )
        
        logger.error(
            f"Failed to generate new clip: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "video_model": video_model,
                "aspect_ratio": aspect_ratio,
                "target_duration": new_clip_prompt.duration,
                "has_scene_reference": bool(new_clip_prompt.scene_reference_url),
                "error_type": type(e).__name__,
                "stage": "video_generation"
            },
            exc_info=True
        )
        
        # Publish regeneration_failed event
        if event_publisher:
            await event_publisher("regeneration_failed", {
                "sequence": 999,
                "clip_index": clip_index,
                "error": str(e)
            })
        
        raise GenerationError(f"Failed to generate new clip: {str(e)}", job_id=job_id) from e


async def regenerate_clip_with_recomposition(
    job_id: UUID,
    clip_index: int,
    user_instruction: str,
    user_id: Optional[UUID] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    event_publisher: Optional[callable] = None
) -> RegenerationResult:
    """
    Regenerate clip and recompose full video.
    
    Steps:
    1-5: Same as regenerate_clip() (regenerate clip)
    6. Replace clip in Clips object
    7. Recompose video (full recomposition)
    8. Update job status
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to regenerate (0-based)
        user_instruction: User's modification instruction
        conversation_history: Optional conversation history
        event_publisher: Optional async callback(event_type, data) to publish events
        
    Returns:
        RegenerationResult with new clip, modified prompt, template used, cost, and video_output
        
    Raises:
        ValidationError: If clip_index is invalid or data loading fails
        GenerationError: If video generation fails
        CompositionError: If recomposition fails permanently
        RetryableError: If recomposition fails but is retryable
    """
    if conversation_history is None:
        conversation_history = []
    
    logger.info(
        f"Starting clip regeneration with recomposition",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "instruction": user_instruction,
            "conversation_history_length": len(conversation_history) if conversation_history else 0
        }
    )
    
    # Steps 1-5: Regenerate clip (from existing function)
    logger.debug(
        f"Calling regenerate_clip (step 1-5)",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    regeneration_result = await regenerate_clip(
        job_id=job_id,
        clip_index=clip_index,
        user_instruction=user_instruction,
        user_id=user_id,
        conversation_history=conversation_history,
        event_publisher=event_publisher
    )
    new_clip = regeneration_result.clip
    
    # Publish recomposition_started event
    if event_publisher:
        await event_publisher("recomposition_started", {
            "sequence": 5,
            "progress": 60,  # Recomposition starts at 60% of regeneration
            "clip_index": clip_index
        })
    
    # Step 6: Replace clip in Clips object
    logger.debug(
        f"Reloading clips for recomposition",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    clips = await load_clips_from_job_stages(job_id)
    if not clips:
        logger.error(
            f"Failed to reload clips for recomposition",
            extra={"job_id": str(job_id), "clip_index": clip_index, "stage": "recomposition"}
        )
        raise ValidationError(f"Failed to load clips for job {job_id}")
    
    logger.debug(
        f"Clips reloaded for recomposition",
        extra={
            "job_id": str(job_id),
            "total_clips": len(clips.clips),
            "clip_index": clip_index
        }
    )
    
    # Find clip by clip_index (not by array position, since clips may not be sequential)
    clip_position = None
    for i, clip in enumerate(clips.clips):
        if clip.clip_index == clip_index:
            clip_position = i
            break
    
    if clip_position is None:
        available_indices = [c.clip_index for c in clips.clips]
        logger.error(
            f"Clip not found during recomposition: clip_index does not exist",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": len(clips.clips),
                "available_clip_indices": available_indices
            }
        )
        raise ValidationError(
            f"Clip with index {clip_index} not found. "
            f"Available clip indices: {available_indices if available_indices else 'none'}. "
            f"The requested clip may be incomplete or not yet generated."
        )
    
    # Ensure new_clip has the correct clip_index
    if new_clip.clip_index != clip_index:
        logger.warning(
            f"New clip has incorrect clip_index ({new_clip.clip_index}), correcting to {clip_index}",
            extra={
                "job_id": str(job_id),
                "expected_clip_index": clip_index,
                "actual_clip_index": new_clip.clip_index
            }
        )
        # Create a copy with corrected clip_index
        if hasattr(new_clip, 'model_copy'):
            new_clip = new_clip.model_copy(update={'clip_index': clip_index})
        else:
            from copy import deepcopy
            new_clip = deepcopy(new_clip)
            new_clip.clip_index = clip_index
    
    # Replace clip at found position with regenerated clip
    logger.debug(
        f"Replacing clip at position {clip_position} (clip_index {clip_index})",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "clip_position": clip_position,
            "old_clip_url": clips.clips[clip_position].video_url,
            "new_clip_url": new_clip.video_url
        }
    )
    # Create a new list to avoid mutating the original (Pydantic models may be immutable)
    updated_clips = clips.clips.copy()
    updated_clips[clip_position] = new_clip
    
    # Reconstruct Clips object with updated clip
    updated_clips_obj = Clips(
        job_id=clips.job_id,
        clips=updated_clips,
        total_clips=clips.total_clips,
        successful_clips=len([c for c in updated_clips if c.status == "success"]),
        failed_clips=len([c for c in updated_clips if c.status == "failed"]),
        total_cost=clips.total_cost + regeneration_result.cost,
        total_generation_time=clips.total_generation_time
    )
    
    logger.info(
        f"Replaced clip {clip_index} in Clips object",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "successful_clips": updated_clips_obj.successful_clips,
            "total_cost": str(updated_clips_obj.total_cost)
        }
    )
    
    # Step 7: Recompose video (full recomposition)
    # Load required data for Composer
    logger.debug(
        f"Loading Composer inputs",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    try:
        audio_url = await get_audio_url(job_id)
        logger.debug(f"Audio URL loaded", extra={"job_id": str(job_id), "has_audio_url": bool(audio_url)})
        
        transitions = await load_transitions_from_job_stages(job_id)
        logger.debug(f"Transitions loaded", extra={"job_id": str(job_id), "transitions_count": len(transitions)})
        
        beat_timestamps = await load_beat_timestamps_from_job_stages(job_id)
        logger.debug(
            f"Beat timestamps loaded",
            extra={
                "job_id": str(job_id),
                "beat_timestamps_count": len(beat_timestamps) if beat_timestamps else 0
            }
        )
        
        aspect_ratio = await get_aspect_ratio(job_id)
        logger.debug(f"Aspect ratio loaded", extra={"job_id": str(job_id), "aspect_ratio": aspect_ratio})
        
        logger.info(
            f"Loaded Composer inputs",
            extra={
                "job_id": str(job_id),
                "transitions_count": len(transitions),
                "beat_timestamps_count": len(beat_timestamps) if beat_timestamps else 0,
                "aspect_ratio": aspect_ratio,
                "total_clips": updated_clips_obj.total_clips,
                "has_audio_url": bool(audio_url)
            }
        )
    except Exception as e:
        logger.error(
            f"Failed to load Composer inputs: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "error_type": type(e).__name__,
                "stage": "composer_input_loading"
            },
            exc_info=True
        )
        raise ValidationError(f"Failed to load Composer inputs: {str(e)}") from e
    
    # Call Composer with updated Clips
    try:
        logger.info(
            f"Starting video recomposition",
            extra={"job_id": str(job_id), "total_clips": updated_clips_obj.total_clips}
        )
        
        video_output = await composer_process(
            job_id=str(job_id),
            clips=updated_clips_obj,
            audio_url=audio_url,
            transitions=transitions,
            beat_timestamps=beat_timestamps,
            aspect_ratio=aspect_ratio
        )
        
        logger.info(
            f"Video recomposition completed successfully",
            extra={
                "job_id": str(job_id),
                "video_url": video_output.video_url,
                "duration": video_output.duration,
                "composition_time": video_output.composition_time
            }
        )
        
        # Publish recomposition_complete event
        if event_publisher:
            await event_publisher("recomposition_complete", {
                "sequence": 999,
                "progress": 100,
                "video_url": video_output.video_url,
                "duration": video_output.duration
            })
        
    except CompositionError as e:
        logger.error(
            f"Composition failed permanently: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": updated_clips_obj.total_clips,
                "error_type": type(e).__name__,
                "stage": "composer_process"
            },
            exc_info=True
        )
        
        # Publish recomposition_failed event
        if event_publisher:
            await event_publisher("recomposition_failed", {
                "sequence": 999,
                "clip_index": clip_index,
                "error": str(e)
            })
        
        raise
    except RetryableError as e:
        logger.error(
            f"Composition failed but is retryable: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": updated_clips_obj.total_clips,
                "error_type": type(e).__name__,
                "stage": "composer_process",
                "retryable": True
            },
            exc_info=True
        )
        
        # Publish recomposition_failed event
        if event_publisher:
            await event_publisher("recomposition_failed", {
                "sequence": 999,
                "clip_index": clip_index,
                "error": str(e),
                "retryable": True
            })
        
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during recomposition: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": updated_clips_obj.total_clips,
                "error_type": type(e).__name__,
                "stage": "composer_process"
            },
            exc_info=True
        )
        
        # Publish recomposition_failed event
        if event_publisher:
            await event_publisher("recomposition_failed", {
                "sequence": 999,
                "clip_index": clip_index,
                "error": str(e)
            })
        
        raise CompositionError(f"Recomposition failed: {str(e)}", job_id=job_id) from e
    
    # Step 8: Track regeneration cost
    try:
        # Get original prompt for cost tracking
        clip_prompts = await load_clip_prompts_from_job_stages(job_id)
        original_prompt = clip_prompts.clip_prompts[clip_index].prompt if clip_prompts else ""
        
        await track_regeneration_cost(
            job_id=job_id,
            clip_index=clip_index,
            original_prompt=original_prompt,
            modified_prompt=regeneration_result.modified_prompt,
            user_instruction=user_instruction,
            conversation_history=conversation_history,
            cost=regeneration_result.cost,
            status="completed"
        )
    except Exception as e:
        # Don't fail regeneration if cost tracking fails
        logger.warning(
            f"Failed to track regeneration cost: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index}
        )
    
    # Step 9: Update job status
    await update_job_status(
        job_id=job_id,
        status="completed",
        video_url=video_output.video_url
    )
    
    logger.info(
        f"Clip regeneration with recomposition completed successfully",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "video_url": video_output.video_url,
            "cost": str(regeneration_result.cost)
        }
    )
    
    return RegenerationResult(
        clip=new_clip,
        modified_prompt=regeneration_result.modified_prompt,
        template_used=regeneration_result.template_used,
        cost=regeneration_result.cost,
        video_output=video_output
    )

