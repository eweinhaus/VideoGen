"""
Analytics tracking for regeneration events.

Tracks regeneration events for analytics dashboard.
Non-blocking: tracking failures don't break regeneration flow.
"""
import asyncio
from typing import Optional
from uuid import UUID
from decimal import Decimal

from shared.database import DatabaseClient
from shared.logging import get_logger
from modules.analytics.aggregation import invalidate_analytics_cache

logger = get_logger("analytics.tracking")

db_client = DatabaseClient()


async def track_regeneration(
    job_id: UUID,
    user_id: UUID,
    clip_index: int,
    instruction: str,
    template_id: Optional[str],
    cost: Decimal,
    success: bool
) -> None:
    """
    Track regeneration event for analytics.
    
    Non-blocking: errors are logged but not raised.
    This ensures tracking failures don't break regeneration flow.
    
    Args:
        job_id: Job ID
        user_id: User ID who initiated regeneration
        clip_index: Index of clip regenerated
        instruction: User instruction that triggered regeneration
        template_id: Template ID if template was matched, None otherwise
        cost: Cost of regeneration
        success: Whether regeneration succeeded
    """
    try:
        await db_client.table("regeneration_analytics").insert({
            "job_id": str(job_id),
            "user_id": str(user_id),
            "clip_index": clip_index,
            "instruction": instruction,
            "template_id": template_id,
            "cost": float(cost),  # Supabase expects float for DECIMAL
            "success": success
        }).execute()
        
        logger.debug(
            f"Tracked regeneration event",
            extra={
                "job_id": str(job_id),
                "user_id": str(user_id),
                "clip_index": clip_index,
                "template_id": template_id,
                "success": success
            }
        )
        
        # Invalidate cache for this job and user (non-blocking)
        try:
            asyncio.create_task(invalidate_analytics_cache(job_id=job_id, user_id=user_id))
        except Exception as e:
            logger.warning(f"Failed to invalidate analytics cache: {e}")
    except Exception as e:
        # Non-blocking: log error but don't raise
        logger.error(
            f"Failed to track regeneration event: {e}",
            extra={
                "job_id": str(job_id),
                "user_id": str(user_id),
                "clip_index": clip_index
            },
            exc_info=True
        )


async def track_regeneration_async(
    job_id: UUID,
    user_id: UUID,
    clip_index: int,
    instruction: str,
    template_id: Optional[str],
    cost: Decimal,
    success: bool
) -> None:
    """
    Track regeneration event asynchronously (fire-and-forget).
    
    Creates a background task that won't block the calling function.
    Use this when you want to ensure tracking doesn't slow down regeneration.
    
    Args:
        Same as track_regeneration()
    """
    asyncio.create_task(
        track_regeneration(
            job_id=job_id,
            user_id=user_id,
            clip_index=clip_index,
            instruction=instruction,
            template_id=template_id,
            cost=cost,
            success=success
        )
    )

