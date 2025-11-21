"""
Regeneration process orchestration.

Main orchestration function for regenerating a single clip based on user instruction.
Handles template matching, LLM modification, and video generation.
"""

import asyncio
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
from modules.lipsync_processor.process import process_single_clip_lipsync
from modules.clip_regenerator.template_matcher import match_template, apply_template, is_lipsync_request
from modules.clip_regenerator.llm_modifier import modify_prompt_with_llm, estimate_llm_cost
from modules.clip_regenerator.context_builder import build_llm_context
from modules.clip_regenerator.character_parser import parse_character_selection
from modules.clip_regenerator.status_manager import update_job_status
from modules.clip_regenerator.cost_tracker import track_regeneration_cost
from modules.video_generator.generator import generate_video_clip
from modules.video_generator.config import get_generation_settings
from modules.video_generator.cost_estimator import estimate_clip_cost
from modules.video_generator.image_handler import download_and_upload_image
from modules.composer.process import process as composer_process
from modules.analytics.tracking import track_regeneration_async

logger = get_logger("clip_regenerator.process")


async def _retry_content_moderation_for_regeneration(
    original_clip_prompt: ClipPrompt,
    original_reference_images: List[str],
    image_url: Optional[str],
    settings_dict: dict,
    job_id: UUID,
    environment: str,
    aspect_ratio: str,
    temperature: Optional[float],
    seed: Optional[int],
    event_publisher: Optional[callable]
) -> Optional[Clip]:
    """
    Retry regeneration after content moderation failure.
    
    Implements the same 4-attempt strategy as main video generation:
    - Attempt 1: Original model + original prompt + refs (already failed)
    - Attempt 2: Veo 3.1 + sanitized prompt + reference images
    - Attempt 3: Kling Turbo + sanitized prompt + NO reference images
    - Attempt 4: Kling Turbo + sanitized prompt + NO reference images (retry)
    
    Args:
        original_clip_prompt: Original ClipPrompt that failed
        original_reference_images: List of reference image URLs used in original attempt
        image_url: Single reference image (backward compatibility)
        settings_dict: Generation settings
        job_id: Job ID for tracking
        environment: Environment (development/production)
        aspect_ratio: Video aspect ratio
        temperature: Temperature parameter for generation (Veo 3.1 only)
        seed: Seed parameter for generation (Veo 3.1 only)
        event_publisher: Optional event publisher callback
        
    Returns:
        Clip if any retry attempt succeeds, None if all fail
    """
    from modules.video_generator.prompt_sanitizer import sanitize_prompt_for_content_moderation
    
    # Sanitize the prompt once for all retry attempts
    sanitized_prompt = sanitize_prompt_for_content_moderation(
        original_clip_prompt.prompt, 
        job_id=str(job_id)
    )
    
    # Track which prompt to use
    prompt_sanitized = sanitized_prompt != original_clip_prompt.prompt
    
    if not prompt_sanitized:
        logger.warning(
            f"Prompt sanitization did not change the prompt - retrying anyway with Kling Turbo fallback",
            extra={
                "job_id": str(job_id),
                "clip_index": original_clip_prompt.clip_index
            }
        )
    
    # Attempt 2: Veo 3.1 with sanitized prompt + reference images
    logger.info(
        f"Content moderation retry attempt 2 for clip {original_clip_prompt.clip_index}: "
        f"Veo 3.1 with sanitized prompt + reference images",
        extra={
            "job_id": str(job_id),
            "clip_index": original_clip_prompt.clip_index,
            "attempt": 2,
            "model": "veo_31",
            "using_ref_images": True,
            "prompt_sanitized": prompt_sanitized
        }
    )
    
    # Create sanitized clip prompt for attempt 2
    sanitized_clip_prompt = ClipPrompt(
        clip_index=original_clip_prompt.clip_index,
        prompt=sanitized_prompt,
        negative_prompt=original_clip_prompt.negative_prompt,
        duration=original_clip_prompt.duration,
        scene_reference_url=original_clip_prompt.scene_reference_url,
        character_reference_urls=original_clip_prompt.character_reference_urls,
        object_reference_urls=original_clip_prompt.object_reference_urls,
        metadata=original_clip_prompt.metadata
    )
    
    try:
        clip = await generate_video_clip(
            clip_prompt=sanitized_clip_prompt,
            image_url=image_url,
            reference_image_urls=original_reference_images if original_reference_images else None,
            settings=settings_dict,
            job_id=job_id,
            environment=environment,
            video_model="veo_31",
            aspect_ratio=aspect_ratio,
            temperature=temperature,
            seed=seed
        )
        
        logger.info(
            f"Content moderation retry attempt 2 succeeded for clip {original_clip_prompt.clip_index}",
            extra={
                "job_id": str(job_id),
                "clip_index": original_clip_prompt.clip_index,
                "attempt": 2,
                "model": "veo_31"
            }
        )
        return clip
        
    except Exception as e:
        logger.warning(
            f"Content moderation retry attempt 2 failed for clip {original_clip_prompt.clip_index}: {str(e)}",
            extra={
                "job_id": str(job_id),
                "clip_index": original_clip_prompt.clip_index,
                "attempt": 2,
                "error": str(e)
            }
        )
    
    # Attempts 3-4: Kling Turbo without reference images
    for attempt_num in [3, 4]:
        logger.info(
            f"Content moderation retry attempt {attempt_num} for clip {original_clip_prompt.clip_index}: "
            f"Kling Turbo with sanitized prompt (no reference images)",
            extra={
                "job_id": str(job_id),
                "clip_index": original_clip_prompt.clip_index,
                "attempt": attempt_num,
                "model": "kling_v25_turbo",
                "using_ref_images": False,
                "prompt_sanitized": prompt_sanitized
            }
        )
        
        # Publish progress event for fallback attempt
        if event_publisher:
            await event_publisher("content_moderation_retry", {
                "sequence": 4.5,  # Between video_generating and video_generated
                "progress": 30,
                "clip_index": original_clip_prompt.clip_index,
                "attempt": attempt_num,
                "model": "kling_v25_turbo",
                "message": f"Retrying with Kling Turbo (attempt {attempt_num - 2}/2)"
            })
        
        try:
            # Use Kling Turbo without reference images (text-only)
            clip = await generate_video_clip(
                clip_prompt=sanitized_clip_prompt,
                image_url=None,  # No reference images for Kling Turbo fallback
                reference_image_urls=None,
                settings=settings_dict,
                job_id=job_id,
                environment=environment,
                video_model="kling_v25_turbo",
                aspect_ratio=aspect_ratio,
                temperature=None,  # Kling doesn't use temperature
                seed=None  # Kling doesn't use seed
            )
            
            logger.info(
                f"Content moderation retry attempt {attempt_num} succeeded for clip {original_clip_prompt.clip_index}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": original_clip_prompt.clip_index,
                    "attempt": attempt_num,
                    "model": "kling_v25_turbo"
                }
            )
            return clip
            
        except Exception as e:
            logger.warning(
                f"Content moderation retry attempt {attempt_num} failed for clip {original_clip_prompt.clip_index}: {str(e)}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": original_clip_prompt.clip_index,
                    "attempt": attempt_num,
                    "error": str(e)
                }
            )
            
            # Continue to next attempt if this wasn't the last one
            if attempt_num < 4:
                continue
    
    # All retry attempts failed
    logger.error(
        f"All content moderation retry attempts failed for clip {original_clip_prompt.clip_index}",
        extra={
            "job_id": str(job_id),
            "clip_index": original_clip_prompt.clip_index,
            "attempts_tried": "2-4",
            "models_tried": ["veo_31", "kling_v25_turbo"]
        }
    )
    return None


@dataclass
class RegenerationResult:
    """Result of clip regeneration."""
    
    clip: Clip
    modified_prompt: str
    template_used: Optional[str]
    cost: Decimal
    video_output: Optional[VideoOutput] = None  # Added for recomposition result
    temperature: Optional[float] = None  # LLM-determined temperature for video generation
    temperature_reasoning: Optional[str] = None  # Brief explanation of temperature choice
    seed: Optional[int] = None  # Seed used for video generation (reused for precise changes)


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


async def _collect_reference_images(
    clip_prompt: ClipPrompt,
    job_id: UUID,
    max_images: int = 3
) -> List[str]:
    """
    Collect all reference images (character + scene + object) for video generation.
    
    Similar to the batch process logic, but for single clip regeneration.
    Prioritizes character references, then scene, then objects.
    Veo 3.1 supports up to 3 reference images total.
    
    Args:
        clip_prompt: ClipPrompt with reference URLs
        job_id: Job ID for logging
        max_images: Maximum number of reference images (default: 3 for Veo 3.1)
        
    Returns:
        List of Replicate-ready image URLs (downloaded/uploaded)
    """
    collected_urls = []
    
    # Detect if clip is face-heavy (close-up, mid-shot, portrait, face-focused)
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
    
    # Add character reference URLs
    # FACE-HEAVY CLIPS: Use ALL character references (no artificial limit)
    # OTHER CLIPS: Limit to 2 to leave room for scene/objects
    character_refs_added = 0
    if clip_prompt.character_reference_urls:
        if is_face_heavy:
            # Face-heavy clips: Prioritize ALL character references
            max_char_refs = len(clip_prompt.character_reference_urls)
            logger.info(
                f"Face-heavy clip detected - prioritizing ALL {len(clip_prompt.character_reference_urls)} character reference(s) for regeneration",
                extra={
                    "job_id": str(job_id),
                    "num_character_refs": len(clip_prompt.character_reference_urls),
                    "shot_type": "mid-shot" if is_medium_shot else "close-up",
                    "camera_angle": camera_angle if camera_angle else None
                }
            )
        else:
            # Other clips: Limit to 2 to leave room for scene/objects
            max_char_refs = min(len(clip_prompt.character_reference_urls), 2)
        
        for char_ref_url in clip_prompt.character_reference_urls[:max_char_refs]:
            if len(collected_urls) >= max_images:
                break
            try:
                downloaded_url = await download_and_upload_image(char_ref_url, job_id)
                if downloaded_url:
                    collected_urls.append(downloaded_url)
                    character_refs_added += 1
                    logger.debug(
                        f"Downloaded character reference for regeneration",
                        extra={"job_id": str(job_id), "url": char_ref_url[:50]}
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to download character reference: {e}",
                    extra={"job_id": str(job_id), "url": char_ref_url[:50]}
                )
    
    # Add scene reference URL if available and we have room (max 3 total)
    # For face-heavy clips: Only add scene if there's room after ALL characters
    if clip_prompt.scene_reference_url and len(collected_urls) < max_images:
        try:
            downloaded_url = await download_and_upload_image(clip_prompt.scene_reference_url, job_id)
            if downloaded_url:
                collected_urls.append(downloaded_url)
                logger.debug(
                    f"Downloaded scene reference for regeneration",
                    extra={"job_id": str(job_id)}
                )
        except Exception as e:
            logger.warning(
                f"Failed to download scene reference: {e}",
                extra={"job_id": str(job_id), "url": clip_prompt.scene_reference_url[:50]}
            )
    
    # Add object reference URLs if available and we have room (max 3 total)
    # For face-heavy clips: Only add objects if there's room after ALL characters and scene
    if clip_prompt.object_reference_urls and len(collected_urls) < max_images:
        remaining_slots = max_images - len(collected_urls)
        max_obj_refs = min(len(clip_prompt.object_reference_urls), remaining_slots)
        for obj_ref_url in clip_prompt.object_reference_urls[:max_obj_refs]:
            if len(collected_urls) >= max_images:
                break
            try:
                downloaded_url = await download_and_upload_image(obj_ref_url, job_id)
                if downloaded_url:
                    collected_urls.append(downloaded_url)
                    logger.debug(
                        f"Downloaded object reference for regeneration",
                        extra={"job_id": str(job_id), "url": obj_ref_url[:50]}
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to download object reference: {e}",
                    extra={"job_id": str(job_id), "url": obj_ref_url[:50]}
                )
    
    logger.info(
        f"Collected {len(collected_urls)} reference image(s) for regeneration "
        f"(face_heavy={is_face_heavy}, {character_refs_added}/{len(clip_prompt.character_reference_urls) if clip_prompt.character_reference_urls else 0} character refs, "
        f"{len(clip_prompt.object_reference_urls) if clip_prompt.object_reference_urls else 0} object refs available)",
        extra={
            "job_id": str(job_id),
            "num_images": len(collected_urls),
            "num_character_refs": character_refs_added,
            "total_character_refs_available": len(clip_prompt.character_reference_urls) if clip_prompt.character_reference_urls else 0,
            "has_character_refs": bool(clip_prompt.character_reference_urls),
            "has_scene_ref": bool(clip_prompt.scene_reference_url),
            "has_object_refs": bool(clip_prompt.object_reference_urls),
            "object_refs_count": len(clip_prompt.object_reference_urls) if clip_prompt.object_reference_urls else 0,
            "face_heavy": is_face_heavy,
            "shot_type": "mid-shot" if is_medium_shot else ("close-up" if is_face_heavy else "wide"),
            "camera_angle": camera_angle if camera_angle else None
        }
    )
    
    return collected_urls


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
    
    # Check if this is a lipsync request (must be checked BEFORE template matching)
    if is_lipsync_request(user_instruction):
        logger.info(
            f"Lipsync request detected, routing to lipsync processor",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "instruction": user_instruction
            }
        )
        
        # Publish lipsync_started event
        if event_publisher:
            await event_publisher("lipsync_started", {
                "clip_index": clip_index,
                "instruction": user_instruction
            })
        
        # Load clips to get the specific clip
        clips = await load_clips_from_job_stages(job_id)
        if not clips:
            raise ValidationError(
                f"Failed to load clips for job {job_id}. "
                "The job may not have completed video generation yet."
            )
        
        # Find the specific clip
        original_clip = None
        for clip in clips.clips:
            if clip.clip_index == clip_index:
                original_clip = clip
                break
        
        if original_clip is None:
            available_indices = [c.clip_index for c in clips.clips]
            raise ValidationError(
                f"Clip with index {clip_index} not found. "
                f"Available clip indices: {available_indices if available_indices else 'none'}."
            )
        
        # Get audio URL
        audio_url = await get_audio_url(job_id)
        
        # Parse character selection from instruction
        character_ids = None
        scene_plan = await load_scene_plan_from_job_stages(job_id)
        if scene_plan:
            character_ids = parse_character_selection(
                instruction=user_instruction,
                scene_plan=scene_plan,
                clip_index=clip_index
            )
            if character_ids:
                logger.info(
                    f"Character selection parsed: {character_ids}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_index,
                        "character_ids": character_ids,
                        "instruction": user_instruction
                    }
                )
            else:
                logger.info(
                    f"No specific character selection found, will sync all visible characters",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_index,
                        "instruction": user_instruction
                    }
                )
        
        # Process through lipsync processor
        lipsynced_clip = await process_single_clip_lipsync(
            clip=original_clip,
            clip_index=clip_index,
            audio_url=audio_url,
            job_id=job_id,
            environment=environment,
            event_publisher=event_publisher,
            character_ids=character_ids if character_ids else None
        )
        
        # Return result in RegenerationResult format (for compatibility)
        # Note: For lipsync, we don't modify the prompt, so we use the original prompt
        clip_prompts = await load_clip_prompts_from_job_stages(job_id)
        original_prompt_text = ""
        if clip_prompts and clip_index < len(clip_prompts.clip_prompts):
            original_prompt_text = clip_prompts.clip_prompts[clip_index].prompt
        
        logger.info(
            f"Lipsync processing complete",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "cost": float(lipsynced_clip.cost)
            }
        )
        
        return RegenerationResult(
            clip=lipsynced_clip,
            modified_prompt=original_prompt_text,  # No prompt modification for lipsync
            template_used="lipsync",  # Special template identifier
            cost=lipsynced_clip.cost,
            temperature=None,  # No temperature for lipsync (not regenerating)
            temperature_reasoning="Lipsync operation - no video regeneration",
            seed=None  # No seed for lipsync
        )
    
    # NOTE: regeneration_started event is published by the worker, not here
    # This avoids duplicate "Regeneration started" messages in the UI
    
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
    
    # CRITICAL FIX: Load the MOST RECENT version of the prompt for cumulative revisions
    # Strategy: Check if there's a prior regenerated version in clip_versions table
    # If yes, use that prompt (which already has prior revisions appended)
    # If no, use the original prompt from clip_prompts
    from modules.clip_regenerator.data_loader import load_clip_version
    
    db_client = DatabaseClient()
    latest_version_prompt = None
    latest_version_data = None
    
    try:
        # Get the latest version from clip_versions table (highest version_number)
        result = await db_client.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq("clip_index", clip_index).order("version_number", desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            latest_version_data = result.data[0]
            latest_version_prompt = latest_version_data.get("prompt")
            
            logger.info(
                f"Using prompt from latest version for cumulative revisions",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "version_number": latest_version_data.get("version_number"),
                    "prompt_length": len(latest_version_prompt) if latest_version_prompt else 0
                }
            )
    except Exception as e:
        logger.debug(
            f"No prior versions found in clip_versions table, using original prompt: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index}
        )
    
    # Get the original prompt for reference URLs and metadata
    original_prompt = clip_prompts.clip_prompts[clip_index]
    
    # If we found a latest version, use its prompt for cumulative revisions
    # Otherwise, use the original prompt
    if latest_version_prompt:
        # Create a new ClipPrompt with the latest version's prompt but original reference URLs
        original_prompt = ClipPrompt(
            clip_index=original_prompt.clip_index,
            prompt=latest_version_prompt,  # Use latest version's prompt
            negative_prompt=original_prompt.negative_prompt,
            duration=original_prompt.duration,
            scene_reference_url=original_prompt.scene_reference_url,
            character_reference_urls=original_prompt.character_reference_urls,
            object_reference_urls=original_prompt.object_reference_urls,
            metadata=original_prompt.metadata
        )
    
    logger.debug(
        f"Prompt retrieved for regeneration",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "prompt_length": len(original_prompt.prompt),
            "has_negative_prompt": bool(original_prompt.negative_prompt),
            "has_scene_reference": bool(original_prompt.scene_reference_url),
            "character_references_count": len(original_prompt.character_reference_urls) if original_prompt.character_reference_urls else 0,
            "using_latest_version": latest_version_prompt is not None
        }
    )
    
    # Get job configuration (aspect_ratio only - video_model always defaults to Veo 3.1 for regeneration)
    logger.debug(
        f"Loading job configuration",
        extra={"job_id": str(job_id)}
    )
    job_config = await _get_job_config(job_id)
    # Always default to Veo 3.1 for regeneration
    # Only switch to Kling Turbo if content moderation retry is needed (handled in video generator)
    video_model = "veo_31"
    aspect_ratio = job_config["aspect_ratio"]
    logger.debug(
        f"Job configuration loaded",
        extra={
            "job_id": str(job_id),
            "video_model": video_model,
            "aspect_ratio": aspect_ratio,
            "environment": environment,
            "note": "Always using Veo 3.1 for regeneration (Kling Turbo only used in content moderation retry)"
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
    
    # Initialize temperature and reasoning variables
    temperature = 0.7  # Default temperature
    temperature_reasoning = "Template match - using default temperature"
    
    # Templates that represent moderate visual changes should ALWAYS use LLM modification
    # for better prompt rewriting. LLM can rewrite the prompt more effectively than just
    # appending text, which is crucial for creating meaningful visual changes even with
    # temperature control. This applies to all models, including Veo 3.1.
    moderate_change_templates = {"nighttime", "daytime", "brighter", "darker"}
    use_llm_for_template = (
        template_match is not None 
        and template_match.template_id in moderate_change_templates
    )
    
    if template_match and not use_llm_for_template:
        # Step 3: Apply template transformation (for simple changes or Veo 3.1)
        modified_prompt = apply_template(original_prompt.prompt, template_match)
        cost_estimate = estimate_clip_cost(original_clip.target_duration, environment)
        # Use default temperature for template matches
        temperature = 0.7
        temperature_reasoning = f"Template match ({template_match.template_id}) - using default temperature"
        
        logger.info(
            f"Template matched: {template_match.template_id}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "template_id": template_match.template_id,
                "temperature": temperature,
                "video_model": video_model
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
        
        llm_result = await modify_prompt_with_llm(
            original_prompt.prompt,
            user_instruction,
            context,
            conversation_history,
            job_id=job_id
        )
        
        # Extract prompt, temperature, and reasoning from LLM result
        if isinstance(llm_result, dict):
            modified_prompt = llm_result.get("prompt", "")
            temperature = llm_result.get("temperature", 0.7)
            temperature_reasoning = llm_result.get("reasoning", "")
        else:
            # Backward compatibility: if LLM returns string (shouldn't happen with new code)
            logger.warning(
                f"LLM returned string instead of dict, using fallback",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            modified_prompt = llm_result if isinstance(llm_result, str) else ""
            temperature = 0.7
            temperature_reasoning = "Fallback - LLM returned unexpected format"
        
        cost_estimate = estimate_llm_cost() + estimate_clip_cost(original_clip.target_duration, environment)
        
        logger.info(
            f"Prompt modified via LLM",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "original_length": len(original_prompt.prompt),
                "modified_length": len(modified_prompt),
                "temperature": temperature,
                "temperature_reasoning": temperature_reasoning[:100] if temperature_reasoning else "",
                "instruction_type": (
                    "precise" if temperature < 0.5 
                    else "moderate" if temperature < 0.8 
                    else "complete_regeneration"
                )
            }
        )
    
    # Publish prompt_modified event
    if event_publisher:
        await event_publisher("prompt_modified", {
            "sequence": 3,
            "modified_prompt": modified_prompt,
            "template_used": template_match.template_id if template_match else None,
            "temperature": temperature,
            "temperature_reasoning": temperature_reasoning
        })
    
    # Step 5: Generate new clip
    # Create new ClipPrompt with modified prompt
    # IMPORTANT: Preserve ALL reference images (character + scene + object) for consistency
    new_clip_prompt = ClipPrompt(
        clip_index=clip_index,
        prompt=modified_prompt,
        negative_prompt=original_prompt.negative_prompt,
        duration=original_prompt.duration,
        scene_reference_url=original_prompt.scene_reference_url,
        character_reference_urls=original_prompt.character_reference_urls,
        object_reference_urls=original_prompt.object_reference_urls,  # ✅ FIX: Preserve object references
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
    
    # Collect all reference images (character + scene + object) for Veo 3.1
    # This ensures object references (like the truck) are preserved during regeneration
    logger.debug(
        f"Collecting reference images for regeneration",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "has_scene_reference": bool(new_clip_prompt.scene_reference_url),
            "has_character_references": bool(new_clip_prompt.character_reference_urls),
            "has_object_references": bool(new_clip_prompt.object_reference_urls),
            "object_refs_count": len(new_clip_prompt.object_reference_urls) if new_clip_prompt.object_reference_urls else 0
        }
    )
    reference_image_urls = await _collect_reference_images(
        new_clip_prompt,
        job_id,
        max_images=3  # Veo 3.1 supports up to 3 reference images
    )
    
    # Use first image for backward compatibility (single image parameter)
    image_url = reference_image_urls[0] if reference_image_urls else new_clip_prompt.scene_reference_url
    
    # Extract seed from original clip metadata for precise changes
    # For precise changes (low temperature), reuse original seed to maintain consistency
    # For complete regenerations (high temperature), use random seed for variation
    original_seed = None
    if original_clip.metadata:
        original_seed = original_clip.metadata.get("generation_seed")
        if original_seed is not None:
            try:
                original_seed = int(original_seed)
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid seed value in metadata: {original_seed}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
                original_seed = None
    
    # Determine seed strategy based on temperature
    seed = None
    if temperature < 0.5 and original_seed is not None:
        # Use original seed for precise changes to maintain consistency
        seed = original_seed
        logger.info(
            f"Using original seed {seed} for precise change (temperature={temperature})",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "temperature": temperature,
                "seed": seed
            }
        )
    else:
        # Use random seed (None) for moderate/complete regenerations
        logger.info(
            f"Using random seed for variation (temperature={temperature})",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "temperature": temperature
            }
        )
    
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
            "has_object_references": bool(new_clip_prompt.object_reference_urls),
            "object_refs_count": len(new_clip_prompt.object_reference_urls) if new_clip_prompt.object_reference_urls else 0,
            "num_reference_images": len(reference_image_urls),
            "modified_prompt_length": len(modified_prompt),
            "template_used": template_match.template_id if template_match else None,
            "temperature": temperature,
            "seed": seed
        }
    )
    
    # CRITICAL: Determine next version number BEFORE generating clip
    # This allows us to use versioned filenames (e.g., clip_4_v2.mp4) to preserve original
    db_for_version = DatabaseClient()
    version_result = await db_for_version.table("clip_versions").select("version_number").eq(
        "job_id", str(job_id)
    ).eq("clip_index", clip_index).order("version_number", desc=True).limit(1).execute()
    
    next_version = 2  # Default to version 2 if no versions exist
    if version_result.data and len(version_result.data) > 0:
        next_version = version_result.data[0].get("version_number", 1) + 1
    
    logger.info(
        f"Regenerating clip as version {next_version} (preserves original in storage)",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "next_version": next_version
        }
    )
    
    try:
        new_clip = await generate_video_clip(
            clip_prompt=new_clip_prompt,
            image_url=image_url,
            reference_image_urls=reference_image_urls if reference_image_urls else None,  # ✅ FIX: Pass all reference images for Veo 3.1
            settings=settings_dict,
            job_id=job_id,
            environment=environment,
            video_model=video_model,
            aspect_ratio=aspect_ratio,
            temperature=temperature if video_model == "veo_31" else None,  # Only pass temperature for Veo 3.1
            seed=seed if video_model == "veo_31" else None,  # Only pass seed for Veo 3.1
            version_number=next_version  # ✅ NEW: Pass version number for versioned filename
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
            import asyncio
            # Fire and forget - don't block on analytics tracking
            asyncio.create_task(track_regeneration_async(
                job_id=job_id,
                user_id=user_id,
                clip_index=clip_index,
                instruction=user_instruction,
                template_id=template_match.template_id if template_match else None,
                cost=cost_estimate,
                success=True
            ))
        
        return RegenerationResult(
            clip=new_clip,
            modified_prompt=modified_prompt,
            template_used=template_match.template_id if template_match else None,
            cost=cost_estimate,
            temperature=temperature,
            temperature_reasoning=temperature_reasoning,
            seed=seed
        )
        
    except RetryableError as e:
        # Check if this is a content moderation error that needs retry
        error_message = str(e).lower()
        is_content_moderation = (
            "content moderation" in error_message or 
            "fallback to kling turbo" in error_message or
            "flagged as sensitive" in error_message
        )
        
        if is_content_moderation:
            logger.info(
                f"Content moderation error detected for clip {clip_index}, attempting retry with fallback",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "error": str(e)
                }
            )
            
            # Publish retry event
            if event_publisher:
                await event_publisher("content_moderation_retry_starting", {
                    "sequence": 4.2,
                    "clip_index": clip_index,
                    "message": "Content moderation triggered, retrying with sanitized prompt and fallback model"
                })
            
            # Attempt retry with content moderation fallback
            try:
                new_clip = await _retry_content_moderation_for_regeneration(
                    original_clip_prompt=new_clip_prompt,
                    original_reference_images=reference_image_urls if reference_image_urls else [],
                    image_url=image_url,
                    settings_dict=settings_dict,
                    job_id=job_id,
                    environment=environment,
                    aspect_ratio=aspect_ratio,
                    temperature=temperature if video_model == "veo_31" else None,
                    seed=seed if video_model == "veo_31" else None,
                    event_publisher=event_publisher
                )
                
                if new_clip:
                    logger.info(
                        f"Content moderation retry succeeded for clip {clip_index}",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_index,
                            "fallback_model": new_clip.model if hasattr(new_clip, 'model') else "unknown"
                        }
                    )
                    
                    # Track successful regeneration (after retry)
                    if user_id:
                        import asyncio
                        asyncio.create_task(track_regeneration_async(
                            job_id=job_id,
                            user_id=user_id,
                            clip_index=clip_index,
                            instruction=user_instruction,
                            template_id=template_match.template_id if template_match else None,
                            cost=cost_estimate,
                            success=True
                        ))
                    
                    return RegenerationResult(
                        clip=new_clip,
                        modified_prompt=modified_prompt,
                        template_used=template_match.template_id if template_match else None,
                        cost=cost_estimate,
                        temperature=temperature,
                        temperature_reasoning=temperature_reasoning,
                        seed=seed
                    )
                else:
                    # All retry attempts failed
                    logger.error(
                        f"All content moderation retry attempts failed for clip {clip_index}",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_index
                        }
                    )
                    
                    # Track failure
                    if user_id:
                        import asyncio
                        asyncio.create_task(track_regeneration_async(
                            job_id=job_id,
                            user_id=user_id,
                            clip_index=clip_index,
                            instruction=user_instruction,
                            template_id=template_match.template_id if template_match else None,
                            cost=cost_estimate,
                            success=False
                        ))
                    
                    # Publish failure event
                    if event_publisher:
                        await event_publisher("regeneration_failed", {
                            "sequence": 999,
                            "clip_index": clip_index,
                            "error": "Content moderation: all retry attempts failed"
                        })
                    
                    raise GenerationError(
                        f"Failed to regenerate clip after content moderation retries: {str(e)}", 
                        job_id=job_id
                    ) from e
                    
            except Exception as retry_error:
                logger.error(
                    f"Error during content moderation retry for clip {clip_index}: {retry_error}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_index,
                        "error_type": type(retry_error).__name__
                    },
                    exc_info=True
                )
                
                # Track failure
                if user_id:
                    import asyncio
                    asyncio.create_task(track_regeneration_async(
                        job_id=job_id,
                        user_id=user_id,
                        clip_index=clip_index,
                        instruction=user_instruction,
                        template_id=template_match.template_id if template_match else None,
                        cost=cost_estimate,
                        success=False
                    ))
                
                # Publish failure event
                if event_publisher:
                    await event_publisher("regeneration_failed", {
                        "sequence": 999,
                        "clip_index": clip_index,
                        "error": str(retry_error)
                    })
                
                raise GenerationError(
                    f"Failed during content moderation retry: {str(retry_error)}", 
                    job_id=job_id
                ) from retry_error
        else:
            # Non-content-moderation retryable error - just fail for now
            logger.error(
                f"Retryable error (non-content-moderation) for clip {clip_index}: {e}",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "error_type": type(e).__name__,
                    "stage": "video_generation"
                },
                exc_info=True
            )
            
            # Track failure
            if user_id:
                import asyncio
                asyncio.create_task(track_regeneration_async(
                    job_id=job_id,
                    user_id=user_id,
                    clip_index=clip_index,
                    instruction=user_instruction,
                    template_id=template_match.template_id if template_match else None,
                    cost=cost_estimate,
                    success=False
                ))
            
            # Publish failure event
            if event_publisher:
                await event_publisher("regeneration_failed", {
                    "sequence": 999,
                    "clip_index": clip_index,
                    "error": str(e)
                })
            
            raise GenerationError(f"Failed to generate new clip: {str(e)}", job_id=job_id) from e
            
    except Exception as e:
        # Non-retryable error
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
        
        # Track failure
        if user_id:
            import asyncio
            asyncio.create_task(track_regeneration_async(
                job_id=job_id,
                user_id=user_id,
                clip_index=clip_index,
                instruction=user_instruction,
                template_id=template_match.template_id if template_match else None,
                cost=cost_estimate,
                success=False
            ))
        
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
    old_clip = clips.clips[clip_position]
    old_clip_url = old_clip.video_url
    new_clip_url = new_clip.video_url
    
    logger.info(
        f"Replacing clip at position {clip_position} (clip_index {clip_index})",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "clip_position": clip_position,
            "old_clip_url": old_clip_url,
            "new_clip_url": new_clip_url,
            "urls_different": old_clip_url != new_clip_url,
            "template_used": regeneration_result.template_used
        }
    )
    
    # Verify that we have a new video URL (for debugging)
    if old_clip_url == new_clip_url and regeneration_result.template_used != "lipsync":
        logger.warning(
            f"WARNING: New clip has same video_url as old clip! This might indicate an issue.",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "video_url": old_clip_url,
                "template_used": regeneration_result.template_used
            }
        )
    
    # Save original clip to clip_versions table BEFORE overwriting (if not already saved)
    # This preserves the original for comparison purposes
    # IMPORTANT: Load the TRUE original from clip_versions v1 if it exists, not from job_stages
    # (job_stages may already have a regenerated clip from a previous regeneration)
    original_clip = clips.clips[clip_position]
    
    # CRITICAL: Save versions with retry logic to prevent silent failures
    db = DatabaseClient()
    version_save_max_retries = 3
    version_save_retry_delay = 1.0  # seconds
    
    # Step 1: Save original clip as version 1 (if not already saved)
    try:
        # Check if version 1 already exists for this clip
        existing_version = await db.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq("clip_index", clip_index).eq("version_number", 1).limit(1).execute()
        
        # Only save if version 1 doesn't exist yet
        if not existing_version.data or len(existing_version.data) == 0:
            # This is the first regeneration - save the current clip as version 1 (original)
            # Get prompt for original clip
            clip_prompts = await load_clip_prompts_from_job_stages(job_id)
            original_prompt = ""
            if clip_prompts and clip_index < len(clip_prompts.clip_prompts):
                original_prompt = clip_prompts.clip_prompts[clip_index].prompt
            
            # Get thumbnail if available
            thumbnail_url = None
            try:
                thumb_result = await db.table("clip_thumbnails").select("thumbnail_url").eq(
                    "job_id", str(job_id)
                ).eq("clip_index", clip_index).limit(1).execute()
                if thumb_result.data and len(thumb_result.data) > 0:
                    thumbnail_url = thumb_result.data[0].get("thumbnail_url")
            except Exception:
                pass  # Table may not exist
            
            # Save original clip as version 1 WITH RETRY LOGIC
            version_data = {
                "job_id": str(job_id),
                "clip_index": clip_index,
                "version_number": 1,
                "video_url": original_clip.video_url,
                "thumbnail_url": thumbnail_url,
                "prompt": original_prompt,
                "user_instruction": None,  # Original has no instruction
                "cost": float(original_clip.cost) if original_clip.cost else 0.0,
                "duration": float(original_clip.actual_duration) if original_clip.actual_duration else None,
                "is_current": False,  # Version 1 is not current after regeneration
                "created_at": "now()"
            }
            
            # Retry loop for version 1 save
            for attempt in range(1, version_save_max_retries + 1):
                try:
                    await db.table("clip_versions").insert(version_data).execute()
                    logger.info(
                        f"✅ Saved original clip to clip_versions as version 1 (attempt {attempt})",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_index,
                            "video_url": original_clip.video_url,
                            "attempt": attempt
                        }
                    )
                    break  # Success!
                except Exception as e:
                    if attempt < version_save_max_retries:
                        logger.warning(
                            f"⚠️ Failed to save version 1 (attempt {attempt}/{version_save_max_retries}), retrying...",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_index,
                                "attempt": attempt,
                                "error": str(e),
                                "error_type": type(e).__name__
                            }
                        )
                        await asyncio.sleep(version_save_retry_delay * attempt)  # Exponential backoff
                    else:
                        # CRITICAL: Last attempt failed - raise error to fail the regeneration
                        logger.error(
                            f"❌ CRITICAL: Failed to save version 1 after {version_save_max_retries} attempts",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_index,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "version_data": version_data
                            },
                            exc_info=True
                        )
                        raise GenerationError(
                            f"Failed to save original clip version to database after {version_save_max_retries} attempts: {str(e)}",
                            job_id=job_id
                        ) from e
        else:
            # Version 1 already exists - this means we've regenerated before
            # The original is already saved, so we don't need to save it again
            logger.debug(
                f"Original clip (version 1) already exists in clip_versions, skipping save",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "existing_v1_url": existing_version.data[0].get("video_url")
                }
            )
    except GenerationError:
        # Re-raise generation errors (these are intentional failures)
        raise
    except Exception as e:
        # CRITICAL: Unexpected error in version 1 check/save - don't swallow it
        logger.error(
            f"❌ CRITICAL: Unexpected error while checking/saving version 1",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        raise GenerationError(
            f"Unexpected error while saving original clip version: {str(e)}",
            job_id=job_id
        ) from e
    
    # Save the regenerated clip as a new version WITH RETRY LOGIC
    # Note: Calculate next_version here (not in regenerate_clip function, different scope)
    # This ensures the version number matches the filename (clip_X_vN.mp4)
    
    # Get the next version number
    version_result_for_save = await db.table("clip_versions").select("version_number").eq(
        "job_id", str(job_id)
    ).eq("clip_index", clip_index).order("version_number", desc=True).limit(1).execute()
    
    next_version = 2  # Default to version 2 if no versions exist
    if version_result_for_save.data and len(version_result_for_save.data) > 0:
        next_version = version_result_for_save.data[0].get("version_number", 1) + 1
    
    logger.info(
        f"Determined next version number: {next_version} for saving to clip_versions",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "next_version": next_version
        }
    )
    
    # Mark all previous versions as not current
    await db.table("clip_versions").update({"is_current": False}).eq(
        "job_id", str(job_id)
    ).eq("clip_index", clip_index).execute()
    
    # Get thumbnail if available
    thumbnail_url = None
    try:
        thumb_result = await db.table("clip_thumbnails").select("thumbnail_url").eq(
            "job_id", str(job_id)
        ).eq("clip_index", clip_index).limit(1).execute()
        if thumb_result.data and len(thumb_result.data) > 0:
            thumbnail_url = thumb_result.data[0].get("thumbnail_url")
    except Exception:
        pass  # Table may not exist
    
    # Save regenerated clip as new version WITH RETRY LOGIC
    regenerated_version_data = {
        "job_id": str(job_id),
        "clip_index": clip_index,
        "version_number": next_version,
        "video_url": new_clip_url,
        "thumbnail_url": thumbnail_url,
        "prompt": regeneration_result.modified_prompt,  # From regeneration_result
        "user_instruction": user_instruction,
        "cost": float(regeneration_result.cost) if regeneration_result.cost else 0.0,
        "duration": float(new_clip.actual_duration) if new_clip.actual_duration else None,
        "is_current": True,  # This is the current version
        "created_at": "now()"
    }
    
    # Retry loop for regenerated version save
    for attempt in range(1, version_save_max_retries + 1):
        try:
            await db.table("clip_versions").insert(regenerated_version_data).execute()
            logger.info(
                f"✅ Saved regenerated clip to clip_versions as version {next_version} (attempt {attempt})",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "version_number": next_version,
                    "video_url": new_clip_url,
                    "attempt": attempt
                }
            )
            break  # Success!
        except Exception as e:
            if attempt < version_save_max_retries:
                logger.warning(
                    f"⚠️ Failed to save regenerated version (attempt {attempt}/{version_save_max_retries}), retrying...",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_index,
                        "attempt": attempt,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "version_data": regenerated_version_data
                    }
                )
                await asyncio.sleep(version_save_retry_delay * attempt)  # Exponential backoff
            else:
                # CRITICAL: Last attempt failed - raise error to fail the regeneration
                logger.error(
                    f"❌ CRITICAL: Failed to save regenerated version after {version_save_max_retries} attempts",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_index,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "version_data": regenerated_version_data
                    },
                    exc_info=True
                )
                raise GenerationError(
                    f"Failed to save regenerated clip version to database after {version_save_max_retries} attempts: {str(e)}",
                    job_id=job_id
                ) from e
    
    # CRITICAL VERIFICATION: Verify both versions exist in database using helper function
    try:
        from modules.clip_regenerator.version_verifier import verify_clip_versions_after_save
        
        verification = await verify_clip_versions_after_save(
            job_id=job_id,
            clip_index=clip_index,
            expected_original_url=old_clip_url,  # Verify original URL is preserved
            expected_latest_url=new_clip_url,    # Verify new URL is saved
            expected_latest_version=next_version
        )
        
        if not verification.get("success"):
            logger.error(
                "⚠️ Database verification returned failure",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "verification": verification
                }
            )
    except Exception as e:
        # Don't fail regeneration if verification fails, but log it
        logger.error(
            "⚠️ Failed to verify clip versions in database (non-fatal)",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "error": str(e),
                "error_type": type(e).__name__
                },
                exc_info=True
            )
    
    # Create a new list to avoid mutating the original (Pydantic models may be immutable)
    updated_clips = clips.clips.copy()
    updated_clips[clip_position] = new_clip
    
    # Verify replacement worked
    replaced_clip = updated_clips[clip_position]
    if replaced_clip.video_url != new_clip_url:
        logger.error(
            f"CRITICAL: Clip replacement failed! Expected video_url {new_clip_url}, got {replaced_clip.video_url}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "expected_url": new_clip_url,
                "actual_url": replaced_clip.video_url
            }
        )
        raise ValidationError(
            f"Clip replacement failed: video_url mismatch. "
            f"Expected: {new_clip_url}, Got: {replaced_clip.video_url}"
        )
    
    logger.info(
        f"Clip replacement verified successfully",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "new_video_url": replaced_clip.video_url
        }
    )
    
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
        # Log the clip URLs that will be used for recomposition
        clip_urls = [clip.video_url for clip in updated_clips_obj.clips]
        logger.info(
            f"Starting video recomposition",
            extra={
                "job_id": str(job_id),
                "total_clips": updated_clips_obj.total_clips,
                "clip_urls": clip_urls,
                "regenerated_clip_index": clip_index,
                "regenerated_clip_url": updated_clips_obj.clips[clip_position].video_url if clip_position is not None else None
            }
        )
        
        # Pass changed_clip_index to composer for potential optimization
        # (Currently composer doesn't use this, but it's available for future optimization)
        video_output = await composer_process(
            job_id=str(job_id),
            clips=updated_clips_obj,
            audio_url=audio_url,
            transitions=transitions,
            beat_timestamps=beat_timestamps,
            aspect_ratio=aspect_ratio,
            changed_clip_index=clip_index
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
        
        # CRITICAL FIX: DO NOT update job_stages with regenerated clips!
        # Reason: job_stages should always preserve the ORIGINAL clips for comparison purposes.
        # The clip_versions table is the source of truth for regenerated versions.
        # If we update job_stages here, we overwrite the original clip URLs, making
        # comparison impossible (both "original" and "regenerated" would show the same video).
        #
        # The recomposition already updated the final video URL in the jobs table,
        # which is all we need. Subsequent regenerations should load from clip_versions,
        # not from job_stages.
        logger.info(
            f"Skipping job_stages update to preserve original clip URLs for comparison",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_clips": updated_clips_obj.total_clips,
                "note": "job_stages preserves original clips, clip_versions tracks regenerated versions"
            }
        )
        
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
    
    # Step 9: Update job status and video_url
    logger.info(
        f"Updating job status and video_url",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "new_video_url": video_output.video_url,
            "template_used": regeneration_result.template_used
        }
    )
    await update_job_status(
        job_id=job_id,
        status="completed",
        video_url=video_output.video_url
    )
    
    # Verify the update worked
    try:
        db_verify = DatabaseClient()
        verify_result = await db_verify.table("jobs").select("video_url").eq("id", str(job_id)).limit(1).execute()
        if verify_result.data:
            job_data = verify_result.data[0] if isinstance(verify_result.data, list) else verify_result.data
            actual_video_url = job_data.get("video_url")
            if actual_video_url != video_output.video_url:
                logger.error(
                    f"CRITICAL: Job video_url update failed! Expected {video_output.video_url}, got {actual_video_url}",
                    extra={
                        "job_id": str(job_id),
                        "expected_url": video_output.video_url,
                        "actual_url": actual_video_url
                    }
                )
            else:
                logger.info(
                    f"Job video_url updated successfully",
                    extra={
                        "job_id": str(job_id),
                        "video_url": actual_video_url
                    }
                )
    except Exception as e:
        logger.warning(
            f"Failed to verify job video_url update: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
    
    logger.info(
        f"Clip regeneration with recomposition completed successfully",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "video_url": video_output.video_url,
            "cost": str(regeneration_result.cost),
            "template_used": regeneration_result.template_used
        }
    )
    
    # Publish final regeneration_complete event with full video URL
    if event_publisher:
        await event_publisher("regeneration_complete", {
            "sequence": 1000,
            "clip_index": clip_index,
            "new_clip_url": new_clip.video_url,
            "video_url": video_output.video_url,  # Full recomposed video URL
            "cost": float(regeneration_result.cost),
            "temperature": regeneration_result.temperature,
            "seed": regeneration_result.seed,
            "template_used": regeneration_result.template_used
        })
    
    return RegenerationResult(
        clip=new_clip,
        modified_prompt=regeneration_result.modified_prompt,
        template_used=regeneration_result.template_used,
        cost=regeneration_result.cost,
        video_output=video_output,
        temperature=regeneration_result.temperature,
        temperature_reasoning=regeneration_result.temperature_reasoning,
        seed=regeneration_result.seed
    )

