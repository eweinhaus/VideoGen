"""
Analytics aggregation with hybrid strategy (real-time + cached).

Part 6: Comparison Tools & Analytics
"""
import json
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime, timedelta

from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger("analytics.aggregation")

db_client = DatabaseClient()
redis_client = RedisClient()


async def get_job_analytics(
    job_id: UUID,
    date_range: str = "all"
) -> List[Dict]:
    """
    Get analytics records for a job with hybrid aggregation strategy.
    
    Real-time for last 7 days, cached for older data.
    
    Args:
        job_id: Job ID
        date_range: Date range filter ("all", "last_7_days", "last_30_days")
        
    Returns:
        List of analytics records
    """
    try:
        # Check if recent (last 7 days) - use real-time
        if date_range == "last_7_days" or date_range == "all":
            cutoff_date = datetime.now() - timedelta(days=7)
            
            # Query recent data (last 7 days) - always real-time
            recent_result = await db_client.table("regeneration_analytics").select("*").eq(
                "job_id", str(job_id)
            ).gte("created_at", cutoff_date.isoformat()).order("created_at", desc=True).execute()
            
            recent_data = recent_result.data or []
            
            # If only requesting last 7 days, return early
            if date_range == "last_7_days":
                return recent_data
            
            # For "all", also get older data (cached)
            # Check cache for older data
            cache_key = f"analytics:job:{job_id}:older_than_7_days"
            cached = await redis_client.get(cache_key)
            
            if cached:
                older_data = json.loads(cached)
                logger.debug(
                    f"Using cached analytics for older data",
                    extra={"job_id": str(job_id), "cached_count": len(older_data)}
                )
            else:
                # Query older data from database
                older_result = await db_client.table("regeneration_analytics").select("*").eq(
                    "job_id", str(job_id)
                ).lt("created_at", cutoff_date.isoformat()).order("created_at", desc=True).execute()
                
                older_data = older_result.data or []
                
                # Cache for 1 hour
                await redis_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps(older_data)
                )
                
                logger.debug(
                    f"Cached analytics for older data",
                    extra={"job_id": str(job_id), "cached_count": len(older_data)}
                )
            
            # Combine recent and older data
            return recent_data + older_data
        
        # For specific date ranges, use cache
        cache_key = f"analytics:job:{job_id}:{date_range}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        # Query database
        # Calculate date filter based on range
        if date_range == "last_30_days":
            cutoff_date = datetime.now() - timedelta(days=30)
            result = await db_client.table("regeneration_analytics").select("*").eq(
                "job_id", str(job_id)
            ).gte("created_at", cutoff_date.isoformat()).order("created_at", desc=True).execute()
        else:
            # All data
            result = await db_client.table("regeneration_analytics").select("*").eq(
                "job_id", str(job_id)
            ).order("created_at", desc=True).execute()
        
        data = result.data or []
        
        # Cache for 1 hour
        await redis_client.setex(
            cache_key,
            3600,
            json.dumps(data)
        )
        
        return data
        
    except Exception as e:
        logger.error(
            f"Failed to get job analytics: {e}",
            extra={"job_id": str(job_id), "date_range": date_range},
            exc_info=True
        )
        return []


async def get_user_analytics(
    user_id: UUID,
    date_range: str = "all"
) -> List[Dict]:
    """
    Get analytics records for a user across all jobs.
    
    Uses caching for performance.
    
    Args:
        user_id: User ID
        date_range: Date range filter ("all", "last_7_days", "last_30_days")
        
    Returns:
        List of analytics records
    """
    try:
        # Check cache
        cache_key = f"analytics:user:{user_id}:{date_range}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        # Query database
        query = db_client.table("regeneration_analytics").select("*").eq(
            "user_id", str(user_id)
        )
        
        # Apply date filter if specified
        if date_range == "last_7_days":
            cutoff_date = datetime.now() - timedelta(days=7)
            query = query.gte("created_at", cutoff_date.isoformat())
        elif date_range == "last_30_days":
            cutoff_date = datetime.now() - timedelta(days=30)
            query = query.gte("created_at", cutoff_date.isoformat())
        
        result = await query.order("created_at", desc=True).execute()
        data = result.data or []
        
        # Cache for 1 hour
        await redis_client.setex(
            cache_key,
            3600,
            json.dumps(data)
        )
        
        return data
        
    except Exception as e:
        logger.error(
            f"Failed to get user analytics: {e}",
            extra={"user_id": str(user_id), "date_range": date_range},
            exc_info=True
        )
        return []


async def invalidate_analytics_cache(job_id: Optional[UUID] = None, user_id: Optional[UUID] = None):
    """
    Invalidate analytics cache when new regeneration is tracked.
    
    Args:
        job_id: Job ID to invalidate cache for
        user_id: User ID to invalidate cache for
    """
    try:
        if job_id:
            # Invalidate all job-related cache keys
            patterns = [
                f"analytics:job:{job_id}:*",
                f"analytics:job:{job_id}:all",
                f"analytics:job:{job_id}:last_7_days",
                f"analytics:job:{job_id}:last_30_days",
                f"analytics:job:{job_id}:older_than_7_days"
            ]
            for pattern in patterns:
                # Note: Redis doesn't support wildcard delete directly
                # In production, use SCAN + DEL or maintain a set of cache keys
                # For now, we'll delete known patterns
                try:
                    await redis_client.delete(pattern.replace("*", "all"))
                    await redis_client.delete(pattern.replace("*", "last_7_days"))
                    await redis_client.delete(pattern.replace("*", "last_30_days"))
                    await redis_client.delete(pattern.replace("*", "older_than_7_days"))
                except Exception:
                    pass  # Key may not exist
        
        if user_id:
            # Invalidate user-related cache keys
            patterns = [
                f"analytics:user:{user_id}:all",
                f"analytics:user:{user_id}:last_7_days",
                f"analytics:user:{user_id}:last_30_days"
            ]
            for pattern in patterns:
                try:
                    await redis_client.delete(pattern)
                except Exception:
                    pass
        
        logger.debug(
            f"Invalidated analytics cache",
            extra={"job_id": str(job_id) if job_id else None, "user_id": str(user_id) if user_id else None}
        )
        
    except Exception as e:
        logger.warning(
            f"Failed to invalidate analytics cache: {e}",
            extra={"job_id": str(job_id) if job_id else None, "user_id": str(user_id) if user_id else None}
        )
        # Non-blocking: cache invalidation failure shouldn't break tracking

