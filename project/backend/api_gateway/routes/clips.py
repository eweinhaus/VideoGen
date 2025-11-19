"""
Clip endpoints.

List clips for a job with thumbnails and metadata.
Regenerate clips based on user instructions.
"""
import json
import uuid
import asyncio
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID
from fastapi import APIRouter, Path, Depends, HTTPException, status, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.database import DatabaseClient
from shared.models.audio import Lyric, ClipBoundary
from shared.logging import get_logger
from shared.errors import ValidationError, GenerationError
from api_gateway.dependencies import get_current_user, verify_job_ownership
from api_gateway.services.event_publisher import publish_event
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clip_prompts_from_job_stages,
    load_audio_data_from_job_stages
)
from modules.clip_regenerator.process import regenerate_clip_with_recomposition
from modules.clip_regenerator.status_manager import acquire_job_lock, update_job_status
from modules.clip_regenerator.cost_tracker import track_regeneration_cost, get_regeneration_history
from modules.clip_regenerator.style_transfer import transfer_style
from modules.clip_regenerator.style_applier import StyleTransferOptions
from modules.clip_regenerator.suggestion_generator import generate_suggestions, Suggestion
from modules.clip_regenerator.instruction_parser import parse_multi_clip_instruction, ClipInstruction
from shared.errors import CompositionError, RetryableError, BudgetExceededError
from shared.cost_tracking import CostTracker
from shared.redis_client import RedisClient
import hashlib
import time

logger = get_logger(__name__)

router = APIRouter()
db_client = DatabaseClient()


def _align_lyrics_to_clip(
    clip_start: float,
    clip_end: float,
    lyrics: List[Lyric],
    is_last_clip: bool = False
) -> Optional[str]:
    """
    Align lyrics to clip boundaries (reuse logic from scene planner).
    
    Uses half-open interval [clip_start, clip_end) for all clips except last.
    Last clip uses inclusive end [clip_start, clip_end].
    
    Args:
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        lyrics: List of lyrics with timestamps
        is_last_clip: If True, use inclusive end boundary
        
    Returns:
        Combined lyrics text or None if no lyrics in range
    """
    if not lyrics:
        return None
    
    # Use half-open interval [start, end) for all clips except the last
    if is_last_clip:
        # Last clip: inclusive end boundary [clip_start, clip_end]
        clip_lyrics = [
            lyric
            for lyric in lyrics
            if clip_start <= lyric.timestamp <= clip_end
        ]
    else:
        # All other clips: half-open interval [clip_start, clip_end)
        clip_lyrics = [
            lyric
            for lyric in lyrics
            if clip_start <= lyric.timestamp < clip_end
        ]
    
    if not clip_lyrics:
        return None
    
    # Build lyrics string from individual words
    words = [lyric.text for lyric in clip_lyrics]
    result = " ".join(words) if words else None
    
    # Truncate to first 2-3 lines (roughly 100-150 characters)
    if result and len(result) > 150:
        # Find last space before 150 chars to avoid cutting words
        truncate_pos = result.rfind(" ", 0, 150)
        if truncate_pos > 0:
            result = result[:truncate_pos] + "..."
        else:
            result = result[:147] + "..."
    
    return result


def _format_timestamp(seconds: float) -> str:
    """
    Format timestamp in seconds to "M:SS" format.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string (e.g., "0:12", "1:30")
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


@router.get("/jobs/{job_id}/clips")
async def get_job_clips(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all clips for a job with thumbnails and metadata.
    
    Args:
        job_id: Job ID
        current_user: Current authenticated user
        
    Returns:
        JSON response with clips array and total_clips count
        
    Raises:
        HTTPException: 404 if job not found, 403 if access denied, 400 if job not completed
    """
    try:
        # Verify job exists and belongs to user
        job_result = await db_client.table("jobs").select("*").eq("id", job_id).execute()
        
        if not job_result.data or len(job_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        job = job_result.data[0]
        
        # Verify ownership
        if job.get("user_id") != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Check job status
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job not completed yet"
            )
        
        # Load clips from job_stages
        clips = await load_clips_from_job_stages(UUID(job_id))
        if not clips:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clips not found (job may not have completed video generation)"
            )
        
        # Load thumbnails from database (gracefully handle missing table)
        thumbnail_map = {}
        try:
            thumbnails_result = await db_client.table("clip_thumbnails").select(
                "clip_index", "thumbnail_url"
            ).eq("job_id", job_id).execute()
            
            thumbnail_map = {
                t["clip_index"]: t["thumbnail_url"]
                for t in thumbnails_result.data
            }
        except Exception as e:
            # Table might not exist yet - log warning and continue without thumbnails
            logger.warning(
                f"Failed to load thumbnails (table may not exist): {e}",
                extra={"job_id": job_id}
            )
            # Continue without thumbnails (not critical for functionality)
        
        # Load lyrics from audio_parser stage
        lyrics: List[Lyric] = []
        clip_boundaries: List[ClipBoundary] = []
        
        try:
            audio_stage_result = await db_client.table("job_stages").select("metadata").eq(
                "job_id", job_id
            ).eq("stage_name", "audio_parser").execute()
            
            if audio_stage_result.data and len(audio_stage_result.data) > 0:
                metadata = audio_stage_result.data[0].get("metadata")
                if metadata:
                    # Handle JSON string or dict
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    
                    # Extract lyrics and clip_boundaries
                    # Check both nested (audio_analysis) and flat structures for backward compatibility
                    lyrics_data = None
                    if "audio_analysis" in metadata and isinstance(metadata["audio_analysis"], dict):
                        # New structure: metadata["audio_analysis"]["lyrics"]
                        audio_analysis = metadata["audio_analysis"]
                        if "lyrics" in audio_analysis:
                            lyrics_data = audio_analysis["lyrics"]
                    elif "lyrics" in metadata:
                        # Old structure: metadata["lyrics"] (backward compatibility)
                        lyrics_data = metadata["lyrics"]
                    
                    if lyrics_data and isinstance(lyrics_data, list):
                        lyrics = [Lyric(**lyric) for lyric in lyrics_data]
                    
                    # Extract clip_boundaries (same pattern)
                    boundaries_data = None
                    if "audio_analysis" in metadata and isinstance(metadata["audio_analysis"], dict):
                        # New structure: metadata["audio_analysis"]["clip_boundaries"]
                        audio_analysis = metadata["audio_analysis"]
                        if "clip_boundaries" in audio_analysis:
                            boundaries_data = audio_analysis["clip_boundaries"]
                    elif "clip_boundaries" in metadata:
                        # Old structure: metadata["clip_boundaries"] (backward compatibility)
                        boundaries_data = metadata["clip_boundaries"]
                    
                    if boundaries_data and isinstance(boundaries_data, list):
                        clip_boundaries = [ClipBoundary(**boundary) for boundary in boundaries_data]
        except Exception as e:
            logger.warning(
                f"Failed to load lyrics from audio_parser stage: {e}",
                extra={"job_id": job_id}
            )
            # Continue without lyrics (not critical)
        
        # Load clip prompts for original_prompt field
        clip_prompts = await load_clip_prompts_from_job_stages(UUID(job_id))
        prompt_map = {}
        if clip_prompts:
            prompt_map = {
                cp.clip_index: cp.prompt
                for cp in clip_prompts.clip_prompts
            }
        
        # Combine data and format response
        clips_response = []
        total_clips = len(clips.clips)
        
        for clip in clips.clips:
            # Get clip boundary for timestamp calculation
            clip_boundary = None
            if clip.clip_index < len(clip_boundaries):
                clip_boundary = clip_boundaries[clip.clip_index]
            
            # Calculate timestamps from clip boundary or use clip duration
            if clip_boundary:
                timestamp_start = clip_boundary.start
                timestamp_end = clip_boundary.end
            else:
                # Fallback: calculate from clip_index and duration
                # This is approximate if boundaries not available
                timestamp_start = sum(
                    c.actual_duration for c in clips.clips[:clip.clip_index]
                )
                timestamp_end = timestamp_start + clip.actual_duration
            
            # Align lyrics to clip
            is_last_clip = (clip.clip_index == total_clips - 1)
            lyrics_preview = _align_lyrics_to_clip(
                timestamp_start,
                timestamp_end,
                lyrics,
                is_last_clip=is_last_clip
            )
            
            # Get original prompt if available
            original_prompt = prompt_map.get(clip.clip_index)
            
            clips_response.append({
                "clip_index": clip.clip_index,
                "thumbnail_url": thumbnail_map.get(clip.clip_index),
                "timestamp_start": timestamp_start,
                "timestamp_end": timestamp_end,
                "lyrics_preview": lyrics_preview,
                "duration": clip.actual_duration,
                "is_regenerated": False,  # Part 1: Always false
                "original_prompt": original_prompt
            })
        
        # Sort by clip_index to ensure correct order
        clips_response.sort(key=lambda x: x["clip_index"])
        
        logger.info(
            f"Returned {len(clips_response)} clips for job {job_id}",
            extra={"job_id": job_id, "total_clips": len(clips_response)}
        )
        
        return {
            "clips": clips_response,
            "total_clips": total_clips
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get clips for job: {e}",
            extra={"job_id": job_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clips"
        )


@router.get("/jobs/{job_id}/clips/{clip_index}/versions/compare")
async def compare_clip_versions(
    job_id: str = Path(...),
    clip_index: int = Path(...),
    original_version: Optional[int] = Query(1, description="Original version number (default: 1)"),
    regenerated_version: Optional[int] = Query(None, description="Regenerated version number (None = current/latest)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Compare two clip versions side-by-side.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to compare
        original_version: Version number for original clip (default: 1)
        regenerated_version: Version number for regenerated clip (None = current/latest)
        current_user: Current authenticated user
        
    Returns:
        JSON response with comparison data (original and regenerated versions)
        
    Raises:
        HTTPException: 404 if versions not found, 403 if access denied
    """
    try:
        from modules.clip_regenerator.data_loader import load_clip_version
        
        # Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # Load original version
        original_data = await load_clip_version(
            UUID(job_id),
            clip_index,
            version_number=original_version
        )
        
        if not original_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original version {original_version} not found for clip {clip_index}"
            )
        
        # Load regenerated version (current or specified version)
        regenerated_data = await load_clip_version(
            UUID(job_id),
            clip_index,
            version_number=regenerated_version
        )
        
        # If regenerated_version not found, try to load current version from clip_versions
        if not regenerated_data and regenerated_version is None:
            try:
                db = DatabaseClient()
                result = await db.table("clip_versions").select("*").eq(
                    "job_id", str(job_id)
                ).eq("clip_index", clip_index).eq("is_current", True).limit(1).execute()
                
                if result.data and len(result.data) > 0:
                    version_data = result.data[0]
                    regenerated_data = {
                        "video_url": version_data.get("video_url"),
                        "thumbnail_url": version_data.get("thumbnail_url"),
                        "prompt": version_data.get("prompt"),
                        "version_number": version_data.get("version_number"),
                        "duration": None,
                        "user_instruction": version_data.get("user_instruction"),
                        "cost": float(version_data.get("cost", 0)) if version_data.get("cost") else None,
                        "created_at": version_data.get("created_at")
                    }
            except Exception:
                pass  # Table may not exist
        
        # If still no regenerated version, use original as both (no regeneration yet)
        if not regenerated_data:
            # No regenerated version exists - return original for both
            regenerated_data = original_data.copy()
            regenerated_data["version_number"] = original_data["version_number"]
        
        # Calculate duration mismatch
        original_duration = original_data.get("duration") or 0
        regenerated_duration = regenerated_data.get("duration") or 0
        duration_mismatch = abs(original_duration - regenerated_duration) > 0.1  # 100ms tolerance
        duration_diff = abs(original_duration - regenerated_duration) if duration_mismatch else 0
        
        # Graceful degradation: if video URLs missing, return thumbnail-only comparison
        if not original_data.get("video_url") or not regenerated_data.get("video_url"):
            logger.warning(
                f"Video URLs missing for comparison, returning thumbnail-only",
                extra={"job_id": job_id, "clip_index": clip_index}
            )
        
        logger.info(
            f"Comparison data loaded successfully",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "original_version": original_data.get("version_number"),
                "regenerated_version": regenerated_data.get("version_number"),
                "duration_mismatch": duration_mismatch
            }
        )
        
        return {
            "original": {
                "video_url": original_data.get("video_url"),
                "thumbnail_url": original_data.get("thumbnail_url"),
                "prompt": original_data.get("prompt"),
                "version_number": original_data.get("version_number"),
                "duration": original_duration,
                "user_instruction": original_data.get("user_instruction"),
                "cost": original_data.get("cost")
            },
            "regenerated": {
                "video_url": regenerated_data.get("video_url"),
                "thumbnail_url": regenerated_data.get("thumbnail_url"),
                "prompt": regenerated_data.get("prompt"),
                "version_number": regenerated_data.get("version_number"),
                "duration": regenerated_duration,
                "user_instruction": regenerated_data.get("user_instruction"),
                "cost": regenerated_data.get("cost")
            },
            "duration_mismatch": duration_mismatch,
            "duration_diff": duration_diff
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to load comparison data: {e}",
            extra={"job_id": job_id, "clip_index": clip_index},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load comparison data"
        )


class RegenerationRequest(BaseModel):
    """Request body for clip regeneration."""
    
    instruction: str
    conversation_history: List[Dict[str, str]] = []


def _create_event_publisher(job_id: str):
    """
    Create event publisher function for regeneration process.
    
    Args:
        job_id: Job ID
        
    Returns:
        Async function that publishes events
    """
    async def publish(event_type: str, data: Dict):
        """Publish regeneration event."""
        await publish_event(job_id, event_type, data)
    
    return publish


@router.post("/jobs/{job_id}/clips/{clip_index}/regenerate")
async def regenerate_clip_endpoint(
    job_id: str = Path(...),
    clip_index: int = Path(...),
    request: RegenerationRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Regenerate a single clip based on user instruction.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to regenerate (0-based)
        request: Regeneration request with instruction and conversation history
        current_user: Current authenticated user
        
    Returns:
        JSON response with regeneration_id, estimated_cost, estimated_time, status, template_matched
        
    Raises:
        HTTPException: 404 if job/clip not found, 403 if access denied, 400 if invalid, 409 if concurrent regeneration
    """
    try:
        logger.info(
            f"Regeneration request received",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "instruction_length": len(request.instruction) if request.instruction else 0,
                "conversation_history_length": len(request.conversation_history) if request.conversation_history else 0,
                "user_id": current_user.get("user_id")
            }
        )
        
        # 1. Verify job ownership (returns job data)
        job = await verify_job_ownership(job_id, current_user)
        logger.debug(
            f"Job ownership verified",
            extra={
                "job_id": job_id,
                "job_status": job.get("status"),
                "job_user_id": job.get("user_id")
            }
        )
        
        # 2. Check job status (must be completed)
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job must be completed before regeneration"
            )
        
        # 3. Concurrent regeneration prevention (database locking)
        try:
            lock_acquired = await acquire_job_lock(UUID(job_id))
            if not lock_acquired:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A regeneration is already in progress for this job. Please wait for it to complete."
                )
        except ValidationError as e:
            # Job not found or invalid status - include full error message
            error_msg = str(e)
            logger.warning(
                f"Validation error during lock acquisition: {error_msg}",
                extra={
                    "job_id": job_id,
                    "clip_index": clip_index,
                    "error_message": error_msg,
                    "error_type": type(e).__name__
                }
            )
            # Ensure the full error message is passed through
            # The error message should already contain detailed diagnostics from status_manager
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg  # Pass through the detailed error message (includes diagnostics)
            )
        except HTTPException:
            raise
        except Exception as e:
            # Log full error details
            error_str = str(e)
            error_type = type(e).__name__
            
            logger.error(
                f"EXCEPTION_DURING_LOCK_ACQUISITION: Failed to acquire lock for regeneration",
                extra={
                    "job_id": job_id,
                    "clip_index": clip_index,
                    "error_type": error_type,
                    "error_message": error_str,
                    "error_args": e.args if hasattr(e, 'args') else None,
                    "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else None,
                    "is_attribute_error": isinstance(e, AttributeError)
                },
                exc_info=True
            )
            
            # Build comprehensive error message
            if isinstance(e, AttributeError):
                # Extract object and method from error message
                error_parts = error_str.split("'")
                obj_name = error_parts[1] if len(error_parts) > 1 else "unknown"
                method_name = error_parts[3] if len(error_parts) > 3 else "unknown"
                
                error_detail = (
                    f"❌ DATABASE CONFIGURATION ERROR ❌\n\n"
                    f"Error: {error_str}\n"
                    f"Object: {obj_name}\n"
                    f"Missing Method: {method_name}\n"
                    f"Error Type: {error_type}\n\n"
                    f"🔧 TROUBLESHOOTING:\n"
                    f"1. Restart the server to load updated code\n"
                    f"2. Check database client version compatibility\n"
                    f"3. Verify shared/database.py is up to date\n"
                    f"4. Check server logs for full error details (search for 'ACQUIRE_LOCK')\n\n"
                    f"If this persists, contact support with this full error message."
                )
            else:
                error_detail = (
                    f"❌ FAILED TO START REGENERATION ❌\n\n"
                    f"Error: {error_str}\n"
                    f"Error Type: {error_type}\n\n"
                    f"Please try again or contact support if this persists.\n"
                    f"Check server logs for details (search for 'EXCEPTION_DURING_LOCK_ACQUISITION')."
                )
            
            # Log the detailed error message separately
            logger.error(f"ERROR_DETAIL_FOR_USER: {error_detail}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail
            )
        
        # 4. Validate clip_index bounds
        logger.debug(
            f"Loading clips from job_stages",
            extra={"job_id": job_id, "clip_index": clip_index}
        )
        clips = await load_clips_from_job_stages(UUID(job_id))
        if not clips:
            logger.error(
                f"Clips not found for job",
                extra={
                    "job_id": job_id,
                    "clip_index": clip_index,
                    "job_status": job.get("status")
                }
            )
            # Restore job status on error
            await update_job_status(UUID(job_id), "completed")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clips not found for this job. The job may not have completed video generation yet, or the clips data is incomplete."
            )
        
        logger.debug(
            f"Clips loaded successfully",
            extra={
                "job_id": job_id,
                "total_clips": clips.total_clips,
                "successful_clips": clips.successful_clips,
                "failed_clips": clips.failed_clips,
                "requested_clip_index": clip_index,
                "available_clip_indices": [c.clip_index for c in clips.clips]
            }
        )
        
        # Check if the specific clip_index exists in the loaded clips
        # (Note: clip indices may not be sequential if some clips were filtered out)
        clip_exists = any(c.clip_index == clip_index for c in clips.clips)
        if not clip_exists:
            available_indices = [c.clip_index for c in clips.clips]
            # Restore job status on error
            await update_job_status(UUID(job_id), "completed")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clip with index {clip_index} not found. Available clip indices: {available_indices if available_indices else 'none'}. The requested clip may be incomplete or not yet generated."
            )
        
        # 5. Validate instruction
        if not request.instruction or not request.instruction.strip():
            # Restore job status on error
            await update_job_status(UUID(job_id), "completed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instruction cannot be empty"
            )
        
        # 6. Budget enforcement (check before starting regeneration)
        try:
            cost_tracker = CostTracker()
            # Estimate regeneration cost (LLM + video generation)
            # Rough estimate: $0.10 for LLM + $0.05 for video = $0.15 per regeneration
            estimated_cost = Decimal("0.15")
            budget_limit = Decimal("2000.00")  # Default budget limit
            
            budget_ok = await cost_tracker.check_budget(
                job_id=UUID(job_id),
                new_cost=estimated_cost,
                limit=budget_limit
            )
            
            if not budget_ok:
                # Restore job status on budget exceeded
                await update_job_status(UUID(job_id), "completed")
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Budget limit exceeded. Estimated cost: ${estimated_cost}, limit: ${budget_limit}"
                )
        except BudgetExceededError as e:
            # Restore job status on budget exceeded
            await update_job_status(UUID(job_id), "completed")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=str(e)
            )
        except Exception as e:
            # Don't block regeneration if budget check fails (log and continue)
            logger.warning(
                f"Budget check failed: {e}, proceeding anyway",
                extra={"job_id": job_id}
            )
        
        # 7. Create event publisher wrapper
        event_pub = _create_event_publisher(job_id)
        
        # 8. Call regeneration process with recomposition (async)
        # Get original prompt for cost tracking (in case of failure)
        logger.debug(
            f"Loading clip prompts for cost tracking",
            extra={"job_id": job_id, "clip_index": clip_index}
        )
        clip_prompts = await load_clip_prompts_from_job_stages(UUID(job_id))
        original_prompt = clip_prompts.clip_prompts[clip_index].prompt if clip_prompts and clip_index < len(clip_prompts.clip_prompts) else ""
        
        logger.info(
            f"Starting regeneration process",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "instruction": request.instruction.strip(),
                "has_original_prompt": bool(original_prompt),
                "original_prompt_length": len(original_prompt) if original_prompt else 0,
                "total_clips": clips.total_clips,
                "total_prompts": len(clip_prompts.clip_prompts) if clip_prompts else 0
            }
        )
        
        # Extract user_id for analytics tracking
        user_id = UUID(current_user["user_id"]) if current_user.get("user_id") else None
        
        # Generate regeneration ID
        regeneration_id = str(uuid.uuid4())
        
        # Start regeneration in background task to avoid HTTP timeout
        # The regeneration can take several minutes (video generation alone can take 240s)
        async def background_regeneration():
            """Background task to run regeneration without blocking HTTP response."""
            try:
                result = await regenerate_clip_with_recomposition(
                    job_id=UUID(job_id),
                    clip_index=clip_index,
                    user_instruction=request.instruction.strip(),
                    user_id=user_id,
                    conversation_history=request.conversation_history,
                    event_publisher=event_pub
                )
                
                # Status is already updated to "completed" by regenerate_clip_with_recomposition
                logger.info(
                    f"Clip regeneration with recomposition completed successfully",
                    extra={
                        "job_id": job_id,
                        "clip_index": clip_index,
                        "template_used": result.template_used,
                        "cost": str(result.cost),
                        "video_url": result.video_output.video_url if result.video_output else None
                    }
                )
                
                # Publish completion event
                await event_pub("regeneration_completed", {
                    "regeneration_id": regeneration_id,
                    "status": "completed",
                    "template_matched": result.template_used,
                    "video_url": result.video_output.video_url if result.video_output else None,
                    "cost": float(result.cost)
                })
                
            except ValidationError as e:
                # Restore job status on validation error
                await update_job_status(UUID(job_id), "completed")
                logger.warning(
                    f"Validation error during regeneration: {e}",
                    extra={"job_id": job_id, "clip_index": clip_index}
                )
                await event_pub("regeneration_failed", {
                    "regeneration_id": regeneration_id,
                    "error": str(e),
                    "error_type": "validation"
                })
            except GenerationError as e:
                # Restore job status on generation error
                await update_job_status(UUID(job_id), "completed")
                logger.error(
                    f"Generation error during regeneration: {e}",
                    extra={"job_id": job_id, "clip_index": clip_index},
                    exc_info=True
                )
                await event_pub("regeneration_failed", {
                    "regeneration_id": regeneration_id,
                    "error": str(e),
                    "error_type": "generation"
                })
            except Exception as e:
                # Restore job status on unexpected error
                await update_job_status(UUID(job_id), "completed")
                logger.error(
                    f"Unexpected error during regeneration: {e}",
                    extra={"job_id": job_id, "clip_index": clip_index},
                    exc_info=True
                )
                await event_pub("regeneration_failed", {
                    "regeneration_id": regeneration_id,
                    "error": str(e),
                    "error_type": "unexpected"
                })
        
        # Start background task
        asyncio.create_task(background_regeneration())
        
        # Return immediately with 202 Accepted status
        # Client should listen to SSE stream for progress updates
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "regeneration_id": regeneration_id,
                "status": "processing",
                "message": "Regeneration started. Listen to SSE stream for progress updates.",
                "estimated_time": 240,  # ~4 minutes for clip regeneration + recomposition
                "stream_url": f"/api/v1/jobs/{job_id}/stream"
            }
        )
    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(
            f"Validation error during regeneration: {e}",
            extra={"job_id": job_id, "clip_index": clip_index},
            exc_info=True
        )
        # Try to restore job status if it was changed
        try:
            await update_job_status(UUID(job_id), "completed")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}"
        )
    except GenerationError as e:
        logger.error(
            f"Generation error during regeneration: {e}",
            extra={"job_id": job_id, "clip_index": clip_index},
            exc_info=True
        )
        # Try to restore job status if it was changed
        try:
            await update_job_status(UUID(job_id), "completed")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video generation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during regeneration: {e}",
            extra={"job_id": job_id, "clip_index": clip_index, "error_type": type(e).__name__},
            exc_info=True
        )
        # Try to restore job status if it was changed
        try:
            await update_job_status(UUID(job_id), "completed")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Regeneration failed: {str(e)}. Error type: {type(e).__name__}"
        )


class StyleTransferRequest(BaseModel):
    """Request body for style transfer."""
    
    source_clip_index: int
    target_clip_index: int
    transfer_options: StyleTransferOptions
    additional_instruction: Optional[str] = None


@router.post("/jobs/{job_id}/clips/style-transfer")
async def style_transfer_endpoint(
    job_id: str = Path(...),
    request: StyleTransferRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Transfer style from source clip to target clip and regenerate.
    
    Args:
        job_id: Job ID
        request: Style transfer request with source/target indices and options
        current_user: Current authenticated user
        
    Returns:
        JSON response with regeneration_id, estimated_cost, status
        
    Raises:
        HTTPException: 404 if job/clip not found, 403 if access denied, 400 if invalid, 409 if concurrent regeneration
    """
    try:
        logger.info(
            f"Style transfer request received",
            extra={
                "job_id": job_id,
                "source_clip_index": request.source_clip_index,
                "target_clip_index": request.target_clip_index,
                "user_id": current_user.get("user_id")
            }
        )
        
        # 1. Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # 2. Check job status (must be completed)
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job must be completed before style transfer"
            )
        
        # 3. Concurrent regeneration prevention
        try:
            lock_acquired = await acquire_job_lock(UUID(job_id))
            if not lock_acquired:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A regeneration is already in progress for this job. Please wait for it to complete."
                )
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        # 4. Validate clip indices
        clips = await load_clips_from_job_stages(UUID(job_id))
        if not clips:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clips not found for job {job_id}"
            )
        
        total_clips = len(clips.clips)
        if request.source_clip_index < 0 or request.source_clip_index >= total_clips:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source_clip_index: {request.source_clip_index}. Valid range: 0-{total_clips - 1}"
            )
        
        if request.target_clip_index < 0 or request.target_clip_index >= total_clips:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid target_clip_index: {request.target_clip_index}. Valid range: 0-{total_clips - 1}"
            )
        
        if request.source_clip_index == request.target_clip_index:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and target clip indices must be different"
            )
        
        # 5. Transfer style and get modified prompt
        modified_prompt = await transfer_style(
            job_id=UUID(job_id),
            source_clip_index=request.source_clip_index,
            target_clip_index=request.target_clip_index,
            transfer_options=request.transfer_options,
            additional_instruction=request.additional_instruction
        )
        
        # 6. Publish style transfer events
        event_pub = _create_event_publisher(job_id)
        await event_pub("style_transfer_started", {
            "sequence": 1,
            "source_clip_index": request.source_clip_index,
            "target_clip_index": request.target_clip_index
        })
        
        await event_pub("style_transfer_complete", {
            "sequence": 2,
            "target_clip_index": request.target_clip_index,
            "modified_prompt_length": len(modified_prompt)
        })
        
        # 7. Regenerate target clip with modified prompt
        # Use the modified prompt as the instruction
        user_id = UUID(current_user["user_id"]) if current_user.get("user_id") else None
        result = await regenerate_clip_with_recomposition(
            job_id=UUID(job_id),
            clip_index=request.target_clip_index,
            user_instruction=modified_prompt,
            user_id=user_id,
            conversation_history=[],
            event_publisher=event_pub
        )
        
        # 8. Calculate estimated cost (style transfer + regeneration)
        estimated_cost = result.cost
        
        logger.info(
            f"Style transfer completed successfully",
            extra={
                "job_id": job_id,
                "source_clip_index": request.source_clip_index,
                "target_clip_index": request.target_clip_index,
                "cost": str(estimated_cost)
            }
        )
        
        return {
            "regeneration_id": str(uuid.uuid4()),
            "estimated_cost": float(estimated_cost),
            "status": "completed"
        }
        
    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(
            f"Validation error during style transfer: {e}",
            extra={"job_id": job_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during style transfer: {e}",
            extra={"job_id": job_id, "error_type": type(e).__name__},
            exc_info=True
        )
        # Try to restore job status
        try:
            await update_job_status(UUID(job_id), "completed")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Style transfer failed: {str(e)}"
        )


async def _check_suggestions_rate_limit(job_id: str) -> None:
    """
    Check suggestions rate limit (10 requests per job per hour).
    
    Args:
        job_id: Job ID to check rate limit for
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    RATE_LIMIT = 10  # requests per job per hour
    redis_client = RedisClient()
    
    key = f"suggestions_rate_limit:{job_id}"
    now = int(time.time())
    one_hour_ago = now - 3600
    
    try:
        # Remove entries older than 1 hour
        await redis_client.client.zremrangebyscore(key, 0, one_hour_ago)
        
        # Count entries in last hour
        count = await redis_client.client.zcard(key)
        
        if count >= RATE_LIMIT:
            # Calculate Retry-After
            oldest_entries = await redis_client.client.zrange(key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_time = int(oldest_entries[0][1])
                retry_after = int(3600 - (now - oldest_time))
            else:
                retry_after = 3600
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Suggestions rate limit exceeded: {RATE_LIMIT} requests per job per hour",
                headers={"Retry-After": str(retry_after)}
            )
        
        # Add current timestamp
        await redis_client.client.zadd(key, {str(now): now})
        await redis_client.client.expire(key, 3600)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(
            f"Suggestions rate limit check failed, allowing request",
            extra={"job_id": job_id, "error": str(e)}
        )
        # Fail-open: allow request if rate limiter fails


def _get_suggestions_cache_key(job_id: str, clip_index: int, context_hash: str) -> str:
    """Generate cache key for suggestions."""
    return f"suggestions:{job_id}:{clip_index}:{context_hash}"


def _hash_suggestions_context(clip_prompt: str, other_clips: List[str], audio_context: Dict) -> str:
    """Generate hash for suggestions context."""
    context_str = f"{clip_prompt}|{','.join(other_clips)}|{audio_context.get('beat_intensity', '')}|{audio_context.get('mood', '')}"
    return hashlib.md5(context_str.encode()).hexdigest()


@router.get("/jobs/{job_id}/clips/{clip_index}/suggestions")
async def get_suggestions_endpoint(
    job_id: str = Path(...),
    clip_index: int = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Get AI suggestions for a clip.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to get suggestions for
        current_user: Current authenticated user
        
    Returns:
        JSON response with suggestions list and cached flag
        
    Raises:
        HTTPException: 404 if job/clip not found, 403 if access denied, 429 if rate limit exceeded
    """
    try:
        logger.info(
            f"Suggestions request received",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "user_id": current_user.get("user_id")
            }
        )
        
        # 1. Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # 2. Check rate limit
        await _check_suggestions_rate_limit(job_id)
        
        # 3. Load clip data to build context hash
        clip_prompts = await load_clip_prompts_from_job_stages(UUID(job_id))
        if not clip_prompts or clip_index >= len(clip_prompts.clip_prompts):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clip {clip_index} not found for job {job_id}"
            )
        
        clip_prompt = clip_prompts.clip_prompts[clip_index].prompt
        other_clips = [
            cp.prompt for cp in clip_prompts.clip_prompts 
            if cp.clip_index != clip_index
        ][:5]
        
        audio_data = await load_audio_data_from_job_stages(UUID(job_id))
        audio_context = {}
        if audio_data:
            beat_intensity = "medium"
            if audio_data.song_structure and clip_index < len(audio_data.song_structure):
                segment = audio_data.song_structure[clip_index]
                beat_intensity = getattr(segment, "beat_intensity", "medium")
            audio_context = {
                "beat_intensity": beat_intensity,
                "mood": audio_data.mood.primary if audio_data.mood else "neutral"
            }
        
        # 4. Check cache
        context_hash = _hash_suggestions_context(clip_prompt, other_clips, audio_context)
        cache_key = _get_suggestions_cache_key(job_id, clip_index, context_hash)
        
        redis_client = RedisClient()
        cached_suggestions = await redis_client.get_json(cache_key)
        
        if cached_suggestions:
            logger.debug(
                f"Returning cached suggestions",
                extra={"job_id": job_id, "clip_index": clip_index}
            )
            return {
                "suggestions": cached_suggestions,
                "cached": True
            }
        
        # 5. Generate suggestions
        suggestions = await generate_suggestions(UUID(job_id), clip_index)
        
        # 6. Cache suggestions (5 minutes TTL)
        suggestions_dict = [s.model_dump() for s in suggestions]
        await redis_client.set_json(cache_key, suggestions_dict, ttl=300)
        
        logger.info(
            f"Generated and cached {len(suggestions)} suggestions",
            extra={"job_id": job_id, "clip_index": clip_index}
        )
        
        return {
            "suggestions": suggestions_dict,
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get suggestions: {e}",
            extra={"job_id": job_id, "clip_index": clip_index},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestions: {str(e)}"
        )


@router.post("/jobs/{job_id}/clips/{clip_index}/suggestions/{suggestion_id}/apply")
async def apply_suggestion_endpoint(
    job_id: str = Path(...),
    clip_index: int = Path(...),
    suggestion_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Apply a suggestion to regenerate a clip.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to regenerate
        suggestion_id: Suggestion ID (context hash)
        current_user: Current authenticated user
        
    Returns:
        JSON response with regeneration_id and status
        
    Raises:
        HTTPException: 404 if job/clip/suggestion not found, 403 if access denied
    """
    try:
        logger.info(
            f"Apply suggestion request received",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "suggestion_id": suggestion_id,
                "user_id": current_user.get("user_id")
            }
        )
        
        # 1. Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # 2. Load suggestion from cache
        # Try to find suggestion in cache (we need to search by context hash)
        # For simplicity, regenerate suggestions and find matching one
        # In production, we'd store suggestion_id -> example_instruction mapping
        suggestions = await generate_suggestions(UUID(job_id), clip_index)
        
        # Find suggestion by index (suggestion_id could be index or hash)
        try:
            suggestion_index = int(suggestion_id)
            if suggestion_index < 0 or suggestion_index >= len(suggestions):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Suggestion {suggestion_id} not found"
                )
            suggestion = suggestions[suggestion_index]
        except ValueError:
            # suggestion_id is not an index, search by hash or return first
            suggestion = suggestions[0] if suggestions else None
            if not suggestion:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No suggestions available"
                )
        
        # 3. Regenerate clip with suggestion's example_instruction
        event_pub = _create_event_publisher(job_id)
        user_id = UUID(current_user["user_id"]) if current_user.get("user_id") else None
        result = await regenerate_clip_with_recomposition(
            job_id=UUID(job_id),
            clip_index=clip_index,
            user_instruction=suggestion.example_instruction,
            user_id=user_id,
            conversation_history=[],
            event_publisher=event_pub
        )
        
        logger.info(
            f"Suggestion applied successfully",
            extra={
                "job_id": job_id,
                "clip_index": clip_index,
                "suggestion_type": suggestion.type
            }
        )
        
        return {
            "regeneration_id": str(uuid.uuid4()),
            "status": "completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to apply suggestion: {e}",
            extra={"job_id": job_id, "clip_index": clip_index},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply suggestion: {str(e)}"
        )


class MultiClipInstructionRequest(BaseModel):
    """Request body for multi-clip instruction."""
    
    instruction: str


@router.post("/jobs/{job_id}/clips/multi-clip-instruction")
async def multi_clip_instruction_endpoint(
    job_id: str = Path(...),
    request: MultiClipInstructionRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Parse multi-clip instruction and return preview.
    
    This endpoint parses the instruction and returns which clips will be modified.
    The actual regeneration should be done via batch-regenerate endpoint (Part 4)
    or individual regenerate endpoints.
    
    Args:
        job_id: Job ID
        request: Multi-clip instruction request
        current_user: Current authenticated user
        
    Returns:
        JSON response with target clips, per-clip instructions, and estimated cost
        
    Raises:
        HTTPException: 404 if job not found, 403 if access denied, 400 if invalid
    """
    try:
        logger.info(
            f"Multi-clip instruction request received",
            extra={
                "job_id": job_id,
                "instruction": request.instruction[:100],
                "user_id": current_user.get("user_id")
            }
        )
        
        # 1. Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # 2. Load clips to get total_clips
        clips = await load_clips_from_job_stages(UUID(job_id))
        if not clips:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clips not found for job {job_id}"
            )
        
        total_clips = len(clips.clips)
        
        # 3. Load audio data (optional, for audio context)
        audio_data = await load_audio_data_from_job_stages(UUID(job_id))
        
        # 4. Parse instruction
        clip_instructions = parse_multi_clip_instruction(
            instruction=request.instruction,
            total_clips=total_clips,
            audio_data=audio_data
        )
        
        if not clip_instructions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No clips matched the instruction"
            )
        
        # 5. Calculate estimated cost
        # Use average cost per clip (rough estimate)
        from modules.video_generator.cost_estimator import estimate_clip_cost
        from shared.config import settings
        
        estimated_cost = Decimal("0.00")
        per_clip_costs = []
        
        for clip_instruction in clip_instructions:
            # Get clip duration for cost estimation
            clip = clips.clips[clip_instruction.clip_index]
            clip_cost = estimate_clip_cost(clip.target_duration, settings.environment)
            estimated_cost += clip_cost
            per_clip_costs.append({
                "clip_index": clip_instruction.clip_index,
                "cost": float(clip_cost)
            })
        
        # Apply batch discount if 3+ clips
        if len(clip_instructions) >= 3:
            estimated_cost = estimated_cost * Decimal("0.9")
        
        logger.info(
            f"Multi-clip instruction parsed",
            extra={
                "job_id": job_id,
                "target_clips_count": len(clip_instructions),
                "estimated_cost": str(estimated_cost)
            }
        )
        
        return {
            "target_clips": [ci.clip_index for ci in clip_instructions],
            "per_clip_instructions": [
                {
                    "clip_index": ci.clip_index,
                    "instruction": ci.instruction
                }
                for ci in clip_instructions
            ],
            "estimated_cost": float(estimated_cost),
            "per_clip_costs": per_clip_costs,
            "batch_discount_applied": len(clip_instructions) >= 3
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to parse multi-clip instruction: {e}",
            extra={"job_id": job_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse instruction: {str(e)}"
        )

