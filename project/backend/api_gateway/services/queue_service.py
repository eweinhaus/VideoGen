"""
Queue service.

Job queue management using Redis (BullMQ-like behavior).
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
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
    template: str = "standard",
    uploaded_character_images: Optional[List[Dict[str, Any]]] = None
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
        uploaded_character_images: Optional list of uploaded character reference images
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
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Add uploaded character images if provided
    if uploaded_character_images:
        job_data["uploaded_character_images"] = uploaded_character_images
        logger.info(
            f"Adding uploaded_character_images to job_data for job {job_id}",
            extra={
                "job_id": job_id,
                "uploaded_character_images_count": len(uploaded_character_images),
                "first_image_url": uploaded_character_images[0].get("url", "missing")[:100] if uploaded_character_images else None
            }
        )
    else:
        logger.info(f"No uploaded_character_images provided for job {job_id}", extra={"job_id": job_id})
    
    try:
        # Add to queue (using Redis list as queue)
        # Encode as bytes since Redis client has decode_responses=False
        queue_key = f"{QUEUE_NAME}:queue"
        job_json = json.dumps(job_data)
        
        # Verify uploaded_character_images is in the JSON
        if "uploaded_character_images" in job_json:
            logger.debug(f"uploaded_character_images found in job_json for job {job_id}", extra={"job_id": job_id})
        else:
            logger.warning(f"uploaded_character_images NOT found in job_json for job {job_id}", extra={"job_id": job_id})
        
        await redis_client.client.lpush(queue_key, job_json.encode('utf-8'))
        
        # Store job data for worker to retrieve
        job_key = f"{QUEUE_NAME}:job:{job_id}"
        await redis_client.client.set(job_key, job_json.encode('utf-8'), ex=900)  # 15 min TTL
        
        logger.info(
            "Job enqueued",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "has_uploaded_character_images": bool(uploaded_character_images),
                "uploaded_character_images_count": len(uploaded_character_images) if uploaded_character_images else 0
            }
        )
        
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

