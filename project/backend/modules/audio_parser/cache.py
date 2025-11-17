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

# Cache version - increment this to invalidate all cached results
# Version 2: Updated clip boundaries from 4-8s to 3-7s range
# Version 3: Fixed clip boundary gaps - clips now start exactly where previous clip ends
CACHE_VERSION = 3


async def get_cached_analysis(file_hash: str) -> Optional[AudioAnalysis]:
    """
    Get cached analysis by file hash.
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        AudioAnalysis if found, None otherwise
    """
    try:
        # Note: RedisClient adds "videogen:cache:" prefix automatically
        cache_key = f"audio_cache:v{CACHE_VERSION}:{file_hash}"
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
        # Note: RedisClient adds "videogen:cache:" prefix automatically
        cache_key = f"audio_cache:v{CACHE_VERSION}:{file_hash}"
        cached_data = analysis.model_dump_json()
        await redis_client.set(cache_key, cached_data, ex=ttl)
        logger.info(f"Stored analysis in cache: {file_hash} (version {CACHE_VERSION})")
    except Exception as e:
        logger.warning(f"Failed to store cached analysis: {str(e)}")
        # Cache failures should not fail the request


async def clear_cached_analysis(file_hash: str) -> bool:
    """
    Clear a specific cached analysis by file hash.
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        True if entry was found and deleted, False otherwise
    """
    try:
        # Note: RedisClient adds "videogen:cache:" prefix automatically
        # But we also need to check for old double-prefixed keys (legacy bug)
        
        # Try current version (correct format)
        cache_key = f"audio_cache:v{CACHE_VERSION}:{file_hash}"
        deleted = await redis_client.delete(cache_key)
        
        if deleted:
            logger.info(f"Cleared cache entry: {file_hash} (version {CACHE_VERSION})")
            return True
        
        # Try old double-prefixed format (legacy bug - direct client access)
        old_double_prefixed = f"videogen:cache:videogen:cache:audio_cache:v{CACHE_VERSION}:{file_hash}"
        deleted = await redis_client.client.delete(old_double_prefixed)
        
        if deleted:
            logger.info(f"Cleared cache entry (legacy double-prefixed): {file_hash}")
            return True
        
        # Try old format (no version, double-prefixed)
        old_cache_key = f"videogen:cache:videogen:cache:audio_cache:{file_hash}"
        deleted = await redis_client.client.delete(old_cache_key)
        
        if deleted:
            logger.info(f"Cleared cache entry (old format, double-prefixed): {file_hash}")
            return True
        
        # Try other versions (double-prefixed)
        for version in range(1, CACHE_VERSION):
            version_key = f"videogen:cache:videogen:cache:audio_cache:v{version}:{file_hash}"
            deleted = await redis_client.client.delete(version_key)
            if deleted:
                logger.info(f"Cleared cache entry (version {version}, double-prefixed): {file_hash}")
                return True
        
        logger.debug(f"No cache entry found for hash: {file_hash}")
        return False
        
    except Exception as e:
        logger.warning(f"Failed to clear cached analysis: {str(e)}")
        return False
