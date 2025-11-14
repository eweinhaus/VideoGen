"""
Job endpoints.

Job status, list, and cancellation.
"""

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
    # Verify ownership (this also fetches the job)
    job = await verify_job_ownership(job_id, current_user)
    
    # Check Redis cache first (30s TTL)
    cache_key = f"job_status:{job_id}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            cached_data = json.loads(cached)
            logger.debug("Job status retrieved from cache", extra={"job_id": job_id})
            return cached_data
    except Exception as e:
        logger.warning("Failed to get job status from cache", exc_info=e)
    
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
        
        # Apply pagination
        # Note: Supabase uses order() method, but our wrapper may not support it yet
        # For now, we'll fetch all and sort in Python (not ideal for large datasets)
        # TODO: Add order() method to AsyncTableQueryBuilder
        query = query.limit(limit + offset)  # Fetch more than needed for offset
        
        # Execute query
        result = await query.execute()
        all_jobs = result.data if result.data else []
        
        # Sort by created_at descending (most recent first)
        all_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # Apply offset and limit
        jobs = all_jobs[offset:offset + limit]
        
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

