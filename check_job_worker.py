#!/usr/bin/env python3
"""
Check which worker/environment is processing a job.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'project', 'backend'))

from shared.redis_client import RedisClient

async def check_job_worker(job_id: str):
    """Check which queue/environment is processing a job."""
    redis = RedisClient()
    
    # Check all possible queue names (development, staging, production)
    environments = ["development", "staging", "production"]
    
    print(f"Checking job: {job_id}\n")
    
    for env in environments:
        queue_name = f"video_generation_{env}"
        queue_key = f"{queue_name}:queue"
        processing_key = f"{queue_name}:processing"
        
        # Check if job is in processing set
        is_processing = await redis.client.sismember(processing_key, job_id)
        
        # Check queue length
        queue_length = await redis.client.llen(queue_key)
        
        # Check if job data exists
        job_key = f"{queue_name}:job:{job_id}"
        job_exists = await redis.client.exists(job_key)
        
        if is_processing or job_exists or queue_length > 0:
            print(f"Environment: {env.upper()}")
            print(f"  Queue name: {queue_name}")
            print(f"  Job in processing set: {is_processing}")
            print(f"  Job data exists: {bool(job_exists)}")
            print(f"  Queue length: {queue_length}")
            
            if is_processing:
                print(f"  ✅ Job is currently being processed by a {env} worker")
            
            # Get all jobs in processing
            processing_jobs = await redis.client.smembers(processing_key)
            if processing_jobs:
                print(f"  All jobs in processing: {[j.decode() if isinstance(j, bytes) else j for j in processing_jobs]}")
            
            print()
    
    # Also check for custom queue name override
    # This would require checking Redis for any keys matching the pattern
    print("Note: Workers don't currently log their hostname/instance ID.")
    print("You can identify the worker by:")
    print("  1. Queue name (environment) - shown above")
    print("  2. Check Railway logs if deployed")
    print("  3. Check local worker logs if running locally")

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else "ea1dcef1-60a3-4267-a81c-ab3a8b2619c8"
    asyncio.run(check_job_worker(job_id))

