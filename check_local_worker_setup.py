#!/usr/bin/env python3
"""
Quick script to verify local worker setup.

Checks:
1. Environment variable
2. Queue name
3. Redis connection
4. Jobs in queue
"""

import asyncio
import sys
import os

# Add project/backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "project", "backend"))

try:
    from shared.config import Settings
    from shared.errors import ConfigError
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root and dependencies are installed.")
    sys.exit(1)

# Try to load settings, but handle missing env vars gracefully
try:
    settings = Settings()
except ConfigError as e:
    print(f"❌ Configuration error: {e}")
    print("\nMake sure you have a .env file in project/backend/ with required variables:")
    print("  - ENVIRONMENT=development")
    print("  - REDIS_URL=redis://localhost:6379")
    print("  - (and other required variables)")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error loading settings: {e}")
    print("\nMake sure you have a .env file in project/backend/ with all required variables.")
    sys.exit(1)

try:
    from shared.redis_client import RedisClient
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


async def check_setup():
    """Check local worker setup."""
    print("🔍 Checking Local Worker Setup\n")
    
    # 1. Check environment
    print(f"1. Environment: {settings.environment}")
    if settings.environment != "development":
        print(f"   ⚠️  Warning: Environment is '{settings.environment}', not 'development'")
        print("   → Local jobs should use ENVIRONMENT=development")
    else:
        print("   ✅ Environment is 'development'")
    
    # 2. Check queue name
    queue_name = settings.queue_name
    print(f"\n2. Queue Name: {queue_name}")
    expected_queue = "video_generation_development"
    if queue_name == expected_queue:
        print(f"   ✅ Queue name matches expected: {expected_queue}")
    else:
        print(f"   ⚠️  Queue name is '{queue_name}', expected '{expected_queue}'")
        print("   → Make sure ENVIRONMENT=development is set")
    
    # 3. Check Redis connection
    print(f"\n3. Redis URL: {settings.redis_url}")
    try:
        redis = RedisClient()
        await redis.client.ping()
        print("   ✅ Redis connection successful")
    except Exception as e:
        print(f"   ❌ Redis connection failed: {e}")
        print("   → Make sure Redis is running and REDIS_URL is correct")
        return
    
    # 4. Check queue length
    queue_key = f"{queue_name}:queue"
    try:
        length = await redis.client.llen(queue_key)
        print(f"\n4. Jobs in queue '{queue_key}': {length}")
        
        if length > 0:
            print(f"   ⚠️  There are {length} job(s) waiting in the queue")
            print("   → Make sure your worker is running to process them")
            
            # Show first job preview
            first_job = await redis.client.lindex(queue_key, 0)
            if first_job:
                try:
                    import json
                    job_data = json.loads(first_job)
                    job_id = job_data.get("job_id", "unknown")
                    print(f"   → First job ID: {job_id}")
                except:
                    print(f"   → First job (preview): {first_job[:100]}...")
        else:
            print("   ✅ Queue is empty (no jobs waiting)")
    except Exception as e:
        print(f"   ❌ Error checking queue: {e}")
    
    # 5. Check processing set
    processing_key = f"{queue_name}:processing"
    try:
        processing_count = await redis.client.scard(processing_key)
        if processing_count > 0:
            print(f"\n5. Jobs currently processing: {processing_count}")
            processing_jobs = await redis.client.smembers(processing_key)
            for job_id in processing_jobs:
                print(f"   → {job_id.decode() if isinstance(job_id, bytes) else job_id}")
        else:
            print("\n5. No jobs currently processing")
    except Exception as e:
        print(f"\n5. Error checking processing set: {e}")
    
    print("\n" + "="*50)
    print("Summary:")
    print(f"  Environment: {settings.environment}")
    print(f"  Queue: {queue_name}")
    print(f"  Redis: {'✅ Connected' if 'redis' in locals() else '❌ Not connected'}")
    print("\nTo start your worker:")
    print("  cd project/backend")
    print("  python -m api_gateway.worker")


if __name__ == "__main__":
    try:
        asyncio.run(check_setup())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

