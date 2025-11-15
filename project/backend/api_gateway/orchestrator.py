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
    RetryableError
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


async def execute_pipeline(job_id: str, audio_url: str, user_prompt: str) -> None:
    """
    Execute the video generation pipeline (modules 3-8).
    
    Args:
        job_id: Job ID
        audio_url: URL of uploaded audio file
        user_prompt: User's creative prompt
    """
    try:
        # Update job status to processing
        await db_client.table("jobs").update({
            "status": "processing",
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        # Stage 1: Audio Parser (10% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        try:
            from modules.audio_parser.main import process_audio_analysis
            
            # Convert job_id from str to UUID (audio parser expects UUID)
            job_uuid = UUID(job_id)
            audio_data = await process_audio_analysis(job_uuid, audio_url)
            
            # Store in database (jobs.audio_data JSONB column)
            # Use model_dump(mode='json') to serialize UUIDs to strings for JSON compatibility
            # Also ensure all UUIDs are converted to strings
            audio_data_dict = audio_data.model_dump(mode='json')
            # Double-check: convert job_id UUID to string if not already
            if isinstance(audio_data_dict.get('job_id'), UUID):
                audio_data_dict['job_id'] = str(audio_data_dict['job_id'])
            
            await db_client.table("jobs").update({
                "audio_data": audio_data_dict,
                "updated_at": "now()"
            }).eq("id", job_id).execute()
            
            await update_progress(job_id, 10, "audio_parser")
            await publish_event(job_id, "stage_update", {
                "stage": "audio_parser",
                "status": "completed"
            })
            
            # Send audio parser results to frontend (ALWAYS send, even if pipeline fails later)
            # This ensures frontend gets the data even if budget check fails
            try:
                logger.info(f"Publishing audio_parser_results event for job {job_id}", extra={"job_id": job_id})
                await publish_event(job_id, "audio_parser_results", {
                    "bpm": audio_data.bpm,
                    "duration": audio_data.duration,
                    "beat_timestamps": audio_data.beat_timestamps,
                    "beat_count": len(audio_data.beat_timestamps),
                    "song_structure": [
                        {
                            "type": seg.type.value if hasattr(seg.type, 'value') else str(seg.type),
                            "start": seg.start,
                            "end": seg.end,
                            "energy": seg.energy.value if hasattr(seg.energy, 'value') else str(seg.energy)
                        }
                        for seg in audio_data.song_structure
                    ],
                    "mood": {
                        "primary": audio_data.mood.primary,
                        "secondary": audio_data.mood.secondary,
                        "energy_level": audio_data.mood.energy_level.value if hasattr(audio_data.mood.energy_level, 'value') else str(audio_data.mood.energy_level),
                        "confidence": audio_data.mood.confidence
                    },
                    "lyrics_count": len(audio_data.lyrics),
                    "clip_boundaries_count": len(audio_data.clip_boundaries),
                    "metadata": audio_data.metadata
                })
                logger.info(f"✅ Successfully published audio_parser_results event for job {job_id}", extra={"job_id": job_id})
            except Exception as event_error:
                # Don't fail the pipeline if event publishing fails
                logger.error(f"Failed to publish audio_parser_results event: {str(event_error)}", exc_info=event_error, extra={"job_id": job_id})
        except Exception as e:
            await handle_pipeline_error(job_id, e)
            raise
        
        # Stage 2: Scene Planner (20% progress) - DISABLED FOR NOW
        await publish_event(job_id, "stage_update", {
            "stage": "scene_planner",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        try:
            from modules.scene_planner.process import process as plan_scene
            plan = await plan_scene(job_id, user_prompt, audio_data)
        except ImportError:
            logger.warning("Scene Planner module not found, using stub", extra={"job_id": job_id})
            from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition
            plan = ScenePlan(
                job_id=job_id,
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
                    mood="energetic",
                    lighting="bright",
                    cinematography="dynamic"
                ),
                clip_scripts=[
                    ClipScript(
                        clip_index=0,
                        start=0.0,
                        end=5.0,
                        visual_description="Opening scene",
                        motion="slow pan",
                        camera_angle="wide",
                        characters=["char1"],
                        scenes=["scene1"],
                        lyrics_context=None,
                        beat_intensity="medium"
                    )
                ],
                transitions=[
                    Transition(from_clip=0, to_clip=1, type="cut", duration=0.0, rationale="Natural transition")
                ]
            )
        
        await update_progress(job_id, 20, "scene_planner")
        await publish_event(job_id, "stage_update", {
            "stage": "scene_planner",
            "status": "completed"
        })
        
        # Stage 3: Reference Generator (30% progress) - with fallback
        await publish_event(job_id, "stage_update", {
            "stage": "reference_generator",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Check budget before expensive operation (environment-aware)
        # Reference generation: 2-4 images at ~$0.005 each = $0.01-0.02
        # Use $0.10 estimate to be safe (10x buffer for retries/failures)
        limit = get_budget_limit(settings.environment)
        # Environment-aware estimate: lower in development
        if settings.environment in ["production", "staging"]:
            ref_gen_estimate = Decimal("0.10")  # $0.10 for production (safe buffer)
        else:
            ref_gen_estimate = Decimal("0.10")  # $0.10 for development (still safe, but realistic)
        
        # Get current cost to provide better error message
        current_cost = await cost_tracker.get_total_cost(UUID(job_id))
        projected_cost = current_cost + ref_gen_estimate
        
        can_proceed = await cost_tracker.check_budget(
            job_id=UUID(job_id),
            new_cost=ref_gen_estimate,
            limit=limit
        )
        if not can_proceed:
            raise BudgetExceededError(
                f"Would exceed budget limit before reference generation: "
                f"current cost=${current_cost:.2f}, estimated=${ref_gen_estimate:.2f}, "
                f"projected=${projected_cost:.2f}, limit=${limit:.2f}"
            )
        
        references = None
        try:
            from modules.reference_generator.process import process as generate_references
            references = await generate_references(job_id, plan)
        except ImportError:
            logger.warning("Reference Generator module not found, using stub", extra={"job_id": job_id})
        except Exception as e:
            # Set fallback flag
            logger.warning("Reference Generator failed, setting fallback mode", exc_info=e, extra={"job_id": job_id})
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
        await publish_event(job_id, "stage_update", {
            "stage": "reference_generator",
            "status": "completed"
        })
        
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
            
            # Create stub prompts based on clip boundaries from audio analysis
            # Use clip boundaries to create prompts with proper durations
            stub_prompts = []
            for idx, boundary in enumerate(audio_data.clip_boundaries):
                # Use duration from boundary (required field)
                clip_duration = boundary.duration
                stub_prompts.append(ClipPrompt(
                    clip_index=idx,
                    prompt=f"A scene matching the audio mood: {audio_data.mood.primary}",
                    negative_prompt="blurry, low quality, distorted, watermark, text overlay",
                    duration=clip_duration
                ))
            
            # If no clip boundaries, create at least one prompt
            if not stub_prompts:
                stub_prompts.append(ClipPrompt(
                    clip_index=0,
                    prompt=f"A scene matching the audio mood: {audio_data.mood.primary}",
                    negative_prompt="blurry, low quality, distorted, watermark, text overlay",
                    duration=5.0  # Default 5 seconds
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
        
        # Stage 5: Video Generator (85% progress)
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "started"
        })
        
        if await check_cancellation(job_id):
            await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
            return
        
        # Check budget before expensive operation (environment-aware)
        # Video generation: ~6 clips × $0.10 = $0.60 typical, use $1.00 estimate for safety
        limit = get_budget_limit(settings.environment)
        # Environment-aware estimate: lower in development
        if settings.environment in ["production", "staging"]:
            video_gen_estimate = Decimal("1.00")  # $1.00 for production (safe buffer)
        else:
            video_gen_estimate = Decimal("1.00")  # $1.00 for development (realistic)
        
        can_proceed = await cost_tracker.check_budget(
            job_id=UUID(job_id),
            new_cost=video_gen_estimate,
            limit=limit
        )
        if not can_proceed:
            raise BudgetExceededError(f"Would exceed budget limit before video generation (estimated cost: ${video_gen_estimate}, limit: ${limit})")
        
        try:
            from modules.video_generator.process import process as generate_videos
            clips = await generate_videos(job_id, clip_prompts)
        except ImportError:
            logger.warning("Video Generator module not found, using stub", extra={"job_id": job_id})
            from shared.models.video import Clips, Clip
            
            # Create stub clips based on clip_prompts
            stub_clips = []
            for prompt in clip_prompts.clip_prompts:
                target_duration = prompt.duration
                # Stub: assume actual duration matches target (perfect generation)
                actual_duration = target_duration
                duration_diff = 0.0
                
                stub_clips.append(Clip(
                    clip_index=prompt.clip_index,
                    video_url=f"stub_video_url_{prompt.clip_index}.mp4",
                    actual_duration=actual_duration,
                    target_duration=target_duration,
                    duration_diff=duration_diff,
                    status="success",
                    cost=Decimal("0.10"),  # Stub cost per clip
                    retry_count=0,
                    generation_time=2.0  # Stub generation time
                ))
            
            # Create Clips collection with all required fields
            clips = Clips(
                job_id=UUID(job_id),
                clips=stub_clips,
                total_clips=len(stub_clips),
                successful_clips=len(stub_clips),
                failed_clips=0,
                total_cost=Decimal(str(len(stub_clips) * 0.10)),  # Total cost for all clips
                total_generation_time=len(stub_clips) * 2.0  # Total generation time
            )
        
        # Validate minimum clips
        if len(clips.clips) < 3:
            raise PipelineError("Insufficient clips generated (minimum 3 required)")
        
        await update_progress(job_id, 85, "video_generator")
        await publish_event(job_id, "stage_update", {
            "stage": "video_generator",
            "status": "completed"
        })
        
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
        beat_timestamps = []  # Audio parser removed - will be rebuilt
        
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
            video_output = VideoOutput(video_url="stub_final_video_url", duration=120.0)
        
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
