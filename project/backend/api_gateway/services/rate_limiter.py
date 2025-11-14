"""
Rate limiting service.

Redis-based sliding window rate limiting (5 jobs per user per hour).
"""

import time
from shared.redis_client import RedisClient
from shared.config import settings
from shared.errors import RateLimitError
from shared.logging import get_logger

logger = get_logger(__name__)

redis_client = RedisClient()


async def check_rate_limit(user_id: str) -> None:
    """
    Check if user has exceeded rate limit (5 jobs per hour).
    
    Uses Redis sorted set with sliding window algorithm.
    
    Args:
        user_id: User ID to check rate limit for
        
    Raises:
        RateLimitError: If rate limit exceeded
    """
    key = f"rate_limit:{user_id}"
    now = int(time.time())  # UTC Unix timestamp
    one_hour_ago = now - 3600
    
    try:
        # Remove entries older than 1 hour
        await redis_client.client.zremrangebyscore(key, 0, one_hour_ago)
        
        # Count entries in last hour
        count = await redis_client.client.zcard(key)
        
        if count >= 5:
            # Calculate Retry-After header
            # Get oldest entry timestamp
            oldest_entries = await redis_client.client.zrange(key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_time = int(oldest_entries[0][1])
                retry_after = int(3600 - (now - oldest_time))
            else:
                retry_after = 3600
            
            logger.warning(
                "Rate limit exceeded",
                extra={"user_id": user_id, "count": count, "retry_after": retry_after}
            )
            
            raise RateLimitError(
                "Rate limit exceeded: 5 jobs per hour",
                retry_after=retry_after,
                code="RATE_LIMIT_EXCEEDED"
            )
        
        # Add current timestamp to sorted set
        await redis_client.client.zadd(key, {str(now): now})
        await redis_client.client.expire(key, 3600)  # Cleanup after 1 hour
        
        logger.debug(
            "Rate limit check passed",
            extra={"user_id": user_id, "count": count + 1}
        )
        
    except RateLimitError:
        raise
    except Exception as e:
        logger.error("Rate limit check failed", exc_info=e, extra={"user_id": user_id})
        
        # Fail-closed: block request if rate limiter fails
        if settings.rate_limit_fail_closed:
            logger.warning(
                "Rate limiter failed in fail-closed mode, blocking request",
                extra={"user_id": user_id}
            )
            raise RateLimitError(
                "Rate limit service unavailable",
                retry_after=60,
                code="RATE_LIMIT_SERVICE_UNAVAILABLE"
            )
        
        # Fail-open: allow request through (MVP default)
        logger.warning(
            "Rate limiter failed in fail-open mode, allowing request",
            extra={"user_id": user_id}
        )

