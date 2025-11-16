"""
Clear audio parser cache from Redis.

This script deletes all audio parser cache entries from Redis.
"""

import asyncio
import sys
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger("clear_audio_cache")


async def clear_audio_cache():
    """Clear all audio parser cache entries from Redis."""
    redis_client = RedisClient()
    
    try:
        # Pattern to match all audio cache keys
        pattern = "videogen:cache:audio_cache:*"
        
        # Use SCAN to find all matching keys
        deleted_count = 0
        cursor = 0
        
        logger.info(f"Scanning for keys matching pattern: {pattern}")
        
        while True:
            # Use raw redis client to access SCAN
            cursor, keys = await redis_client.client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            
            if keys:
                # Delete all matching keys
                deleted = await redis_client.client.delete(*keys)
                deleted_count += deleted
                logger.info(f"Deleted {deleted} keys (total: {deleted_count})")
            
            # If cursor is 0, we've scanned all keys
            if cursor == 0:
                break
        
        logger.info(f"✅ Cleared audio parser cache: {deleted_count} entries deleted")
        return deleted_count
        
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

