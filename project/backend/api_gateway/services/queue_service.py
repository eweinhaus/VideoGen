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
from shared.config import settings

logger = get_logger(__name__)

redis_client = RedisClient()
# Use environment-aware queue name to prevent cross-environment job consumption
# Local workers will use "video_generation_development", production uses "video_generation_production"
QUEUE_NAME = settings.queue_name


async def enqueue_job(
    job_id: str,
    user_id: str,
    audio_url: str,
    user_prompt: str,
    stop_at_stage: str = None,
    video_model: str = "kling_v21",
    aspect_ratio: str = "16:9",
    template: str = "standard"
) -> None:
    """
    Enqueue a job to the processing queue.
    
    Args:
        job_id: Job ID
        user_id: User ID
        audio_url: URL of uploaded audio file
        user_prompt: User's creative prompt
        stop_at_stage: Optional stage to stop at (for testing)
        video_model: Video generation model to use
        aspect_ratio: Aspect ratio for video generation (default: "16:9")
        template: Template to use (default: "standard", options: "standard", "lipsync")
    """
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "audio_url": audio_url,
        "user_prompt": user_prompt,
        "stop_at_stage": stop_at_stage,
        "video_model": video_model,
        "aspect_ratio": aspect_ratio,
        "template": template,
        "job_type": "generation",  # Distinguish from regeneration
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        # Add to queue (using Redis list as queue)
        # Encode as bytes since Redis client has decode_responses=False
        queue_key = f"{QUEUE_NAME}:queue"
        job_json = json.dumps(job_data)
        await redis_client.client.lpush(queue_key, job_json.encode('utf-8'))
        
        # Store job data for worker to retrieve
        job_key = f"{QUEUE_NAME}:job:{job_id}"
        await redis_client.client.set(job_key, job_json.encode('utf-8'), ex=900)  # 15 min TTL
        
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


async def enqueue_regeneration_job(
    job_id: str,
    user_id: str,
    clip_indices: list,
    user_instruction: str,
    conversation_history: list = None,
    regeneration_id: str = None
) -> None:
    """
    Enqueue a regeneration job to the processing queue.
    
    Args:
        job_id: Job ID to regenerate clips for
        user_id: User ID
        clip_indices: List of clip indices to regenerate
        user_instruction: User's regeneration instruction
        conversation_history: Optional conversation history for context
        regeneration_id: Optional regeneration ID (generated if not provided)
    """
    if not regeneration_id:
        regeneration_id = str(uuid.uuid4())
    
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "clip_indices": clip_indices,
        "user_instruction": user_instruction,
        "conversation_history": conversation_history or [],
        "regeneration_id": regeneration_id,
        "job_type": "regeneration",  # Distinguish from generation
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        # Add to queue (using Redis list as queue)
        # Encode as bytes since Redis client has decode_responses=False
        queue_key = f"{QUEUE_NAME}:queue"
        job_json = json.dumps(job_data)
        await redis_client.client.lpush(queue_key, job_json.encode('utf-8'))
        
        # Store job data for worker to retrieve
        regen_key = f"{QUEUE_NAME}:regeneration:{regeneration_id}"
        await redis_client.client.set(regen_key, job_json.encode('utf-8'), ex=900)  # 15 min TTL
        
        logger.info(
            "Regeneration job enqueued", 
            extra={
                "job_id": job_id, 
                "user_id": user_id, 
                "regeneration_id": regeneration_id,
                "clip_indices": clip_indices
            }
        )
        
    except Exception as e:
        logger.error(
            "Failed to enqueue regeneration job", 
            exc_info=e, 
            extra={"job_id": job_id, "regeneration_id": regeneration_id}
        )
        raise


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

