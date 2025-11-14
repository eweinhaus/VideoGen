"""
Queue service.

Job queue management using Redis (BullMQ-like behavior).
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger(__name__)

redis_client = RedisClient()
QUEUE_NAME = "video_generation"


async def enqueue_job(
    job_id: str,
    user_id: str,
    audio_url: str,
    user_prompt: str
) -> None:
    """
    Enqueue a job to the processing queue.
    
    Args:
        job_id: Job ID
        user_id: User ID
        audio_url: URL of uploaded audio file
        user_prompt: User's creative prompt
    """
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "audio_url": audio_url,
        "user_prompt": user_prompt,
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        # Add to queue (using Redis list as queue)
        queue_key = f"{QUEUE_NAME}:queue"
        await redis_client.client.lpush(queue_key, json.dumps(job_data))
        
        # Store job data for worker to retrieve
        job_key = f"{QUEUE_NAME}:job:{job_id}"
        await redis_client.client.set(job_key, json.dumps(job_data), ex=900)  # 15 min TTL
        
        logger.info("Job enqueued", extra={"job_id": job_id, "user_id": user_id})
        
    except Exception as e:
        logger.error("Failed to enqueue job", exc_info=e, extra={"job_id": job_id})
        raise


async def remove_job(job_id: str) -> bool:
    """
    Remove a job from the queue.
    
    Args:
        job_id: Job ID to remove
        
    Returns:
        True if job was removed, False if not found
    """
    try:
        # Remove from queue (this is a simplified version)
        # In a real BullMQ implementation, this would be more complex
        job_key = f"{QUEUE_NAME}:job:{job_id}"
        await redis_client.client.delete(job_key)
        
        logger.info("Job removed from queue", extra={"job_id": job_id})
        return True
        
    except Exception as e:
        logger.error("Failed to remove job from queue", exc_info=e, extra={"job_id": job_id})
        return False


async def get_queue_size() -> int:
    """
    Get the current queue size.
    
    Returns:
        Number of jobs in queue
    """
    try:
        queue_key = f"{QUEUE_NAME}:queue"
        size = await redis_client.client.llen(queue_key)
        return size
    except Exception as e:
        logger.error("Failed to get queue size", exc_info=e)
        return 0

