#!/usr/bin/env python3
"""
Clear all audio analysis cache entries.

Clears both Redis cache and database cache for audio analysis results.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'project', 'backend'))

from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger("clear_audio_cache")


async def clear_redis_cache():
    """Clear all audio cache entries from Redis."""
    try:
        redis_client = RedisClient()
        
        # Find all keys matching audio_cache pattern
        # RedisClient adds "videogen:cache:" prefix, so we search for that
        pattern = "videogen:cache:audio_cache:*"
        
        # Use SCAN to find all matching keys (more efficient than KEYS for large datasets)
        keys_to_delete = []
        cursor = 0
        
        while True:
            # SCAN returns (cursor, [keys])
            cursor, keys = await redis_client.client.scan(cursor, match=pattern, count=100)
            keys_to_delete.extend(keys)
            
            if cursor == 0:
                break
        
        # Also check for old double-prefixed keys (legacy bug)
        old_pattern = "videogen:cache:videogen:cache:audio_cache:*"
        cursor = 0
        while True:
            cursor, keys = await redis_client.client.scan(cursor, match=old_pattern, count=100)
            keys_to_delete.extend(keys)
            
            if cursor == 0:
                break
        
        if keys_to_delete:
            # Delete all keys at once
            deleted = await redis_client.client.delete(*keys_to_delete)
            logger.info(f"Cleared {deleted} audio cache entries from Redis")
            return deleted
        else:
            logger.info("No audio cache entries found in Redis")
            return 0
            
    except Exception as e:
        logger.error(f"Failed to clear Redis cache: {str(e)}")
        raise


async def clear_database_cache():
    """Clear all audio cache entries from database."""
    try:
        db = DatabaseClient()
        
        # Delete all entries from audio_analysis_cache table
        # Use a filter that matches all rows (file_hash is always present)
        result = await db.table("audio_analysis_cache").delete().gte("created_at", "1970-01-01").execute()
        
        # Supabase delete returns the deleted rows in data
        deleted_count = len(result.data) if result.data else 0
        logger.info(f"Cleared {deleted_count} audio cache entries from database")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to clear database cache: {str(e)}")
        raise


async def main():
    """Main function to clear all audio cache."""
    print("Clearing audio analysis cache...")
    print("=" * 50)
    
    try:
        # Clear Redis cache
        print("\n1. Clearing Redis cache...")
        redis_count = await clear_redis_cache()
        print(f"   ✓ Cleared {redis_count} entries from Redis")
        
        # Clear database cache
        print("\n2. Clearing database cache...")
        db_count = await clear_database_cache()
        print(f"   ✓ Cleared {db_count} entries from database")
        
        print("\n" + "=" * 50)
        print(f"✓ Successfully cleared audio cache!")
        print(f"  Total: {redis_count + db_count} entries cleared")
        
    except Exception as e:
        print(f"\n✗ Error clearing cache: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

