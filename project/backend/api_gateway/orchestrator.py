"""
Pipeline orchestration logic.

Executes modules 3-8 sequentially with progress tracking and error handling.
"""

import json
from uuid import UUID
from typing import Optional
from decimal import Decimal
from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.cost_tracking import CostTracker
from shared.config import settings
from shared.errors import (
    PipelineError,
    BudgetExceededError,
    RetryableError,
    ValidationError,
    GenerationError
)
from shared.logging import get_logger
from api_gateway.services.event_publisher import publish_event
from api_gateway.services.sse_manager import broadcast_event
from api_gateway.services.budget_helpers import get_budget_limit

logger = get_logger(__name__)

db_client = DatabaseClient()
redis_client = RedisClient()
cost_tracker = CostTracker()


async def check_cancellation(job_id: str) -> bool:
    """
    Check if job has been cancelled.
    
    Args:
        job_id: Job ID to check
        
    Returns:
        True if cancelled, False otherwise
    """
    try:
        cancel_key = f"job_cancel:{job_id}"
        cancelled = await redis_client.get(cancel_key)
        return cancelled is not None
    except Exception as e:
        logger.warning("Failed to check cancellation flag", exc_info=e)
        return False


async def should_stop_after_stage(stage_name: str, stop_at_stage: str = None) -> bool:
    """
    Check if pipeline should stop after the current stage.
    
    Args:
        stage_name: Current stage name
        stop_at_stage: Stage to stop at (if set)
        
    Returns:
        True if should stop, False otherwise
    """
    if not stop_at_stage:
        return False
    
    return stage_name == stop_at_stage


async def stop_pipeline_gracefully(job_id: str, stage_name: str, progress: int) -> None:
    """
    Stop pipeline gracefully after completing a stage.
    
    Args:
        job_id: Job ID
        stage_name: Stage that just completed
        progress: Current progress percentage
    """
    await db_client.table("jobs").update({
        "current_stage": stage_name,
        "progress": progress,
        "updated_at": "now()"
    }).eq("id", job_id).execute()
    
    # Invalidate cache
    cache_key = f"job_status:{job_id}"
    await redis_client.client.delete(cache_key)
    
    logger.info(
        f"Pipeline stopped gracefully after {stage_name} (progress: {progress}%)",
        extra={"job_id": job_id, "stage": stage_name, "progress": progress}
    )


async def update_progress(job_id: str, progress: int, stage_name: str) -> None:
    """
    Update job progress in database and publish progress event.
    
    Args:
        job_id: Job ID
        progress: Progress percentage (0-100)
        stage_name: Current stage name
    """
    try:
        # Update database
        await db_client.table("jobs").update({
            "progress": progress,
            "current_stage": stage_name,
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        # Publish progress event (both Redis pub/sub and direct SSE broadcast)
        progress_data = {
            "progress": progress,
            "estimated_remaining": None,  # TODO: Calculate based on stage
            "stage": stage_name
        }
        await publish_event(job_id, "progress", progress_data)
        await broadcast_event(job_id, "progress", progress_data)
        
        logger.info(
            "Progress updated",
            extra={"job_id": job_id, "progress": progress, "stage": stage_name}
        )
        
    except Exception as e:
        logger.error("Failed to update progress", exc_info=e, extra={"job_id": job_id})


async def enforce_budget(job_id: str) -> None:
    """
    Enforce budget limit for a job.
    
    Raises BudgetExceededError if limit exceeded.
    
    Args:
        job_id: Job ID to enforce budget for
    """
    try:
        limit = get_budget_limit(settings.environment)
        await cost_tracker.enforce_budget_limit(UUID(job_id), limit=limit)
    except BudgetExceededError as e:
        # Publish error event
        await publish_event(job_id, "error", {
            "error": str(e),
            "code": "BUDGET_EXCEEDED",
            "retryable": False
        })
        raise


async def handle_pipeline_error(job_id: str, error: Exception) -> None:
    """
    Handle pipeline error by marking job as failed and publishing error event.
    
    Args:
        job_id: Job ID
        error: Exception that occurred
    """
    try:
        error_message = str(error)
        # Check if it's a BudgetExceededError
        if isinstance(error, BudgetExceededError):
            error_code = "BUDGET_EXCEEDED"
            retryable = False
        else:
            error_code = getattr(error, "code", "MODULE_FAILURE")
            retryable = isinstance(error, RetryableError)
        
        # Update job status
        await db_client.table("jobs").update({
            "status": "failed",
            "error_message": error_message,
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        # Publish error event
        await publish_event(job_id, "error", {
            "error": error_message,
            "code": error_code,
            "retryable": retryable
        })
        
        logger.error(
            "Pipeline error handled",
            exc_info=error,
            extra={"job_id": job_id, "error_code": error_code}
        )
        
    except Exception as e:
        logger.error("Failed to handle pipeline error", exc_info=e, extra={"job_id": job_id})


async def execute_pipeline(job_id: str, audio_url: str, user_prompt: str, stop_at_stage: str = None) -> None:
    """
    Execute the video generation pipeline (modules 3-8).
    
    Args:
        job_id: Job ID
        audio_url: URL of uploaded audio file
        user_prompt: User's creative prompt
        stop_at_stage: Optional stage to stop at (for testing: audio_parser, scene_planner, reference_generator, prompt_generator, video_generator, composer)
    """
    try:
        # Stage 1: Audio Parser (10% progress)
        # Publish stage update FIRST before status change to avoid flickering
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "started"
        })
        
        # Update job status to processing
        await db_client.table("jobs").update({
            "status": "processing",
            "current_stage": "audio_parser",
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Import and call Audio Parser
        # Note: Modules will be implemented later, so we'll use stubs for now
        await publish_event(job_id, "message", {
            "text": "Starting audio analysis...",
            "stage": "audio_parser"
        })
        # Set initial progress after stage is established
        await update_progress(job_id, 1, "audio_parser")
        
        try:
            from modules.audio_parser.main import process_audio_analysis
            await publish_event(job_id, "message", {
                "text": "Analyzing audio structure and beats...",
                "stage": "audio_parser"
            })
            await update_progress(job_id, 5, "audio_parser")
            # Convert job_id from str to UUID for audio parser
            job_id_uuid = UUID(job_id)
            logger.info(f"Calling audio parser for job {job_id}", extra={"job_id": job_id, "audio_url": audio_url})
            audio_data = await process_audio_analysis(job_id_uuid, audio_url)
            logger.info(
                f"Audio parser completed successfully for job {job_id}: "
                f"BPM={audio_data.bpm:.1f}, duration={audio_data.duration:.2f}s, "
                f"beats={len(audio_data.beat_timestamps)}",
                extra={"job_id": job_id}
            )
        except ImportError as e:
            # Module not implemented yet - use stub
            logger.warning("Audio Parser module not found, using stub", extra={"job_id": job_id})
            await publish_event(job_id, "message", {
                "text": "Extracting audio features...",
                "stage": "audio_parser"
            })
            await update_progress(job_id, 5, "audio_parser")
            
            # Simulate processing time with progress updates
            import asyncio
            await asyncio.sleep(0.5)  # Simulate processing
            await update_progress(job_id, 6, "audio_parser")
            await publish_event(job_id, "message", {
                "text": "Detecting beats and structure...",
                "stage": "audio_parser"
            })
            await asyncio.sleep(0.5)
            await update_progress(job_id, 8, "audio_parser")
            
            # Create stub audio_data
            from shared.models.audio import AudioAnalysis, SongStructure, Mood, ClipBoundary
            # Get audio duration from file (stub: assume 120 seconds)
            duration = 120.0  # TODO: Get actual duration from audio file
            beat_timestamps = [float(i * 0.5) for i in range(int(duration * 2))]  # Stub beats every 0.5s
            
            # Generate clip boundaries: 4-8 second clips, minimum 3 clips
            # Align to beats, create boundaries every ~6 seconds
            clip_boundaries = []
            clip_duration = 6.0  # Target 6 seconds per clip
            current_start = 0.0
            clip_index = 0
            
            while current_start < duration:
                clip_end = min(current_start + clip_duration, duration)
                clip_boundaries.append(ClipBoundary(
                    start=current_start,
                    end=clip_end,
                    duration=clip_end - current_start
                ))
                current_start = clip_end
                clip_index += 1
                # Ensure minimum 3 clips
                if clip_index >= 3 and current_start >= duration:
                    break
            
            # If we don't have enough clips, adjust
            if len(clip_boundaries) < 3:
                # Redistribute evenly
                clip_boundaries = []
                clips_needed = 3
                clip_duration = duration / clips_needed
                for i in range(clips_needed):
                    start = i * clip_duration
                    end = (i + 1) * clip_duration if i < clips_needed - 1 else duration
                    clip_boundaries.append(ClipBoundary(
                        start=start,
                        end=end,
                        duration=end - start
                    ))
            
            # Convert job_id to UUID for stub as well
            job_id_uuid = UUID(job_id)
            audio_data = AudioAnalysis(
                job_id=job_id_uuid,
                bpm=120.0,
                duration=duration,
                beat_timestamps=beat_timestamps,
                song_structure=[
                    SongStructure(type="intro", start=0.0, end=10.0, energy="low"),
                    SongStructure(type="verse", start=10.0, end=30.0, energy="medium"),
                    SongStructure(type="chorus", start=30.0, end=50.0, energy="high"),
                    SongStructure(type="verse", start=50.0, end=70.0, energy="medium"),
                    SongStructure(type="chorus", start=70.0, end=90.0, energy="high"),
                    SongStructure(type="outro", start=90.0, end=duration, energy="low"),
                ],
                mood=Mood(
                    primary="energetic",
                    energy_level="high",
                    confidence=0.8
                ),
                lyrics=[],
                clip_boundaries=clip_boundaries
            )
        
        await update_progress(job_id, 10, "audio_parser")  # Audio parser is 10% of total job
        await publish_event(job_id, "message", {
            "text": "Audio analysis complete!",
            "stage": "audio_parser"
        })
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "completed",
            "duration": audio_data.duration if hasattr(audio_data, 'duration') else (audio_data.beat_timestamps[-1] if audio_data.beat_timestamps else 0)
        })
        
        # Log audio parser results
        logger.info(
            "Audio parser results",
            extra={
                "job_id": job_id,
                "bpm": audio_data.bpm,
                "duration": audio_data.duration,
                "beat_count": len(audio_data.beat_timestamps),
                "structure_segments": len(audio_data.song_structure),
                "mood": audio_data.mood.primary if hasattr(audio_data.mood, 'primary') else str(audio_data.mood),
                "energy_level": audio_data.mood.energy_level if hasattr(audio_data.mood, 'energy_level') else None
            }
        )
        
        # Publish audio parser results for frontend display (before checking stop)
        # Extract metadata if available
        metadata = audio_data.metadata if hasattr(audio_data, 'metadata') and audio_data.metadata else {}
        
        await publish_event(job_id, "audio_parser_results", {
            "bpm": audio_data.bpm,
            "duration": audio_data.duration,
            "beat_timestamps": audio_data.beat_timestamps[:20],  # First 20 beats
            "beat_count": len(audio_data.beat_timestamps),
            "song_structure": [
                {
                    "type": seg.type,
                    "start": seg.start,
                    "end": seg.end,
                    "energy": seg.energy
                }
                for seg in audio_data.song_structure
            ],
            "mood": {
                "primary": audio_data.mood.primary if hasattr(audio_data.mood, 'primary') else str(audio_data.mood),
                "energy_level": audio_data.mood.energy_level if hasattr(audio_data.mood, 'energy_level') else None,
                "confidence": audio_data.mood.confidence if hasattr(audio_data.mood, 'confidence') else None
            },
            "lyrics_count": len(audio_data.lyrics),
            "clip_boundaries_count": len(audio_data.clip_boundaries),
            "clip_boundaries": [
                {
                    "start": boundary.start,
                    "end": boundary.end,
                    "duration": boundary.duration
                }
                for boundary in audio_data.clip_boundaries
            ],
            "metadata": {
                "cache_hit": metadata.get("cache_hit", False),
                "fallback_used": metadata.get("fallbacks_used", []),
                "beat_detection_confidence": metadata.get("beat_detection_confidence"),
                "structure_confidence": metadata.get("structure_confidence"),
                "mood_confidence": metadata.get("mood_confidence"),
                "processing_time": metadata.get("processing_time")
            }
        })
        
        # Check if should stop after audio parser (after publishing results)
        if await should_stop_after_stage("audio_parser", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "audio_parser", 10)
            return
        
        # Stage 2: Scene Planner (20% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "scene_planner",
            "status": "started"
        })
        await publish_event(job_id, "message", {
            "text": "Starting scene planning...",
            "stage": "scene_planner"
        })
        await update_progress(job_id, 12, "scene_planner")
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        try:
            from modules.scene_planner.main import process_scene_planning
            await publish_event(job_id, "message", {
                "text": "Generating video plan with director knowledge...",
                "stage": "scene_planner"
            })
            await update_progress(job_id, 15, "scene_planner")
            
            # Convert job_id to UUID with error handling
            try:
                job_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid job_id format: {job_id}", exc_info=e, extra={"job_id": job_id})
                raise ValidationError(f"Invalid job_id format: {job_id}", job_id=job_id) from e
            
            plan = await process_scene_planning(
                job_id=job_uuid,
                user_prompt=user_prompt,
                audio_data=audio_data
            )
            await publish_event(job_id, "message", {
                "text": "Scene planning complete!",
                "stage": "scene_planner"
            })
        except (ValidationError, GenerationError) as e:
            # Scene Planner validation or generation error
            logger.error("Scene Planner failed", exc_info=e, extra={"job_id": job_id})
            await handle_pipeline_error(job_id, e)
            raise
        except ImportError:
            logger.warning("Scene Planner module not found, using stub", extra={"job_id": job_id})
            await publish_event(job_id, "message", {
                "text": "Scene Planner module not found, using stub data...",
                "stage": "scene_planner"
            })
            from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition
            import asyncio
            await asyncio.sleep(1.0)  # Simulate processing time
            
            # Generate clip scripts based on clip boundaries from audio_data
            clip_scripts = []
            transitions = []
            
            for idx, boundary in enumerate(audio_data.clip_boundaries):
                clip_scripts.append(ClipScript(
                    clip_index=idx,
                    start=boundary.start,
                    end=boundary.end,
                    visual_description=f"Scene {idx + 1}: {user_prompt[:50]}...",
                    motion="tracking shot" if idx % 2 == 0 else "static",
                    camera_angle="wide" if idx == 0 else "medium",
                    characters=["char1"],
                    scenes=["scene1"],
                    lyrics_context=None,
                    beat_intensity="high" if audio_data.mood.energy_level == "high" else "medium"
                ))
                
                # Create transitions between clips
                if idx < len(audio_data.clip_boundaries) - 1:
                    transitions.append(Transition(
                        from_clip=idx,
                        to_clip=idx + 1,
                        type="cut" if audio_data.mood.energy_level == "high" else "crossfade",
                        duration=0.5 if audio_data.mood.energy_level != "high" else 0.0,
                        rationale="Beat-aligned transition"
                    ))
            
            plan = ScenePlan(
                job_id=UUID(job_id),
                video_summary=f"Music video for: {user_prompt[:100]}",
                characters=[
                    Character(id="char1", description="Main character", role="main character")
                ],
                scenes=[
                    Scene(id="scene1", description="Urban setting", time_of_day="day")
                ],
                style=Style(
                    color_palette=["#FF5733", "#33FF57", "#3357FF"],
                    visual_style="realistic",
                    mood=audio_data.mood.primary,
                    lighting="bright" if audio_data.mood.energy_level == "high" else "soft",
                    cinematography="dynamic"
                ),
                clip_scripts=clip_scripts,
                transitions=transitions
            )
        
        await update_progress(job_id, 20, "scene_planner")
        await publish_event(job_id, "stage_update", {
            "stage": "scene_planner",
            "status": "completed"
        })
        
        # Publish scene planner results for frontend display (before checking stop)
        try:
            logger.info("Publishing scene planner results", extra={"job_id": job_id, "plan_has_clips": len(plan.clip_scripts) if plan else 0})
            await publish_event(job_id, "scene_planner_results", {
                "job_id": str(plan.job_id),
                "video_summary": plan.video_summary,
                "characters": [
                    {
                        "id": char.id,
                        "description": char.description,
                        "role": char.role
                    }
                    for char in plan.characters
                ],
                "scenes": [
                    {
                        "id": scene.id,
                        "description": scene.description,
                        "time_of_day": scene.time_of_day
                    }
                    for scene in plan.scenes
                ],
                "style": {
                    "color_palette": plan.style.color_palette,
                    "visual_style": plan.style.visual_style,
                    "mood": plan.style.mood,
                    "lighting": plan.style.lighting,
                    "cinematography": plan.style.cinematography
                },
                "clip_scripts": [
                    {
                        "clip_index": clip.clip_index,
                        "start": clip.start,
                        "end": clip.end,
                        "visual_description": clip.visual_description,
                        "motion": clip.motion,
                        "camera_angle": clip.camera_angle,
                        "characters": clip.characters,
                        "scenes": clip.scenes,
                        "lyrics_context": clip.lyrics_context,
                        "beat_intensity": clip.beat_intensity
                    }
                    for clip in plan.clip_scripts
                ],
                "transitions": [
                    {
                        "from_clip": trans.from_clip,
                        "to_clip": trans.to_clip,
                        "type": trans.type,
                        "duration": trans.duration,
                        "rationale": trans.rationale
                    }
                    for trans in plan.transitions
                ]
            })
            logger.info("Scene planner results published successfully", extra={"job_id": job_id})
        except Exception as e:
            logger.error("Failed to publish scene planner results", exc_info=e, extra={"job_id": job_id})
            # Don't fail the pipeline, but log the error
        
        # Check if should stop after scene planner (after publishing results)
        if await should_stop_after_stage("scene_planner", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "scene_planner", 20)
            return
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        logger.info("Scene planner completed, continuing to reference generator", extra={"job_id": job_id})
        
        # Stage 3: Reference Generator (30% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "reference_generator",
            "status": "started"
        })
        await update_progress(job_id, 30, "reference_generator")
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Check budget before expensive operation (duration-based)
        # Get audio duration from audio_data (already in scope after audio_parser stage)
        duration_minutes = audio_data.duration / 60.0
        budget_limit = Decimal(str(duration_minutes * 200.0))
        
        # Calculate estimated cost for reference generation (with 20% buffer)
        estimated_cost = Decimal(str((len(plan.scenes) + len(plan.characters)) * 0.005 * 1.2))
        
        # Check budget
        can_proceed = await cost_tracker.check_budget(
            job_id=UUID(job_id),
            new_cost=estimated_cost,
            limit=budget_limit
        )
        if not can_proceed:
            raise BudgetExceededError(
                f"Would exceed budget limit before reference generation "
                f"(estimated: ${estimated_cost}, limit: ${budget_limit})",
                job_id=UUID(job_id)
            )
        
        references = None
        events = []
        try:
            from modules.reference_generator.process import process as generate_references
            # Pass duration_seconds for mid-generation budget checks
            references, events = await generate_references(
                job_id=UUID(job_id),
                plan=plan,
                duration_seconds=audio_data.duration
            )
            
            # Publish all events returned from module
            for event in events:
                await publish_event(job_id, event["event_type"], event["data"])
                
        except ImportError:
            logger.warning("Reference Generator module not found, using stub", extra={"job_id": job_id})
        except BudgetExceededError as e:
            # Budget exceeded - publish error event
            logger.error("Budget exceeded in reference generator", exc_info=e, extra={"job_id": job_id})
            await publish_event(job_id, "error", {
                "stage": "reference_generator",
                "reason": "Budget exceeded",
                "message": str(e),
                "fallback_mode": True
            })
            await db_client.table("job_stages").insert({
                "job_id": job_id,
                "stage_name": "reference_generator",
                "status": "failed",
                "metadata": json.dumps({
                    "fallback_mode": True,
                    "fallback_reason": "Budget exceeded"
                })
            }).execute()
            references = None
        except ValidationError as e:
            # Validation error - publish error event
            logger.error("Validation error in reference generator", exc_info=e, extra={"job_id": job_id})
            await publish_event(job_id, "error", {
                "stage": "reference_generator",
                "reason": "Validation error",
                "message": str(e),
                "fallback_mode": True
            })
            await db_client.table("job_stages").insert({
                "job_id": job_id,
                "stage_name": "reference_generator",
                "status": "failed",
                "metadata": json.dumps({
                    "fallback_mode": True,
                    "fallback_reason": str(e)
                })
            }).execute()
            references = None
        except GenerationError as e:
            # Generation error - publish error event
            logger.error("Generation error in reference generator", exc_info=e, extra={"job_id": job_id})
            await publish_event(job_id, "error", {
                "stage": "reference_generator",
                "reason": "Generation error",
                "message": str(e),
                "fallback_mode": True
            })
            await db_client.table("job_stages").insert({
                "job_id": job_id,
                "stage_name": "reference_generator",
                "status": "failed",
                "metadata": json.dumps({
                    "fallback_mode": True,
                    "fallback_reason": str(e)
                })
            }).execute()
            references = None
        except Exception as e:
            # Other errors - set fallback flag
            logger.warning("Reference Generator failed, setting fallback mode", exc_info=e, extra={"job_id": job_id})
            await publish_event(job_id, "error", {
                "stage": "reference_generator",
                "reason": "Unknown error",
                "message": str(e),
                "fallback_mode": True
            })
            await db_client.table("job_stages").insert({
                "job_id": job_id,
                "stage_name": "reference_generator",
                "status": "failed",
                "metadata": json.dumps({
                    "fallback_mode": True,
                    "fallback_reason": str(e)
                })
            }).execute()
            references = None
        
        await update_progress(job_id, 30, "reference_generator")
        
        # Publish completion event if not already published by module
        if not any(e.get("event_type") == "stage_update" and e.get("data", {}).get("status") == "completed" for e in events):
            await publish_event(job_id, "stage_update", {
                "stage": "reference_generator",
                "status": "completed",
                "references": references is not None,
                "fallback_mode": references is None
            })
        
        # Check if should stop after reference generator
        if await should_stop_after_stage("reference_generator", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "reference_generator", 30)
            return
        
        # Enforce budget after reference generator (if costs were tracked)
        await enforce_budget(job_id)
        
        # Stage 4: Prompt Generator (40% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "prompt_generator",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Check fallback mode from job_stages
        fallback_mode = False
        try:
            stage_result = await db_client.table("job_stages").select("metadata").eq("job_id", job_id).eq("stage_name", "reference_generator").execute()
            if stage_result.data and stage_result.data[0].get("metadata"):
                metadata = stage_result.data[0]["metadata"]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                fallback_mode = metadata.get("fallback_mode", False)
        except Exception as e:
            logger.warning("Failed to check fallback mode", exc_info=e)
        
        try:
            from modules.prompt_generator.process import process as generate_prompts
            clip_prompts = await generate_prompts(job_id, plan, references)
        except ImportError:
            logger.warning("Prompt Generator module not found, using stub", extra={"job_id": job_id})
            from shared.models.video import ClipPrompts, ClipPrompt
            # Create stub ClipPrompts from plan's clip_scripts with all required fields
            stub_prompts = []
            for clip_script in plan.clip_scripts:
                duration = clip_script.end - clip_script.start
                stub_prompts.append(ClipPrompt(
                    clip_index=clip_script.clip_index,
                    prompt=clip_script.visual_description or "A scene",
                    negative_prompt="blurry, low quality, distorted, watermark, text",
                    duration=duration,
                    scene_reference_url=None,
                    character_reference_urls=[],
                    metadata={}
                ))
            clip_prompts = ClipPrompts(
                job_id=UUID(job_id),
                clip_prompts=stub_prompts,
                total_clips=len(stub_prompts),
                generation_time=0.0
            )
        
        await update_progress(job_id, 40, "prompt_generator")
        await publish_event(job_id, "stage_update", {
            "stage": "prompt_generator",
            "status": "completed"
        })
        
        # Check if should stop after prompt generator
        if await should_stop_after_stage("prompt_generator", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "prompt_generator", 40)
            return
        
        # Stage 5: Video Generator (85% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Check budget before expensive operation (environment-aware)
        limit = get_budget_limit(settings.environment)
        can_proceed = await cost_tracker.check_budget(
            job_id=UUID(job_id),
            new_cost=Decimal("100.00"),  # Estimated cost for video generation
            limit=limit
        )
        if not can_proceed:
            raise BudgetExceededError("Would exceed budget limit before video generation")
        
        try:
            from modules.video_generator.process import process as generate_videos
            clips = await generate_videos(job_id, clip_prompts)
        except ImportError:
            logger.warning("Video Generator module not found, using stub", extra={"job_id": job_id})
            from shared.models.video import Clips, Clip
            from decimal import Decimal
            # Create stub clips (minimum 3 required)
            stub_clips = [
                Clip(
                    clip_index=i,
                    video_url=f"stub_clip_{i}_url",
                    actual_duration=5.0,
                    target_duration=5.0,
                    duration_diff=0.0,
                    status="success",
                    cost=Decimal("0.00"),
                    retry_count=0,
                    generation_time=0.0
                )
                for i in range(3)
            ]
            clips = Clips(
                job_id=UUID(job_id),
                clips=stub_clips,
                total_clips=3,
                successful_clips=3,
                failed_clips=0,
                total_cost=Decimal("0.00"),
                total_generation_time=0.0
            )
        
        # Validate minimum clips
        if len(clips.clips) < 3:
            raise PipelineError("Insufficient clips generated (minimum 3 required)")
        
        await update_progress(job_id, 85, "video_generator")
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "completed"
        })
        
        # Check if should stop after video generator
        if await should_stop_after_stage("video_generator", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "video_generator", 85)
            return
        
        # Enforce budget after video generator (costs were tracked)
        await enforce_budget(job_id)
        
        # Stage 6: Composer (100% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "composer",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Extract transitions and beats
        transitions = plan.transitions if hasattr(plan, "transitions") else []
        beat_timestamps = audio_data.beat_timestamps if hasattr(audio_data, "beat_timestamps") else []
        
        try:
            from modules.composer.process import process as compose_video
            video_output = await compose_video(
                job_id,
                clips,
                audio_url,
                transitions,
                beat_timestamps
            )
        except ImportError:
            logger.warning("Composer module not found, using stub", extra={"job_id": job_id})
            from shared.models.video import VideoOutput
            from decimal import Decimal
            video_output = VideoOutput(
                job_id=UUID(job_id),
                video_url="stub_final_video_url",
                duration=120.0,
                audio_duration=audio_data.duration if hasattr(audio_data, 'duration') else 120.0,
                sync_drift=0.0,
                clips_used=len(clips.clips) if hasattr(clips, 'clips') else 0,
                clips_trimmed=0,
                clips_looped=0,
                transitions_applied=len(transitions) if transitions else 0,
                file_size_mb=0.0,
                composition_time=0.0,
                cost=Decimal("0.00"),
                status="success"
            )
        
        # Get final cost
        job_result = await db_client.table("jobs").select("total_cost").eq("id", job_id).execute()
        total_cost = job_result.data[0].get("total_cost", 0) if job_result.data else 0
        
        # Update job as completed
        await db_client.table("jobs").update({
            "status": "completed",
            "progress": 100,
            "current_stage": "composer",
            "video_url": video_output.video_url,
            "total_cost": total_cost,
            "completed_at": "now()",
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        await update_progress(job_id, 100, "composer")
        await publish_event(job_id, "completed", {
            "video_url": video_output.video_url,
            "total_cost": float(total_cost)
        })
        
        logger.info("Pipeline completed successfully", extra={"job_id": job_id, "total_cost": total_cost})
        
    except (BudgetExceededError, PipelineError) as e:
        await handle_pipeline_error(job_id, e)
        raise
    except Exception as e:
        logger.error("Pipeline execution failed", exc_info=e, extra={"job_id": job_id})
        await handle_pipeline_error(job_id, PipelineError(f"Pipeline execution failed: {str(e)}"))
        raise
