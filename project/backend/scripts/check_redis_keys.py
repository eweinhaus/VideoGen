#!/usr/bin/env python3
"""
Check what audio cache keys actually exist in Redis.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger("check_redis_keys")


async def check_keys():
    """Check what keys exist in Redis."""
    redis_client = RedisClient()
    
    try:
        if not await redis_client.health_check():
            logger.error("Failed to connect to Redis")
            raise ConnectionError("Failed to connect to Redis")
        
        client = redis_client.client
        
        # Check various patterns
        patterns = [
            "videogen:cache:*",  # All cache keys
            "videogen:cache:audio_cache:*",  # Old format
            "videogen:cache:audio_cache:v*:*",  # Versioned format
            "videogen:cache:videogen:cache:audio_cache:*",  # Double-prefixed (if bug exists)
        ]
        
        for pattern in patterns:
            print(f"\n🔍 Scanning pattern: {pattern}")
            cursor = 0
            keys_found = []
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    # Decode keys if they're bytes
                    decoded_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
                    keys_found.extend(decoded_keys)
                if cursor == 0:
                    break
            
            if keys_found:
                print(f"  ✅ Found {len(keys_found)} keys")
                for key in keys_found[:10]:  # Show first 10
                    print(f"    - {key}")
                if len(keys_found) > 10:
                    print(f"    ... and {len(keys_found) - 10} more")
            else:
                print(f"  ❌ No keys found")
        
        # Also check ALL keys with "audio" in them
        print(f"\n🔍 Scanning for any keys containing 'audio'...")
        cursor = 0
        audio_keys = []
        while True:
            cursor, keys = await client.scan(cursor, match="*audio*", count=100)
            if keys:
                decoded_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
                audio_keys.extend(decoded_keys)
            if cursor == 0:
                break
        
        if audio_keys:
            print(f"  ✅ Found {len(audio_keys)} keys with 'audio'")
            for key in audio_keys[:20]:  # Show first 20
                print(f"    - {key}")
            if len(audio_keys) > 20:
                print(f"    ... and {len(audio_keys) - 20} more")
        else:
            print(f"  ❌ No keys with 'audio' found")
        
    except Exception as e:
        logger.error(f"Failed to check keys: {str(e)}")
        raise
    finally:
        await redis_client.close()


async def main():
    """Main entry point."""
    print("Checking Redis keys...")
    try:
        await check_keys()
        return 0
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

