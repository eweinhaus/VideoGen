"""
Caching utilities for audio parser.

Redis-based caching for audio analysis results.
"""

from typing import Optional
from shared.redis_client import RedisClient
from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

logger = get_logger("audio_parser")

redis_client = RedisClient()


async def get_cached_analysis(file_hash: str) -> Optional[AudioAnalysis]:
    """
    Get cached analysis by file hash.
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        AudioAnalysis if found, None otherwise
    """
    try:
        cache_key = f"videogen:cache:audio_cache:{file_hash}"
        cached_data = await redis_client.get(cache_key)
        
        if cached_data:
            # Parse JSON string to AudioAnalysis model
            return AudioAnalysis.model_validate_json(cached_data)
        return None
    except Exception as e:
        logger.warning(f"Failed to get cached analysis: {str(e)}")
        # Cache failures should not fail the request
        return None


async def store_cached_analysis(file_hash: str, analysis: AudioAnalysis, ttl: int = 86400):
    """
    Store analysis in cache.
    
    Args:
        file_hash: MD5 hash of audio file
        analysis: AudioAnalysis object to cache
        ttl: Time to live in seconds (default: 86400 = 24 hours)
    """
    try:
        cache_key = f"videogen:cache:audio_cache:{file_hash}"
        cached_data = analysis.model_dump_json()
        await redis_client.set(cache_key, cached_data, ttl=ttl)
        logger.info(f"Stored analysis in cache: {file_hash}")
    except Exception as e:
        logger.warning(f"Failed to store cached analysis: {str(e)}")
        # Cache failures should not fail the request
