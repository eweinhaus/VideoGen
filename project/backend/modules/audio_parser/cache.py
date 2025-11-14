"""
Redis caching utilities for audio analysis.

Cache audio analysis results by MD5 file hash with 24-hour TTL.
"""

import json
from typing import Optional
from datetime import datetime, timedelta

from shared.models.audio import AudioAnalysis
from shared.redis_client import redis
from shared.database import db
from shared.errors import RetryableError
from shared.logging import get_logger

logger = get_logger("audio_parser")


def _serialize_analysis(analysis: AudioAnalysis) -> dict:
    """
    Serialize AudioAnalysis to dict for storage.
    
    Args:
        analysis: AudioAnalysis model
        
    Returns:
        Dict representation
    """
    return analysis.model_dump(mode="json")


def _deserialize_analysis(data: dict) -> AudioAnalysis:
    """
    Deserialize dict to AudioAnalysis model.
    
    Args:
        data: Dict representation
        
    Returns:
        AudioAnalysis model
    """
    return AudioAnalysis(**data)


async def get_cached_analysis(file_hash: str) -> Optional[AudioAnalysis]:
    """
    Get cached audio analysis from Redis.
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        AudioAnalysis if found, None otherwise
        
    Raises:
        RetryableError: If cache read fails
    """
    try:
        cache_key = f"audio_cache:{file_hash}"
        cached_data = await redis.get_json(cache_key)
        
        if cached_data is None:
            logger.debug(f"Cache miss for file hash: {file_hash}")
            return None
        
        logger.info(f"Cache hit for file hash: {file_hash}")
        analysis = _deserialize_analysis(cached_data)
        return analysis
        
    except Exception as e:
        logger.warning(f"Failed to get cached analysis: {str(e)}", extra={"file_hash": file_hash})
        # Don't fail the request if cache read fails
        return None


async def store_cached_analysis(
    file_hash: str,
    analysis: AudioAnalysis,
    ttl: int = 86400
) -> None:
    """
    Store audio analysis in Redis cache and database.
    
    Args:
        file_hash: MD5 hash of audio file
        analysis: AudioAnalysis model to cache
        ttl: Time to live in seconds (default: 86400 = 24 hours)
        
    Raises:
        RetryableError: If cache write fails (non-fatal, logged as warning)
    """
    try:
        # Serialize analysis
        analysis_dict = _serialize_analysis(analysis)
        
        # Store in Redis
        cache_key = f"audio_cache:{file_hash}"
        await redis.set_json(cache_key, analysis_dict, ttl=ttl)
        logger.info(f"Stored analysis in Redis cache: {file_hash}")
        
        # Store in database
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        cache_record = {
            "file_hash": file_hash,
            "analysis_data": analysis_dict,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        # Upsert (insert or update if exists)
        await db.table("audio_analysis_cache").upsert(cache_record).execute()
        logger.info(f"Stored analysis in database cache: {file_hash}")
        
    except Exception as e:
        # Cache write failures should not fail the request
        logger.warning(
            f"Failed to store cached analysis: {str(e)}",
            extra={"file_hash": file_hash, "error": str(e)}
        )
        # Don't raise - caching is best-effort

