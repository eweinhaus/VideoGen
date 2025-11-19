"""
Job endpoints.

Job status, list, and cancellation.
"""

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Path, Query, Depends, HTTPException, status
from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.errors import ValidationError
from shared.logging import get_logger
from api_gateway.dependencies import get_current_user, verify_job_ownership
from api_gateway.services.queue_service import remove_job

logger = get_logger(__name__)

router = APIRouter()
db_client = DatabaseClient()
redis_client = RedisClient()


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Get job status (polling fallback, SSE preferred).
    
    Args:
        job_id: Job ID
        current_user: Current authenticated user
        
    Returns:
        Job status with all fields
    """
    # Check Redis cache first (30s TTL) - before any database queries
    cache_key = f"job_status:{job_id}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            cached_data = json.loads(cached)
            # Verify ownership from cached data (quick check)
            if cached_data.get("user_id") == current_user["user_id"]:
                # If cached data doesn't have stages or stages don't have metadata, fetch them (for backward compatibility with old cache)
                if "stages" not in cached_data or not any(s.get("metadata") for s in cached_data.get("stages", {}).values()):
                    try:
                        stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).execute()
                        stages = {}
                        if stages_result.data:
                            for stage in stages_result.data:
                                stage_name = stage.get("stage_name")
                                if stage_name:
                                    stage_info = {
                                        "status": stage.get("status", "pending"),
                                        "duration": stage.get("duration_seconds"),
                                        "progress": None,
                                    }
                                    # Include metadata if available
                                    metadata = stage.get("metadata")
                                    if metadata:
                                        try:
                                            if isinstance(metadata, str):
                                                metadata = json.loads(metadata)
                                            stage_info["metadata"] = metadata
                                        except (json.JSONDecodeError, TypeError):
                                            pass
                                    stages[stage_name] = stage_info
                        cached_data["stages"] = stages
                        # Update cache with stages included
                        await redis_client.set(cache_key, json.dumps(cached_data), ex=30)
                    except Exception as e:
                        logger.warning("Failed to fetch stages for cached job", exc_info=e, extra={"job_id": job_id})
                        if "stages" not in cached_data:
                            cached_data["stages"] = {}
                logger.debug("Job status retrieved from cache", extra={"job_id": job_id})
                return cached_data
            else:
                # Cache hit but wrong user - clear cache and fetch from DB
                logger.warning("Cached job belongs to different user, fetching from DB", extra={"job_id": job_id})
                await redis_client.client.delete(cache_key)
    except Exception as e:
        logger.warning("Failed to get job status from cache", exc_info=e)
    
    # Cache miss or ownership mismatch - fetch from database
    # Verify ownership (this also fetches the job)
    job = await verify_job_ownership(job_id, current_user)
    
    # Fetch stages from job_stages table, including metadata
    try:
        stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).execute()
        stages = {}
        if stages_result.data:
            for stage in stages_result.data:
                stage_name = stage.get("stage_name")
                if stage_name:
                    stage_info = {
                        "status": stage.get("status", "pending"),
                        "duration": stage.get("duration_seconds"),
                        "progress": None,  # Not stored in job_stages table
                    }
                    # Include metadata if available (for restoring section content)
                    metadata = stage.get("metadata")
                    if metadata:
                        try:
                            # Parse JSON metadata if it's a string
                            if isinstance(metadata, str):
                                metadata = json.loads(metadata)
                            stage_info["metadata"] = metadata
                        except (json.JSONDecodeError, TypeError):
                            # If metadata is not valid JSON, skip it
                            pass
                    stages[stage_name] = stage_info
        
        # For old jobs without metadata, try to reconstruct from Supabase Storage
        # This handles jobs created before metadata storage was implemented
        # Use shorter timeout and non-blocking approach to avoid hanging
        if not stages.get("reference_generator", {}).get("metadata", {}).get("reference_images"):
            try:
                from shared.storage import storage
                import re
                
                # List files in reference-images bucket for this job
                # Use shorter timeout (5s) to avoid blocking the endpoint
                def _list_reference_files():
                    return storage.storage.from_("reference-images").list(job_id)
                
                try:
                    reference_files = await asyncio.wait_for(
                        storage._execute_sync(_list_reference_files, timeout=5.0),
                        timeout=5.0
                    )
                    if reference_files and len(reference_files) > 0:
                        scene_refs = []
                        char_refs = []
                        
                        for file_info in reference_files:
                            if not isinstance(file_info, dict):
                                continue
                            file_name = file_info.get("name", "")
                            # Generate signed URL for the file
                            try:
                                signed_url = await storage.get_signed_url(
                                    bucket="reference-images",
                                    path=f"{job_id}/{file_name}",
                                    expires_in=3600
                                )
                                
                                # Determine if it's a scene or character reference based on filename
                                if file_name.startswith("scene_"):
                                    scene_id = file_name.replace("scene_", "").replace(".png", "")
                                    scene_refs.append({
                                        "scene_id": scene_id,
                                        "image_url": signed_url,
                                        "prompt_used": "",
                                        "generation_time": 0,
                                        "cost": "0"
                                    })
                                elif file_name.startswith("char_"):
                                    char_id = file_name.replace("char_", "").replace(".png", "")
                                    char_refs.append({
                                        "character_id": char_id,
                                        "image_url": signed_url,
                                        "prompt_used": "",
                                        "generation_time": 0,
                                        "cost": "0"
                                    })
                            except Exception as url_error:
                                logger.warning(f"Failed to generate signed URL for {file_name}", exc_info=url_error)
                        
                        if scene_refs or char_refs:
                            # Reconstruct metadata from storage
                            if "reference_generator" not in stages:
                                stages["reference_generator"] = {"status": "completed"}
                            
                            if "metadata" not in stages["reference_generator"]:
                                stages["reference_generator"]["metadata"] = {}
                            
                            stages["reference_generator"]["metadata"]["reference_images"] = {
                                "scene_references": scene_refs,
                                "character_references": char_refs,
                                "total_references": len(scene_refs) + len(char_refs),
                                "total_generation_time": 0,
                                "total_cost": "0",
                                "status": "success"
                            }
                            logger.info(f"Reconstructed reference images metadata from storage for job {job_id}")
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout listing reference images from storage for job {job_id}")
                except Exception as storage_error:
                    logger.debug(f"Could not list reference images from storage (may not exist): {storage_error}")
            except asyncio.TimeoutError:
                logger.debug(f"Timeout during reference images reconstruction for job {job_id}")
            except Exception as e:
                logger.debug(f"Failed to reconstruct reference images from storage: {e}")
        
        # Reconstruct video clips from storage if metadata is missing
        # Use shorter timeout to avoid blocking the endpoint
        if not stages.get("video_generator", {}).get("metadata", {}).get("clips"):
            try:
                from shared.storage import storage
                
                def _list_video_clips():
                    return storage.storage.from_("video-clips").list(job_id)
                
                try:
                    clip_files = await asyncio.wait_for(
                        storage._execute_sync(_list_video_clips, timeout=5.0),
                        timeout=5.0
                    )
                    if clip_files and len(clip_files) > 0:
                        clips = []
                        completed = 0
                        
                        for file_info in clip_files:
                            if not isinstance(file_info, dict):
                                continue
                            file_name = file_info.get("name", "")
                            # Extract clip index from filename (e.g., "clip_0.mp4" -> 0)
                            match = re.search(r"clip_(\d+)\.mp4", file_name)
                            if match:
                                clip_index = int(match.group(1))
                                try:
                                    signed_url = await storage.get_signed_url(
                                        bucket="video-clips",
                                        path=f"{job_id}/{file_name}",
                                        expires_in=3600
                                    )
                                    clips.append({
                                        "clip_index": clip_index,
                                        "video_url": signed_url,
                                        "actual_duration": 5.0,  # Unknown, use default
                                        "target_duration": 5.0,
                                        "duration_diff": 0.0,
                                        "status": "success",
                                        "cost": "0",
                                        "retry_count": 0,
                                        "generation_time": 0
                                    })
                                    completed += 1
                                except Exception as url_error:
                                    logger.warning(f"Failed to generate signed URL for {file_name}", exc_info=url_error)
                        
                        if clips:
                            # Sort by clip_index
                            clips.sort(key=lambda x: x["clip_index"])
                            
                            if "video_generator" not in stages:
                                stages["video_generator"] = {"status": "completed"}
                            
                            if "metadata" not in stages["video_generator"]:
                                stages["video_generator"]["metadata"] = {}
                            
                            stages["video_generator"]["metadata"]["clips"] = {
                                "job_id": job_id,
                                "clips": clips,
                                "total_clips": len(clips),
                                "successful_clips": completed,
                                "failed_clips": 0,
                                "total_cost": "0",
                                "total_generation_time": 0
                            }
                            logger.info(f"Reconstructed video clips metadata from storage for job {job_id}")
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout listing video clips from storage for job {job_id}")
                except Exception as storage_error:
                    logger.debug(f"Could not list video clips from storage (may not exist): {storage_error}")
            except asyncio.TimeoutError:
                logger.debug(f"Timeout during video clips reconstruction for job {job_id}")
            except Exception as e:
                logger.debug(f"Failed to reconstruct video clips from storage: {e}")
        
        job["stages"] = stages
    except Exception as e:
        logger.warning("Failed to fetch job stages", exc_info=e, extra={"job_id": job_id})
        # If stages fetch fails, set empty dict to avoid breaking frontend
        job["stages"] = {}
    
    # Cache result (30s TTL)
    try:
        await redis_client.set(cache_key, json.dumps(job), ex=30)
    except Exception as e:
        logger.warning("Failed to cache job status", exc_info=e)
    
    return job


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    List user's jobs with pagination and filtering.
    
    Args:
        status_filter: Filter by status (queued, processing, completed, failed)
        limit: Number of results (default: 10, max: 50)
        offset: Pagination offset (default: 0)
        current_user: Current authenticated user
        
    Returns:
        Jobs list with total, limit, offset
    """
    user_id = current_user["user_id"]
    
    try:
        # Build query
        query = db_client.table("jobs").select("*").eq("user_id", user_id)
        
        # Apply status filter
        if status_filter:
            valid_statuses = ["queued", "processing", "completed", "failed"]
            if status_filter not in valid_statuses:
                raise ValidationError(f"Invalid status filter. Must be one of: {valid_statuses}")
            query = query.eq("status", status_filter)
        
        # Get total count
        count_query = db_client.table("jobs").select("*", count="exact").eq("user_id", user_id)
        if status_filter:
            count_query = count_query.eq("status", status_filter)
        count_result = await count_query.execute()
        total = count_result.count if hasattr(count_result, "count") else 0
        
        # Apply ordering and pagination
        # Order by created_at descending (most recent first)
        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)  # Supabase uses range() for offset/limit
        
        # Execute query
        result = await query.execute()
        jobs = result.data if result.data else []
        
        return {
            "jobs": jobs,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error("Failed to list jobs", exc_info=e, extra={"user_id": user_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list jobs"
        )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel a queued or processing job.
    
    Args:
        job_id: Job ID to cancel
        current_user: Current authenticated user
        
    Returns:
        Cancellation confirmation
    """
    # Verify ownership
    job = await verify_job_ownership(job_id, current_user)
    
    job_status = job.get("status")
    
    # Only allow cancellation if queued or processing
    if job_status not in ["queued", "processing"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job_status}"
        )
    
    try:
        if job_status == "queued":
            # Remove from queue
            await remove_job(job_id)
            
            # Mark as failed in database
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": "Job cancelled by user"
            }).eq("id", job_id).execute()
            
        elif job_status == "processing":
            # Set cancellation flag in Redis (TTL: 15min)
            cancel_key = f"job_cancel:{job_id}"
            await redis_client.set(cancel_key, "1", ex=900)  # 15 minutes
            
            # Mark as failed in database immediately
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": "Job cancelled by user"
            }).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        logger.info("Job cancelled", extra={"job_id": job_id, "status": job_status})
        
        return {
            "job_id": job_id,
            "status": "failed",
            "message": "Job cancelled by user"
        }
        
    except Exception as e:
        logger.error("Failed to cancel job", exc_info=e, extra={"job_id": job_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel job"
        )

