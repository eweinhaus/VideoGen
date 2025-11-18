"""
Job status management for clip regeneration.

Handles job status updates and database locking to prevent concurrent regenerations.
"""
from typing import Optional
from uuid import UUID

from shared.database import DatabaseClient
from shared.logging import get_logger
from shared.errors import ValidationError

logger = get_logger("clip_regenerator.status_manager")

db_client = DatabaseClient()


async def acquire_job_lock(job_id: UUID) -> bool:
    """
    Acquire database lock on job row to prevent concurrent regeneration.
    
    Uses atomic status update: only succeeds if status is 'completed'.
    If another request already set status to 'regenerating', this will fail.
    
    Args:
        job_id: Job ID to lock
        
    Returns:
        True if lock acquired, False if already locked
        
    Raises:
        ValidationError: If job not found or status is invalid
    """
    try:
        # Check current job status
        result = await db_client.table("jobs").select("status").eq("id", str(job_id)).single().execute()
        
        if not result.data:
            raise ValidationError(f"Job {job_id} not found")
        
        current_status = result.data.get("status")
        
        # Only allow locking if status is 'completed' or 'failed' (for retry)
        if current_status not in ["completed", "failed"]:
            if current_status == "regenerating":
                logger.debug(
                    f"Job {job_id} is already being regenerated",
                    extra={"job_id": str(job_id), "status": current_status}
                )
                return False
            else:
                raise ValidationError(
                    f"Cannot regenerate job with status '{current_status}'. Job must be 'completed' or 'failed'."
                )
        
        # Atomically update status from 'completed'/'failed' to 'regenerating'
        # This ensures only one request can acquire the lock
        update_result = await db_client.table("jobs").update({
            "status": "regenerating"
        }).eq("id", str(job_id)).eq("status", current_status).execute()
        
        # Check if update succeeded (if another request updated it, this will return 0 rows)
        if not update_result.data or len(update_result.data) == 0:
            # Another request got there first
            logger.debug(
                f"Failed to acquire lock for job {job_id} (another request got there first)",
                extra={"job_id": str(job_id)}
            )
            return False
        
        logger.info(
            f"Successfully acquired lock for job {job_id}",
            extra={"job_id": str(job_id), "previous_status": current_status}
        )
        return True
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to acquire lock for job {job_id}: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        raise ValidationError(f"Failed to acquire lock: {str(e)}") from e


async def release_job_lock(job_id: UUID) -> None:
    """
    Release database lock on job row.
    
    This is a no-op if lock was already released, but ensures cleanup.
    
    Args:
        job_id: Job ID to release lock for
    """
    try:
        # Lock is released by updating status to 'completed' or 'failed'
        # This function is mainly for logging and ensuring cleanup
        logger.debug(
            f"Releasing lock for job {job_id}",
            extra={"job_id": str(job_id)}
        )
    except Exception as e:
        logger.warning(
            f"Error releasing lock for job {job_id}: {e}",
            extra={"job_id": str(job_id)}
        )


async def update_job_status(
    job_id: UUID,
    status: str,
    video_url: Optional[str] = None
) -> None:
    """
    Update job status in database.
    
    Also updates video_url if provided.
    Validates status transitions are allowed.
    
    Args:
        job_id: Job ID to update
        status: New status ('completed', 'failed', 'regenerating')
        video_url: Optional new video URL (only set if status is 'completed')
        
    Raises:
        ValidationError: If status transition is invalid
    """
    # Validate status
    valid_statuses = ["queued", "processing", "completed", "failed", "regenerating"]
    if status not in valid_statuses:
        raise ValidationError(f"Invalid status: {status}. Valid statuses: {valid_statuses}")
    
    # Validate status transitions
    # Get current status
    try:
        current_result = await db_client.table("jobs").select("status").eq("id", str(job_id)).single().execute()
        if current_result.data:
            current_status = current_result.data.get("status")
            
            # Validate transition
            if current_status == "completed" and status not in ["regenerating", "completed"]:
                raise ValidationError(
                    f"Invalid status transition: {current_status} -> {status}. "
                    "Completed jobs can only transition to 'regenerating' or remain 'completed'."
                )
            if current_status == "regenerating" and status not in ["completed", "failed"]:
                raise ValidationError(
                    f"Invalid status transition: {current_status} -> {status}. "
                    "Regenerating jobs can only transition to 'completed' or 'failed'."
                )
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        # If we can't check current status, proceed anyway (might be first update)
        logger.warning(
            f"Could not validate status transition for job {job_id}: {e}",
            extra={"job_id": str(job_id)}
        )
    
    # Prepare update data
    update_data = {"status": status}
    if video_url and status == "completed":
        update_data["video_url"] = video_url
    
    try:
        await db_client.table("jobs").update(update_data).eq("id", str(job_id)).execute()
        
        logger.info(
            f"Updated job status to '{status}'",
            extra={
                "job_id": str(job_id),
                "status": status,
                "video_url_updated": video_url is not None
            }
        )
    except Exception as e:
        logger.error(
            f"Failed to update job status: {e}",
            extra={"job_id": str(job_id), "status": status},
            exc_info=True
        )
        raise ValidationError(f"Failed to update job status: {str(e)}") from e

