"""
Pipeline orchestration logic.

Executes modules 3-8 sequentially with progress tracking and error handling.
"""

import json
import time
from datetime import datetime
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
from api_gateway.services.budget_helpers import get_budget_limit, get_cost_estimate
from api_gateway.services.time_estimator import calculate_estimated_remaining

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


def calculate_stage_progress(
    completed_items: int,
    total_items: int,
    stage_start_progress: int,
    stage_end_progress: int
) -> int:
    """
    Calculate progress percentage within a stage based on completed items.
    
    Args:
        completed_items: Number of items completed
        total_items: Total number of items in stage
        stage_start_progress: Starting progress percentage for this stage
        stage_end_progress: Ending progress percentage for this stage
        
    Returns:
        Progress percentage (0-100), clamped to stage range
    """
    if total_items == 0:
        return stage_start_progress
    
    stage_range = stage_end_progress - stage_start_progress
    completion_ratio = completed_items / total_items
    progress = stage_start_progress + int(completion_ratio * stage_range)
    
    # Clamp to stage range
    return max(stage_start_progress, min(progress, stage_end_progress))


async def update_progress(
    job_id: str,
    progress: int,
    stage_name: str,
    audio_duration: Optional[float] = None,
    num_clips: Optional[int] = None,
    num_images: Optional[int] = None
) -> None:
    """
    Update job progress in database and publish progress event.
    
    Args:
        job_id: Job ID
        progress: Progress percentage (0-100)
        stage_name: Current stage name
        audio_duration: Audio duration in seconds (optional, for estimation)
        num_clips: Number of video clips (optional, for video_generator stage)
        num_images: Number of reference images (optional, for reference_generator stage)
    """
    try:
        # Try to get audio_duration from Redis if not provided
        if audio_duration is None:
            try:
                duration_str = await redis_client.get(f"job:{job_id}:audio_duration")
                if duration_str:
                    audio_duration = float(duration_str)
            except Exception:
                pass  # Gracefully handle if Redis unavailable or key doesn't exist
        
        # Calculate estimated remaining time
        estimated_remaining = None
        if audio_duration is not None:
            estimated_remaining = await calculate_estimated_remaining(
                job_id=job_id,
                current_stage=stage_name,
                progress=progress,
                audio_duration=audio_duration,
                environment=settings.environment,
                num_clips=num_clips,
                num_images=num_images
            )
        
        # Update database
        update_data = {
            "progress": progress,
            "current_stage": stage_name,
            "updated_at": "now()"
        }
        if estimated_remaining is not None:
            update_data["estimated_remaining"] = estimated_remaining
        
        await db_client.table("jobs").update(update_data).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        # Publish progress event (both Redis pub/sub and direct SSE broadcast)
        progress_data = {
            "progress": progress,
            "estimated_remaining": estimated_remaining,
            "stage": stage_name
        }
        await publish_event(job_id, "progress", progress_data)
        await broadcast_event(job_id, "progress", progress_data)
        
        logger.info(
            "Progress updated",
            extra={
                "job_id": job_id,
                "progress": progress,
                "stage": stage_name,
                "estimated_remaining": estimated_remaining
            }
        )
        
    except Exception as e:
        logger.error("Failed to update progress", exc_info=e, extra={"job_id": job_id})


async def publish_cost_update(job_id: str, stage_name: str) -> None:
    """
    Publish cost_update SSE event with current total cost.
    
    Args:
        job_id: Job ID
        stage_name: Stage name that just completed
    """
    try:
        total_cost = await cost_tracker.get_total_cost(UUID(job_id))
        await publish_event(job_id, "cost_update", {
            "stage": stage_name,
            "cost": 0.0,  # Incremental cost not available here, just total
            "total": float(total_cost)
        })
    except Exception as e:
        # Don't fail pipeline if cost update publishing fails
        logger.debug(f"Failed to publish cost_update event: {e}", extra={"job_id": job_id})


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
    logger.info(
        f"execute_pipeline called for job {job_id}",
        extra={
            "job_id": job_id,
            "audio_url": audio_url,
            "user_prompt_length": len(user_prompt) if user_prompt else 0,
            "stop_at_stage": stop_at_stage
        }
    )
    try:
        # Stage 1: Audio Parser (10% progress)
        # Publish stage update FIRST before status change to avoid flickering
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "started"
        })
        
        # Track stage start time
        try:
            from api_gateway.services.db_helpers import update_job_stage
            # Check if stage exists
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "audio_parser").execute()
            if existing.data and len(existing.data) > 0:
                # Update existing
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "audio_parser").execute()
            else:
                # Insert new
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "audio_parser",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track audio parser start time", exc_info=e, extra={"job_id": job_id})
        
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
            
            # Store audio duration in Redis for time estimation
            try:
                await redis_client.set(
                    f"job:{job_id}:audio_duration",
                    str(audio_data.duration),
                    ex=3600  # 1 hour TTL
                )
            except Exception as e:
                logger.warning("Failed to store audio duration in Redis", exc_info=e, extra={"job_id": job_id})
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
        
        # Store audio duration in Redis for time estimation (for both real and stub)
        try:
            await redis_client.set(
                f"job:{job_id}:audio_duration",
                str(audio_data.duration),
                ex=3600  # 1 hour TTL
            )
        except Exception as e:
            logger.warning("Failed to store audio duration in Redis", exc_info=e, extra={"job_id": job_id})
        
        await update_progress(job_id, 10, "audio_parser", audio_duration=audio_data.duration)  # Audio parser is 10% of total job
        await publish_event(job_id, "message", {
            "text": "Audio analysis complete!",
            "stage": "audio_parser"
        })
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "completed",
            "duration": audio_data.duration if hasattr(audio_data, 'duration') else (audio_data.beat_timestamps[-1] if audio_data.beat_timestamps else 0)
        })
        await publish_cost_update(job_id, "audio_parser")
        
        # Save audio parser results to database for persistence and testing
        try:
            from api_gateway.services.db_helpers import update_job_stage
            
            # Convert AudioAnalysis to dict for storage
            audio_analysis_dict = {
                "job_id": str(audio_data.job_id),
                "bpm": audio_data.bpm,
                "duration": audio_data.duration,
                "beat_timestamps": audio_data.beat_timestamps,
                "beat_count": len(audio_data.beat_timestamps),
                "beat_subdivisions": audio_data.beat_subdivisions if hasattr(audio_data, 'beat_subdivisions') else {"eighth_notes": [], "sixteenth_notes": []},
                "beat_strength": audio_data.beat_strength if hasattr(audio_data, 'beat_strength') else [],
                "song_structure": [
                    {
                        "type": seg.type,
                        "start": seg.start,
                        "end": seg.end,
                        "energy": seg.energy,
                        "beat_intensity": getattr(seg, 'beat_intensity', None)
                    }
                    for seg in audio_data.song_structure
                ],
                "mood": {
                    "primary": audio_data.mood.primary if hasattr(audio_data.mood, 'primary') else str(audio_data.mood),
                    "secondary": audio_data.mood.secondary if hasattr(audio_data.mood, 'secondary') else None,
                    "energy_level": audio_data.mood.energy_level if hasattr(audio_data.mood, 'energy_level') else None,
                    "confidence": audio_data.mood.confidence if hasattr(audio_data.mood, 'confidence') else None
                },
                "lyrics": [
                    {
                        "text": lyric.text,
                        "timestamp": lyric.timestamp
                    }
                    for lyric in audio_data.lyrics
                ],
                "lyrics_count": len(audio_data.lyrics),
                "clip_boundaries": [
                    {
                        "start": boundary.start,
                        "end": boundary.end,
                        "duration": boundary.duration
                    }
                    for boundary in audio_data.clip_boundaries
                ],
                "clip_boundaries_count": len(audio_data.clip_boundaries),
                "metadata": audio_data.metadata if hasattr(audio_data, 'metadata') and audio_data.metadata else {}
            }
            
            await update_job_stage(
                job_id=job_id,
                stage_name="audio_parser",
                status="completed",
                metadata={"audio_analysis": audio_analysis_dict}
            )
            logger.info("Audio analysis saved to database", extra={"job_id": job_id})
        except Exception as e:
            logger.error("Failed to save audio analysis to database", exc_info=e, extra={"job_id": job_id})
            # Don't fail the pipeline, but log the error
        
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
            "beat_subdivisions": {
                "eighth_notes_count": len(audio_data.beat_subdivisions.get("eighth_notes", [])),
                "sixteenth_notes_count": len(audio_data.beat_subdivisions.get("sixteenth_notes", []))
            },
            "beat_strength": audio_data.beat_strength[:20] if len(audio_data.beat_strength) > 0 else [],  # First 20
            "song_structure": [
                {
                    "type": seg.type,
                    "start": seg.start,
                    "end": seg.end,
                    "energy": seg.energy,
                    "beat_intensity": getattr(seg, 'beat_intensity', None)
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
                "subdivision_count": metadata.get("subdivision_count", 0),
                "downbeat_count": metadata.get("downbeat_count", 0),
                "intensity_distribution": metadata.get("intensity_distribution", {}),
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
        
        # Track stage start time
        try:
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "scene_planner").execute()
            if existing.data and len(existing.data) > 0:
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "scene_planner").execute()
            else:
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "scene_planner",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track scene planner start time", exc_info=e, extra={"job_id": job_id})
        
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
        
        await update_progress(job_id, 20, "scene_planner", audio_duration=audio_data.duration if hasattr(audio_data, 'duration') else None)
        await publish_event(job_id, "stage_update", {
            "stage": "scene_planner",
            "status": "completed"
        })
        await publish_cost_update(job_id, "scene_planner")
        
        # Save scene plan to database for persistence and testing
        # This allows the reference generator to access it even if pipeline restarts
        try:
            from api_gateway.services.db_helpers import update_job_stage
            
            # Convert ScenePlan to dict for storage
            scene_plan_dict = {
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
            }
            
            await update_job_stage(
                job_id=job_id,
                stage_name="scene_planner",
                status="completed",
                metadata={"scene_plan": scene_plan_dict}
            )
            logger.info("Scene plan saved to database", extra={"job_id": job_id})
        except Exception as e:
            logger.error("Failed to save scene plan to database", exc_info=e, extra={"job_id": job_id})
            # Don't fail the pipeline, but log the error
        
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
        
        # Note: If stop_at_stage is not set or is beyond scene_planner, continue to next stage
        
        # Stage 3: Reference Generator (30% progress)
        # Publish stage update BEFORE calling generator so UI shows spinner immediately
        await publish_event(job_id, "stage_update", {
            "stage": "reference_generator",
            "status": "started"
        })
        
        # Track stage start time
        try:
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "reference_generator").execute()
            if existing.data and len(existing.data) > 0:
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "reference_generator").execute()
            else:
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "reference_generator",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track reference generator start time", exc_info=e, extra={"job_id": job_id})
        
        await publish_event(job_id, "message", {
            "text": "Starting reference image generation...",
            "stage": "reference_generator"
        })
        
        # Calculate number of images to generate
        num_images = None
        if plan and hasattr(plan, 'scenes') and hasattr(plan, 'characters'):
            num_images = len(plan.scenes) + len(plan.characters)
        
        # Set initial progress for reference generator stage (25% - start of stage)
        await update_progress(job_id, 25, "reference_generator", num_images=num_images)
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Load scene plan from database if not available in memory (fallback for pipeline restarts)
        if not plan:
            logger.warning(
                f"Scene plan not in memory for job {job_id}, loading from database...",
                extra={"job_id": job_id}
            )
            from api_gateway.services.db_helpers import get_job_stage
            from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition
            
            stage_data = await get_job_stage(job_id, "scene_planner")
            if stage_data and stage_data.get("metadata"):
                metadata = stage_data["metadata"]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                if isinstance(metadata, dict) and "scene_plan" in metadata:
                    scene_plan_data = metadata["scene_plan"]
                    plan = ScenePlan(
                        job_id=UUID(job_id),
                        video_summary=scene_plan_data.get("video_summary", ""),
                        characters=[
                            Character(**char) for char in scene_plan_data.get("characters", [])
                        ],
                        scenes=[
                            Scene(**scene) for scene in scene_plan_data.get("scenes", [])
                        ],
                        style=Style(**scene_plan_data.get("style", {})),
                        clip_scripts=[
                            ClipScript(**clip) for clip in scene_plan_data.get("clip_scripts", [])
                        ],
                        transitions=[
                            Transition(**trans) for trans in scene_plan_data.get("transitions", [])
                        ]
                    )
                    logger.info(
                        f"Scene plan loaded from database for job {job_id}",
                        extra={
                            "job_id": job_id,
                            "scenes_count": len(plan.scenes),
                            "characters_count": len(plan.characters)
                        }
                    )
                else:
                    logger.error(
                        f"Scene plan metadata missing 'scene_plan' key for job {job_id}",
                        extra={"job_id": job_id, "metadata_keys": list(metadata.keys()) if isinstance(metadata, dict) else "not a dict"}
                    )
            else:
                logger.error(
                    f"No scene planner stage data found in database for job {job_id}",
                    extra={"job_id": job_id}
                )
        
        # Budget check removed for reference generator - actual cost is minimal (~$0.01-0.02 for 2-4 images)
        # The check was causing false positives. Budget is still enforced at the job level.
        references = None
        reference_events = []
        try:
            # Validate plan before calling reference generator
            if not plan:
                logger.error(
                    f"Scene plan is None for job {job_id} after attempting to load from database",
                    extra={"job_id": job_id}
                )
                raise PipelineError("Scene plan is None - cannot generate references")
            
            if not plan.scenes or len(plan.scenes) == 0:
                logger.error(
                    f"Scene plan has no scenes for job {job_id}",
                    extra={"job_id": job_id}
                )
                raise PipelineError("Scene plan has no scenes - cannot generate references")
            
            if not plan.characters or len(plan.characters) == 0:
                logger.error(
                    f"Scene plan has no characters for job {job_id}",
                    extra={"job_id": job_id}
                )
                raise PipelineError("Scene plan has no characters - cannot generate references")
            
            logger.info(
                f"Starting reference generator for job {job_id}",
                extra={
                    "job_id": job_id,
                    "plan_has_scenes": len(plan.scenes),
                    "plan_has_characters": len(plan.characters),
                    "scene_ids": [s.id for s in plan.scenes],
                    "character_ids": [c.id for c in plan.characters]
                }
            )
            from modules.reference_generator.process import process as generate_references
            # Convert job_id to UUID and pass duration_seconds for budget checks
            job_id_uuid = UUID(job_id)
            duration_seconds = audio_data.duration if hasattr(audio_data, 'duration') else None
            logger.info(
                f"Calling generate_references for job {job_id}",
                extra={
                    "job_id": job_id,
                    "job_id_uuid": str(job_id_uuid),
                    "duration_seconds": duration_seconds,
                    "scenes_count": len(plan.scenes),
                    "characters_count": len(plan.characters),
                    "total_images_to_generate": len(plan.scenes) + len(plan.characters)
                }
            )
            # Reference generator returns tuple: (Optional[ReferenceImages], List[Dict[str, Any]])
            start_time = time.time()
            references, reference_events = await generate_references(job_id_uuid, plan, duration_seconds)
            elapsed_time = time.time() - start_time
            
            logger.info(
                f"Reference generator returned for job {job_id}",
                extra={
                    "job_id": job_id,
                    "references_is_none": references is None,
                    "events_count": len(reference_events),
                    "has_references": references is not None,
                    "elapsed_seconds": elapsed_time,
                    "scene_refs_count": len(references.scene_references) if references else 0,
                    "character_refs_count": len(references.character_references) if references else 0,
                    "total_refs": references.total_references if references else 0
                }
            )
            
            # Log event types for debugging
            event_types = {}
            for event in reference_events:
                event_type = event.get("event_type", "unknown")
                event_types[event_type] = event_types.get(event_type, 0) + 1
            logger.info(
                f"Reference generator events for job {job_id}",
                extra={"job_id": job_id, "event_types": event_types}
            )
            
            # Track progress as images complete (for more frequent updates)
            reference_progress_tracker = {
                "completed": 0,
                "total": num_images or 4  # Default to 4 if not known yet
            }
            
            # Publish all events from reference generator and track progress
            for event in reference_events:
                event_type = event.get("event_type", "message")
                event_data = event.get("data", {})
                
                # Update progress when images complete
                if event_type == "reference_generation_complete":
                    # Update total if provided in event
                    if "total_images" in event_data:
                        reference_progress_tracker["total"] = max(
                            reference_progress_tracker["total"],
                            event_data["total_images"]
                        )
                    # Update completed count
                    if "completed_images" in event_data:
                        reference_progress_tracker["completed"] = max(
                            reference_progress_tracker["completed"],
                            event_data["completed_images"]
                        )
                    else:
                        reference_progress_tracker["completed"] += 1
                    
                    # Calculate and update progress (25-30% range)
                    progress = calculate_stage_progress(
                        reference_progress_tracker["completed"],
                        reference_progress_tracker["total"],
                        25,  # stage start
                        30   # stage end
                    )
                    await update_progress(
                        job_id,
                        progress,
                        "reference_generator",
                        num_images=reference_progress_tracker["total"]
                    )
                
                # Publish the event
                await publish_event(job_id, event_type, event_data)
            
            if references is None:
                logger.error(
                    "Reference generator returned no references",
                    extra={"job_id": job_id}
                )
                failure_metadata = {"fallback_mode": True, "fallback_reason": "reference_generator_returned_none"}
                try:
                    await db_client.table("job_stages").insert({
                        "job_id": job_id,
                        "stage_name": "reference_generator",
                        "status": "failed",
                        "metadata": json.dumps(failure_metadata)
                    }).execute()
                except Exception as stage_err:
                    logger.warning("Failed to record reference generator failure metadata", exc_info=stage_err)
                raise PipelineError("Reference generator did not produce any references")
            
            # Final progress update (should already be at 30% from incremental updates, but ensure it's set)
            num_images_actual = None
            if references:
                num_images_actual = references.total_references if hasattr(references, 'total_references') else None
            # Only update if we didn't track progress incrementally (fallback)
            if num_images_actual or num_images:
                final_total = num_images_actual or num_images
                # Check if we already updated to 30% via incremental tracking
                # If not, set it now
                await update_progress(job_id, 30, "reference_generator", num_images=final_total)
            
            # Save reference images to database for persistence
            if references:
                try:
                    from api_gateway.services.db_helpers import update_job_stage
                    
                    # Convert ReferenceImages to dict for storage
                    reference_images_dict = {
                        "job_id": str(references.job_id),
                        "scene_references": [
                            {
                                "scene_id": ref.scene_id,
                                "character_id": ref.character_id,
                                "image_url": ref.image_url,
                                "prompt_used": ref.prompt_used,
                                "generation_time": ref.generation_time,
                                "cost": str(ref.cost)
                            }
                            for ref in references.scene_references
                        ],
                        "character_references": [
                            {
                                "scene_id": ref.scene_id,
                                "character_id": ref.character_id,
                                "image_url": ref.image_url,
                                "prompt_used": ref.prompt_used,
                                "generation_time": ref.generation_time,
                                "cost": str(ref.cost)
                            }
                            for ref in references.character_references
                        ],
                        "total_references": references.total_references,
                        "total_generation_time": references.total_generation_time,
                        "total_cost": str(references.total_cost),
                        "status": references.status,
                        "metadata": references.metadata or {}
                    }
                    
                    await update_job_stage(
                        job_id=job_id,
                        stage_name="reference_generator",
                        status="completed",
                        metadata={"reference_images": reference_images_dict}
                    )
                    logger.info("Reference images saved to database", extra={"job_id": job_id})
                except Exception as e:
                    logger.error("Failed to save reference images to database", exc_info=e, extra={"job_id": job_id})
                    # Don't fail the pipeline, but log the error
        except ImportError:
            logger.warning("Reference Generator module not found, using stub", extra={"job_id": job_id})
            # Publish failed event for stub case
            await publish_event(job_id, "stage_update", {
                "stage": "reference_generator",
                "status": "failed"
            })
        except Exception as e:
            # Set fallback flag
            logger.error("Reference Generator failed, setting fallback mode", exc_info=e, extra={"job_id": job_id})
            await db_client.table("job_stages").insert({
                "job_id": job_id,
                "stage_name": "reference_generator",
                "status": "failed",
                "metadata": json.dumps({
                    "fallback_mode": True,
                    "fallback_reason": str(e)
                })
            }).execute()
            # Publish failed event
            await publish_event(job_id, "stage_update", {
                "stage": "reference_generator",
                "status": "failed"
            })
            references = None
        
        # Publish reference generator completion and cost update
        if references is not None:
            await publish_event(job_id, "stage_update", {
                "stage": "reference_generator",
                "status": "completed"
            })
            await publish_cost_update(job_id, "reference_generator")
        
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
        
        # Track stage start time
        try:
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "prompt_generator").execute()
            if existing.data and len(existing.data) > 0:
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "prompt_generator").execute()
            else:
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "prompt_generator",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track prompt generator start time", exc_info=e, extra={"job_id": job_id})
        
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
        
        try:
            llm_used = any(
                getattr(prompt, "metadata", {}).get("llm_used")
                for prompt in clip_prompts.clip_prompts
            )
            llm_model = None
            if llm_used:
                for prompt in clip_prompts.clip_prompts:
                    maybe = (prompt.metadata or {}).get("llm_model")
                    if maybe:
                        llm_model = maybe
                        break
            
            # Convert ClipPrompts to dict for storage
            clip_prompts_dict = {
                "job_id": str(clip_prompts.job_id),
                "total_clips": clip_prompts.total_clips,
                "generation_time": clip_prompts.generation_time,
                "llm_used": llm_used,
                "llm_model": llm_model,
                "clip_prompts": [
                    {
                        "clip_index": prompt.clip_index,
                        "prompt": prompt.prompt,
                        "negative_prompt": prompt.negative_prompt,
                        "duration": prompt.duration,
                        "scene_reference_url": prompt.scene_reference_url,
                        "character_reference_urls": prompt.character_reference_urls,
                        "metadata": prompt.metadata or {},
                    }
                    for prompt in clip_prompts.clip_prompts
                ]
            }
            
            # Save prompt generator results to database for persistence and testing
            try:
                from api_gateway.services.db_helpers import update_job_stage
                
                await update_job_stage(
                    job_id=job_id,
                    stage_name="prompt_generator",
                    status="completed",
                    metadata={"clip_prompts": clip_prompts_dict}
                )
                logger.info("Clip prompts saved to database", extra={"job_id": job_id})
            except Exception as e:
                logger.error("Failed to save clip prompts to database", exc_info=e, extra={"job_id": job_id})
                # Don't fail the pipeline, but log the error
            
            await publish_event(job_id, "prompt_generator_results", clip_prompts_dict)
        except Exception as e:
            logger.error("Failed to publish prompt generator results", exc_info=e, extra={"job_id": job_id})
        
        await update_progress(job_id, 40, "prompt_generator", audio_duration=audio_data.duration if hasattr(audio_data, 'duration') else None)
        await publish_event(job_id, "stage_update", {
            "stage": "prompt_generator",
            "status": "completed"
        })
        await publish_cost_update(job_id, "prompt_generator")
        
        # Check if should stop after prompt generator
        if await should_stop_after_stage("prompt_generator", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "prompt_generator", 40)
            return
        
        # Stage 5: Video Generator (40-85% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "started"
        })
        
        # Track stage start time
        try:
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "video_generator").execute()
            if existing.data and len(existing.data) > 0:
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "video_generator").execute()
            else:
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "video_generator",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track video generator start time", exc_info=e, extra={"job_id": job_id})
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Set initial progress for video generator stage (40% - start of stage)
        num_clips_initial = len(clip_prompts.clip_prompts) if hasattr(clip_prompts, 'clip_prompts') else None
        await update_progress(job_id, 40, "video_generator", num_clips=num_clips_initial)
        
        # Check budget before expensive operation (environment-aware)
        # Estimate video generation cost as ~50% of total budget (most expensive stage)
        duration_minutes = audio_data.duration / 60.0
        total_budget_estimate = get_cost_estimate(duration_minutes, settings.environment)
        video_estimate = Decimal(str(total_budget_estimate * 0.50))  # 50% of total budget
        
        limit = get_budget_limit(settings.environment)
        can_proceed = await cost_tracker.check_budget(
            job_id=UUID(job_id),
            new_cost=video_estimate,
            limit=limit
        )
        if not can_proceed:
            raise BudgetExceededError("Would exceed budget limit before video generation")
        
        try:
            from modules.video_generator.process import process as generate_videos
            
            # Track progress as clips complete (for more frequent updates)
            video_progress_tracker = {
                "completed": 0,
                "total": len(clip_prompts.clip_prompts) if hasattr(clip_prompts, 'clip_prompts') else None,
                "clip_progress": {}  # Track sub-progress for each clip
            }
            
            # Create event publisher callback for real-time progress updates
            async def real_time_event_publisher(event_type: str, event_data: dict) -> None:
                """Publish events immediately and update progress in real-time."""
                try:
                    # Update tracker state
                    if event_type == "video_generation_start":
                        if "total_clips" in event_data:
                            video_progress_tracker["total"] = max(
                                video_progress_tracker["total"] or 0,
                                event_data["total_clips"]
                            )
                    
                    # Handle progress updates in real-time
                    elif event_type == "video_generation_progress":
                        clip_index = event_data.get("clip_index")
                        sub_progress = event_data.get("sub_progress", 0.0)
                        
                        if clip_index is not None and video_progress_tracker["total"]:
                            # Update tracker with latest sub-progress for this clip
                            video_progress_tracker["clip_progress"][clip_index] = sub_progress
                            
                            # Calculate overall progress: average of all active clips + completed clips
                            # Each clip represents ~4.5% of video generator stage (40-85% range, 45% total)
                            clip_progress_range = 45.0 / video_progress_tracker["total"]  # % per clip
                            
                            # Base progress from completed clips (each completed clip = 100% of its range)
                            base_progress = 40 + (video_progress_tracker["completed"] * clip_progress_range)
                            
                            # Add average progress from all active clips (clips currently generating)
                            # When multiple clips are generating in parallel, we average their progress
                            active_clips_average_progress = 0.0
                            if video_progress_tracker["clip_progress"]:
                                # Calculate average progress across all active clips
                                active_clips_average_progress = sum(video_progress_tracker["clip_progress"].values()) / len(video_progress_tracker["clip_progress"])
                            
                            # Calculate total progress: base + active clips contribution
                            # Active clips contribute their average progress * number of active clips * clip_progress_range
                            num_active_clips = len(video_progress_tracker["clip_progress"])
                            active_contribution = active_clips_average_progress * num_active_clips * clip_progress_range
                            current_clip_progress = base_progress + active_contribution
                            
                            # Update overall progress (clamp to stage range)
                            progress = max(40, min(int(current_clip_progress), 85))
                            await update_progress(
                                job_id,
                                progress,
                                "video_generator",
                                num_clips=video_progress_tracker["total"]
                            )
                    
                    # Handle clip completion
                    elif event_type == "video_generation_complete":
                        video_progress_tracker["completed"] += 1
                        clip_index = event_data.get("clip_index")
                        if clip_index is not None:
                            # Remove sub-progress tracking for completed clip
                            video_progress_tracker["clip_progress"].pop(clip_index, None)
                        
                        # Only update progress if we know the total
                        if video_progress_tracker["total"]:
                            progress = calculate_stage_progress(
                                video_progress_tracker["completed"],
                                video_progress_tracker["total"],
                                40,  # stage start (prompt_generator ends at 40%)
                                85   # stage end
                            )
                            await update_progress(
                                job_id,
                                progress,
                                "video_generator",
                                num_clips=video_progress_tracker["total"]
                            )
                    
                    # Publish the event to SSE
                    await publish_event(job_id, event_type, event_data)
                except Exception as e:
                    logger.warning(
                        f"Failed to handle real-time event: {e}",
                        exc_info=e,
                        extra={"job_id": job_id, "event_type": event_type}
                    )
            
            # Pass ScenePlan and event publisher to video generator for real-time updates
            clips, video_events = await generate_videos(job_id, clip_prompts, plan, real_time_event_publisher)
            
            # Publish any remaining events that weren't published in real-time (backward compatibility)
            # Note: Most events are already published in real-time, but we still process the list
            # to ensure all events are published even if real-time publishing failed
            try:
                for event in video_events:
                    event_type = event.get("event_type", "message")
                    event_data = event.get("data", {})
                    
                    # Skip events that are already published in real-time to avoid double-counting
                    # These events are published immediately when they occur, so we don't need to republish them
                    if event_type not in [
                        "video_generation_progress",
                        "video_generation_complete",
                        "video_generation_start",
                        "video_generation_retry",
                        "video_generation_failed"
                    ]:
                        await publish_event(job_id, event_type, event_data)
            except Exception as e:
                logger.warning("Failed to publish some video generation events", exc_info=e, extra={"job_id": job_id})
        except ImportError:
            logger.warning("Video Generator module not found, using stub", extra={"job_id": job_id})
            from shared.models.video import Clips, Clip
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
        
        # Final progress update (should already be at 85% from incremental updates, but ensure it's set)
        num_clips = len(clips.clips) if hasattr(clips, 'clips') else None
        # Only update if we didn't track progress incrementally (fallback)
        if num_clips:
            await update_progress(job_id, 85, "video_generator", num_clips=num_clips)
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "completed"
        })
        await publish_cost_update(job_id, "video_generator")
        
        # Save video clips to database for persistence
        try:
            from api_gateway.services.db_helpers import update_job_stage
            
            # Convert Clips to dict for storage
            clips_dict = {
                "job_id": str(clips.job_id),
                "clips": [
                    {
                        "clip_index": clip.clip_index,
                        "video_url": clip.video_url,
                        "actual_duration": clip.actual_duration,
                        "target_duration": clip.target_duration,
                        "duration_diff": clip.duration_diff,
                        "status": clip.status,
                        "cost": str(clip.cost),
                        "retry_count": clip.retry_count,
                        "generation_time": clip.generation_time
                    }
                    for clip in clips.clips
                ],
                "total_clips": clips.total_clips,
                "successful_clips": clips.successful_clips,
                "failed_clips": clips.failed_clips,
                "total_cost": str(clips.total_cost),
                "total_generation_time": clips.total_generation_time
            }
            
            await update_job_stage(
                job_id=job_id,
                stage_name="video_generator",
                status="completed",
                metadata={"clips": clips_dict}
            )
            logger.info("Video clips saved to database", extra={"job_id": job_id})
        except Exception as e:
            logger.error("Failed to save video clips to database", exc_info=e, extra={"job_id": job_id})
            # Don't fail the pipeline, but log the error
        
        # Check if should stop after video generator
        if await should_stop_after_stage("video_generator", stop_at_stage):
            await stop_pipeline_gracefully(job_id, "video_generator", 85)
            return
        
        # Enforce budget after video generator (costs were tracked)
        await enforce_budget(job_id)
        
        # Stage 6: Composer (85-100% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "composer",
            "status": "started"
        })
        
        # Track stage start time
        try:
            existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", "composer").execute()
            if existing.data and len(existing.data) > 0:
                await db_client.table("job_stages").update({
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).eq("job_id", job_id).eq("stage_name", "composer").execute()
            else:
                await db_client.table("job_stages").insert({
                    "job_id": job_id,
                    "stage_name": "composer",
                    "status": "processing",
                    "started_at": datetime.now().isoformat()
                }).execute()
        except Exception as e:
            logger.warning("Failed to track composer start time", exc_info=e, extra={"job_id": job_id})
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Set initial progress for composer stage (85% - start of stage)
        # Note: Composer will also set this, but we set it here for consistency
        await update_progress(job_id, 85, "composer", audio_duration=audio_data.duration if hasattr(audio_data, 'duration') else None)
        
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
        
        await update_progress(job_id, 100, "composer", audio_duration=audio_data.duration if hasattr(audio_data, 'duration') else None)
        
        # Publish composer completion before completed event
        await publish_event(job_id, "stage_update", {
            "stage": "composer",
            "status": "completed"
        })
        await publish_cost_update(job_id, "composer")
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
