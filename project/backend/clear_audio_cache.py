#!/usr/bin/env python3
"""
Clear audio parser cache from Redis.

This script deletes all audio parser cache entries from Redis.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger("clear_audio_cache")


async def clear_audio_cache():
    """Clear all audio parser cache entries from Redis."""
    redis_client = RedisClient()
    
    try:
        # Check connection
        if not await redis_client.health_check():
            logger.error("Failed to connect to Redis")
            raise ConnectionError("Failed to connect to Redis")
        
        logger.info("Connected to Redis, scanning for audio cache keys...")
        
        # Get the underlying Redis client to use SCAN
        client = redis_client.client
        
        # Pattern to match all audio cache keys (old and new versions)
        # Note: RedisClient adds "videogen:cache:" prefix automatically
        # But we also need to check for old double-prefixed keys (legacy bug)
        patterns = [
            "videogen:cache:audio_cache:*",  # Correct format (single prefix)
            "videogen:cache:audio_cache:v*:*",  # Correct format with version
            "videogen:cache:videogen:cache:audio_cache:*",  # Legacy double-prefixed (bug)
            "videogen:cache:videogen:cache:audio_cache:v*:*",  # Legacy double-prefixed with version
        ]
        
        total_deleted = 0
        
        for pattern in patterns:
            logger.info(f"Scanning for keys matching pattern: {pattern}")
            deleted_count = 0
            
            # Use SCAN to iterate through keys (more efficient than KEYS for large datasets)
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                
                if keys:
                    # Delete all keys in batch
                    deleted = await client.delete(*keys)
                    deleted_count += deleted
                    logger.info(f"Deleted {deleted} keys (pattern: {pattern})")
                
                if cursor == 0:
                    break
            
            total_deleted += deleted_count
            logger.info(f"Pattern '{pattern}': deleted {deleted_count} keys")
        
        logger.info(f"✅ Cleared audio parser cache: {total_deleted} entries deleted")
        return total_deleted
        
    except Exception as e:
        logger.error(f"Failed to clear audio cache: {str(e)}")
        raise
    finally:
        await redis_client.close()


async def main():
    """Main entry point."""
    print("Clearing audio parser cache...")
    try:
        count = await clear_audio_cache()
        print(f"✅ Successfully cleared {count} cache entries")
        return 0
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
