#!/usr/bin/env python3
"""
Quick script to check worker status and queue information.
"""

import sys
import os
import asyncio

# Add project/backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "project", "backend"))

async def check_worker_status():
    """Check worker and queue status."""
    try:
        from shared.redis_client import RedisClient
        
        # Try to connect to Redis
        redis = RedisClient()
        await redis.client.ping()
        print("✅ Redis connection successful")
        
        # Check queue name (default to development)
        env = os.getenv('ENVIRONMENT', 'development')
        queue_name = f"video_generation_{env}"
        queue_key = f"{queue_name}:queue"
        processing_key = f"{queue_name}:processing"
        
        print(f"\n📋 Queue Information:")
        print(f"   Environment: {env}")
        print(f"   Queue Name: {queue_name}")
        print(f"   Queue Key: {queue_key}")
        print(f"   Processing Key: {processing_key}")
        
        # Check queue length
        queue_length = await redis.client.llen(queue_key)
        print(f"\n📊 Queue Status:")
        print(f"   Jobs waiting: {queue_length}")
        
        # Check processing set
        processing_count = await redis.client.scard(processing_key)
        if processing_count > 0:
            processing_jobs = await redis.client.smembers(processing_key)
            print(f"   Jobs processing: {processing_count}")
            for job_id in processing_jobs:
                job_id_str = job_id.decode() if isinstance(job_id, bytes) else job_id
                print(f"      - {job_id_str}")
        else:
            print(f"   Jobs processing: 0")
        
        # Check if worker is listening (by checking if queue is being consumed)
        # This is indirect - if jobs are being processed, worker is active
        if processing_count > 0 or queue_length > 0:
            print(f"\n✅ Worker appears to be active (jobs in queue or processing)")
        else:
            print(f"\n⚠️  No jobs in queue or processing - worker may be idle")
        
        await redis.client.aclose()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(check_worker_status())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

