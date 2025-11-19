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
    # Log entry point for debugging
    logger.info(
        f"ACQUIRE_LOCK_START: Beginning lock acquisition for job {job_id}",
        extra={
            "job_id": str(job_id),
            "db_client_type": str(type(db_client)),
            "has_table_method": hasattr(db_client, 'table')
        }
    )
    
    try:
        logger.debug(
            f"Attempting to acquire lock for job {job_id}",
            extra={"job_id": str(job_id)}
        )
        
        # Check current job status
        logger.debug(
            f"Building database query for job status",
            extra={"job_id": str(job_id)}
        )
        
        # Build query step by step to catch where error occurs
        table_builder = db_client.table("jobs")
        logger.debug(f"Table builder type: {type(table_builder)}", extra={"job_id": str(job_id)})
        
        # Check if table_builder has expected methods
        table_methods = [m for m in dir(table_builder) if not m.startswith('_')]
        logger.debug(
            f"Table builder methods available",
            extra={"job_id": str(job_id), "methods": table_methods[:10]}  # First 10 methods
        )
        
        select_builder = table_builder.select("status")
        logger.debug(
            f"Select builder type: {type(select_builder)}",
            extra={
                "job_id": str(job_id),
                "has_limit": hasattr(select_builder, 'limit'),
                "has_single": hasattr(select_builder, 'single'),
                "has_eq": hasattr(select_builder, 'eq')
            }
        )
        
        eq_builder = select_builder.eq("id", str(job_id))
        logger.debug(
            f"Eq builder type: {type(eq_builder)}",
            extra={
                "job_id": str(job_id),
                "has_limit": hasattr(eq_builder, 'limit'),
                "has_single": hasattr(eq_builder, 'single'),
                "has_execute": hasattr(eq_builder, 'execute')
            }
        )
        
        # Use limit(1) instead of single() to avoid method availability issues
        # This works reliably even if single() method isn't available
        logger.debug(f"Using limit(1) for query (single() may not be available)", extra={"job_id": str(job_id)})
        
        # Check if limit method exists before calling
        if not hasattr(eq_builder, 'limit'):
            available_methods = [m for m in dir(eq_builder) if not m.startswith('_')]
            error_msg = (
                f"Query builder does not support 'limit()' method. "
                f"Available methods: {available_methods[:15]}. "
                f"Builder type: {type(eq_builder)}. "
                f"This suggests a database client configuration issue or version mismatch."
            )
            logger.error(error_msg, extra={"job_id": str(job_id), "available_methods": available_methods})
            raise ValidationError(error_msg)
        
        result = await eq_builder.limit(1).execute()
        logger.debug(f"Query executed successfully", extra={"job_id": str(job_id)})
        
        if not result.data:
            raise ValidationError(f"Job {job_id} not found")
        
        # Handle case where result.data might be a list (happens with limit(1) fallback or .single() edge cases)
        if isinstance(result.data, list):
            if len(result.data) == 0:
                raise ValidationError(f"Job {job_id} not found")
            elif len(result.data) > 1:
                logger.warning(
                    f"Multiple results found for job {job_id} (expected single result)",
                    extra={"job_id": str(job_id), "result_count": len(result.data)}
                )
            # Use first result
            job_data = result.data[0]
        else:
            # Normal case: result.data is a dict (from .single())
            job_data = result.data
        
        current_status = job_data.get("status")
        
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
    except AttributeError as e:
        # Special handling for AttributeError to provide more context
        # Get detailed information about what object failed and what methods it has
        error_str = str(e)
        error_obj_name = error_str.split("'")[1] if "'" in error_str else "unknown"
        error_method_name = error_str.split("'")[3] if "'" in error_str and error_str.count("'") >= 4 else "unknown"
        
        # Get available methods on the failing object if possible
        available_methods = []
        try:
            # Try to inspect what methods are actually available
            if "AsyncTableQueryBuilder" in error_str:
                from shared.database import AsyncTableQueryBuilder
                available_methods = [m for m in dir(AsyncTableQueryBuilder) if not m.startswith('_')]
        except Exception as diag_error:
            available_methods = [f"Could not inspect: {str(diag_error)}"]
        
        error_details = {
            "job_id": str(job_id),
            "error_type": type(e).__name__,
            "error_message": str(e),
            "error_args": e.args if hasattr(e, 'args') else None,
            "db_client_type": str(type(db_client)),
            "table_method_exists": hasattr(db_client, 'table'),
            "error_object": error_obj_name,
            "missing_method": error_method_name,
            "available_methods": available_methods[:20],  # First 20 methods
        }
        
        logger.error(
            f"ACQUIRE_LOCK_ATTRIBUTE_ERROR: AttributeError while acquiring lock for job {job_id}",
            extra=error_details,
            exc_info=True
        )
        
        # Build comprehensive error message that will definitely show up
        methods_list = ", ".join(available_methods[:15]) if available_methods else "could not determine"
        detailed_error = (
            f"❌ DATABASE CONFIGURATION ERROR ❌\n\n"
            f"Error: {str(e)}\n"
            f"Object: {error_obj_name}\n"
            f"Missing Method: {error_method_name}\n"
            f"Error Type: {type(e).__name__}\n\n"
            f"Available methods on {error_obj_name}: {methods_list}\n\n"
            f"🔧 TROUBLESHOOTING:\n"
            f"1. Restart the server to load updated code\n"
            f"2. Check database client version compatibility\n"
            f"3. Verify shared/database.py is up to date\n"
            f"4. Check server logs for full error details\n\n"
            f"If this persists, contact support with this full error message."
        )
        
        # Log the detailed error separately so it definitely appears
        logger.error(f"ACQUIRE_LOCK_DETAILED_ERROR: {detailed_error}")
        
        raise ValidationError(detailed_error) from e
    except Exception as e:
        error_info = {
            "job_id": str(job_id),
            "error_type": type(e).__name__,
            "error_message": str(e),
            "error_args": e.args if hasattr(e, 'args') else None,
            "db_client_type": str(type(db_client)),
            "traceback_summary": str(e.__traceback__) if hasattr(e, '__traceback__') else None,
        }
        
        # Extract more context from the error message
        error_str = str(e).lower()
        is_database_method_error = (
            "single" in error_str or 
            "attribute" in error_str or 
            "async" in error_str or
            "querybuilder" in error_str or
            "query_builder" in error_str
        )
        
        logger.error(
            f"Failed to acquire lock for job {job_id}: {e}",
            extra=error_info,
            exc_info=True
        )
        
        # Provide user-friendly error message with details
        if is_database_method_error:
            # Extract object and method names from error if possible
            error_parts = str(e).split("'")
            obj_name = error_parts[1] if len(error_parts) > 1 else "unknown object"
            method_name = error_parts[3] if len(error_parts) > 3 else "unknown method"
            
            # Try to get available methods
            available_methods = []
            try:
                if "AsyncTableQueryBuilder" in str(e):
                    from shared.database import AsyncTableQueryBuilder
                    available_methods = [m for m in dir(AsyncTableQueryBuilder) if not m.startswith('_')]
            except Exception:
                pass
            
            methods_str = ", ".join(available_methods[:15]) if available_methods else "could not determine"
            
            user_message = (
                f"❌ DATABASE CONFIGURATION ERROR ❌\n\n"
                f"Error: {str(e)}\n"
                f"Object: {obj_name}\n"
                f"Missing Method: {method_name}\n"
                f"Error Type: {type(e).__name__}\n\n"
                f"Available methods: {methods_str}\n\n"
                f"🔧 TROUBLESHOOTING:\n"
                f"1. Restart the server\n"
                f"2. Check database client version\n"
                f"3. Verify code is up to date\n"
                f"4. Check server logs for details\n\n"
                f"If this persists, contact support."
            )
        else:
            user_message = (
                f"❌ FAILED TO ACQUIRE LOCK ❌\n\n"
                f"Error: {str(e)}\n"
                f"Error Type: {type(e).__name__}\n\n"
                f"Please try again or contact support if this persists."
            )
        
        # Log the detailed error separately
        logger.error(f"ACQUIRE_LOCK_GENERAL_ERROR: {user_message}")
        
        raise ValidationError(user_message) from e


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
        # Use limit(1) instead of single() for reliability
        eq_builder = db_client.table("jobs").select("status").eq("id", str(job_id))
        current_result = await eq_builder.limit(1).execute()
        if current_result.data:
            # Handle case where result.data might be a list
            if isinstance(current_result.data, list):
                if len(current_result.data) > 0:
                    job_data = current_result.data[0]
                else:
                    job_data = {}
            else:
                job_data = current_result.data
            
            current_status = job_data.get("status")
            
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

