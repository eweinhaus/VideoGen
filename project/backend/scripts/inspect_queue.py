#!/usr/bin/env python3
"""
Inspect Redis queue directly to see what's in it.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.redis_client import RedisClient
from api_gateway.services.queue_service import QUEUE_NAME

async def inspect_queue():
    """Inspect the queue directly."""
    redis_client = RedisClient()
    queue_key = f"{QUEUE_NAME}:queue"
    
    print(f"Inspecting queue: {queue_key}")
    print("=" * 80)
    
    # Check queue length
    length = await redis_client.client.llen(queue_key)
    print(f"Queue length: {length}")
    
    # Get all items in queue
    if length > 0:
        items = await redis_client.client.lrange(queue_key, 0, -1)
        print(f"\nFound {len(items)} items in queue:")
        for i, item in enumerate(items):
            print(f"\nItem {i+1}:")
            if isinstance(item, bytes):
                try:
                    decoded = item.decode('utf-8')
                    print(f"  Raw (decoded): {decoded[:100]}...")
                    try:
                        parsed = json.loads(decoded)
                        print(f"  Parsed: job_id={parsed.get('job_id')}, user_id={parsed.get('user_id')}")
                    except json.JSONDecodeError:
                        print(f"  (Not valid JSON)")
                except UnicodeDecodeError:
                    print(f"  Raw (bytes): {item[:50]}...")
            else:
                print(f"  Raw: {item[:100]}...")
    else:
        print("\nQueue is empty")
    
    # Check for similar keys
    print("\n" + "=" * 80)
    print("Checking for similar keys...")
    try:
        # Try to find keys matching the pattern
        pattern = f"{QUEUE_NAME}*"
        keys = []
        async for key in redis_client.client.scan_iter(match=pattern):
            if isinstance(key, bytes):
                keys.append(key.decode('utf-8'))
            else:
                keys.append(key)
        
        if keys:
            print(f"Found {len(keys)} keys matching '{pattern}':")
            for key in keys:
                key_type = await redis_client.client.type(key)
                if isinstance(key_type, bytes):
                    key_type = key_type.decode('utf-8')
                print(f"  - {key} (type: {key_type})")
        else:
            print(f"No keys found matching '{pattern}'")
    except Exception as e:
        print(f"Error scanning keys: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_queue())

