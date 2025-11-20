"""
Database helper functions.

Utility functions for common database operations.
"""

import json
from typing import Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime, date
from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger(__name__)

db_client = DatabaseClient()
redis_client = RedisClient()


def make_json_serializable(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable objects to serializable types.
    
    Handles:
    - UUID -> str
    - Decimal -> str
    - datetime -> ISO format string
    - date -> ISO format string
    - dict/list -> recursively process values
    
    Args:
        obj: Object to make JSON serializable
        
    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj


async def invalidate_job_cache(job_id: str) -> None:
    """
    Invalidate Redis cache for a job.
    
    Args:
        job_id: Job ID
    """
    try:
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
    except Exception as e:
        logger.warning("Failed to invalidate job cache", exc_info=e, extra={"job_id": job_id})


async def update_job_stage(
    job_id: str,
    stage_name: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Update or create a job stage record.
    
    Args:
        job_id: Job ID
        stage_name: Stage name
        status: Stage status (pending, processing, completed, failed)
        metadata: Optional metadata dictionary (will be stored as JSONB)
    """
    try:
        stage_data = {
            "job_id": job_id,
            "stage_name": stage_name,
            "status": status
        }
        
        if metadata:
            # Convert metadata to JSON-serializable format (recursively convert UUIDs, Decimals, etc. to strings)
            # PostgREST will handle JSON serialization for JSONB fields, but we need to ensure all values are JSON-serializable
            serializable_metadata = make_json_serializable(metadata)
            stage_data["metadata"] = serializable_metadata
        
        # Check if stage exists
        existing = await db_client.table("job_stages").select("id").eq("job_id", job_id).eq("stage_name", stage_name).execute()
        
        if existing.data and len(existing.data) > 0:
            # Update existing
            await db_client.table("job_stages").update(stage_data).eq("job_id", job_id).eq("stage_name", stage_name).execute()
        else:
            # Insert new
            await db_client.table("job_stages").insert(stage_data).execute()
        
        logger.debug("Job stage updated", extra={"job_id": job_id, "stage_name": stage_name, "status": status})
        
    except Exception as e:
        logger.error("Failed to update job stage", exc_info=e, extra={"job_id": job_id, "stage_name": stage_name})


async def get_job_stage(job_id: str, stage_name: str) -> Optional[Dict[str, Any]]:
    """
    Get job stage record.
    
    Args:
        job_id: Job ID
        stage_name: Stage name
        
    Returns:
        Stage record dictionary or None if not found
    """
    try:
        result = await db_client.table("job_stages").select("*").eq("job_id", job_id).eq("stage_name", stage_name).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        
        return None
        
    except Exception as e:
        logger.error("Failed to get job stage", exc_info=e, extra={"job_id": job_id, "stage_name": stage_name})
        return None

