#!/usr/bin/env python3
"""
Clear a specific audio parser cache entry from Redis.

Usage:
    python clear_specific_audio_cache.py <file_hash>
    python clear_specific_audio_cache.py --url <audio_url>
    python clear_specific_audio_cache.py --all  # Clear all entries
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.redis_client import RedisClient
from shared.logging import get_logger
from modules.audio_parser.utils import calculate_file_hash, download_audio_file
from modules.audio_parser.cache import CACHE_VERSION

logger = get_logger("clear_specific_audio_cache")


async def clear_cache_by_hash(file_hash: str) -> bool:
    """
    Clear a specific audio cache entry by file hash.
    
    Args:
        file_hash: MD5 hash of the audio file
        
    Returns:
        True if entry was found and deleted, False otherwise
    """
    redis_client = RedisClient()
    
    try:
        # Check connection
        if not await redis_client.health_check():
            logger.error("Failed to connect to Redis")
            raise ConnectionError("Failed to connect to Redis")
        
        # Try current version first
        cache_key = f"videogen:cache:audio_cache:v{CACHE_VERSION}:{file_hash}"
        deleted = await redis_client.client.delete(cache_key)
        
        if deleted:
            logger.info(f"✅ Deleted cache entry: {cache_key}")
            return True
        
        # Try old format (no version)
        old_cache_key = f"videogen:cache:audio_cache:{file_hash}"
        deleted = await redis_client.client.delete(old_cache_key)
        
        if deleted:
            logger.info(f"✅ Deleted cache entry (old format): {old_cache_key}")
            return True
        
        # Try other versions
        for version in range(1, CACHE_VERSION):
            version_key = f"videogen:cache:audio_cache:v{version}:{file_hash}"
            deleted = await redis_client.client.delete(version_key)
            if deleted:
                logger.info(f"✅ Deleted cache entry (version {version}): {version_key}")
                return True
        
        logger.warning(f"⚠️  No cache entry found for hash: {file_hash}")
        return False
        
    except Exception as e:
        logger.error(f"Failed to clear cache entry: {str(e)}")
        raise
    finally:
        await redis_client.close()


async def clear_cache_by_url(audio_url: str) -> bool:
    """
    Clear audio cache entry by downloading the file and calculating its hash.
    
    Args:
        audio_url: URL of the audio file
        
    Returns:
        True if entry was found and deleted, False otherwise
    """
    try:
        logger.info(f"Downloading audio file from URL to calculate hash...")
        audio_bytes = await download_audio_file(audio_url)
        file_hash = calculate_file_hash(audio_bytes)
        logger.info(f"Calculated hash: {file_hash}")
        return await clear_cache_by_hash(file_hash)
    except Exception as e:
        logger.error(f"Failed to clear cache by URL: {str(e)}")
        raise


async def clear_all_cache() -> int:
    """
    Clear all audio parser cache entries from Redis.
    
    Returns:
        Number of entries deleted
    """
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
    parser = argparse.ArgumentParser(
        description="Clear specific or all audio parser cache entries"
    )
    parser.add_argument(
        "file_hash",
        nargs="?",
        help="MD5 hash of the audio file to clear from cache"
    )
    parser.add_argument(
        "--url",
        help="Audio file URL (will download and calculate hash)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clear all audio cache entries"
    )
    
    args = parser.parse_args()
    
    try:
        if args.all:
            print("Clearing all audio parser cache entries...")
            count = await clear_all_cache()
            print(f"✅ Successfully cleared {count} cache entries")
            return 0
        elif args.url:
            print(f"Clearing cache for audio URL: {args.url}")
            success = await clear_cache_by_url(args.url)
            if success:
                print("✅ Successfully cleared cache entry")
                return 0
            else:
                print("⚠️  No cache entry found for this URL")
                return 1
        elif args.file_hash:
            print(f"Clearing cache for hash: {args.file_hash}")
            success = await clear_cache_by_hash(args.file_hash)
            if success:
                print("✅ Successfully cleared cache entry")
                return 0
            else:
                print("⚠️  No cache entry found for this hash")
                return 1
        else:
            parser.print_help()
            return 1
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

