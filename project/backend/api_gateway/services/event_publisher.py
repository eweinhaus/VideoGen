"""
Event publisher service.

Publishes pipeline events to Redis pub/sub for SSE distribution.
"""

import json
from typing import Dict, Any
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger(__name__)

redis_client = RedisClient()


async def publish_event(job_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """
    Publish an event to Redis pub/sub channel.
    
    Args:
        job_id: Job ID
        event_type: Event type (progress, stage_update, message, cost_update, completed, error)
        data: Event data dictionary
    """
    channel = f"job_events:{job_id}"
    
    message = {
        "event_type": event_type,
        "data": data
    }
    
    try:
        # Publish to Redis pub/sub channel
        # Note: Redis pub/sub requires bytes, so we encode the JSON string
        message_json = json.dumps(message)
        await redis_client.client.publish(channel, message_json)
        
        logger.debug(
            "Event published",
            extra={"job_id": job_id, "event_type": event_type}
        )
        
    except Exception as e:
        logger.error(
            "Failed to publish event",
            exc_info=e,
            extra={"job_id": job_id, "event_type": event_type}
        )

