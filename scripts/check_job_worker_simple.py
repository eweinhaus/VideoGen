#!/usr/bin/env python3
"""
Check which worker/environment is processing a job.
Uses direct Redis connection to avoid config requirements.
"""
import asyncio
import redis.asyncio as redis
import os
import sys

async def check_job_worker(job_id: str):
    """Check which queue/environment is processing a job."""
    # Get Redis URL from environment or use default
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Connect to Redis
    r = await redis.from_url(redis_url, decode_responses=False)
    
    print(f"Checking job: {job_id}\n")
    
    # Check all possible queue names (development, staging, production)
    environments = ["development", "staging", "production"]
    
    found = False
    for env in environments:
        queue_name = f"video_generation_{env}"
        queue_key = f"{queue_name}:queue"
        processing_key = f"{queue_name}:processing"
        
        # Check if job is in processing set
        is_processing = await r.sismember(processing_key, job_id.encode() if isinstance(job_id, str) else job_id)
        
        # Check queue length
        queue_length = await r.llen(queue_key)
        
        # Check if job data exists
        job_key = f"{queue_name}:job:{job_id}"
        job_exists = await r.exists(job_key)
        
        if is_processing or job_exists or queue_length > 0:
            found = True
            print(f"Environment: {env.upper()}")
            print(f"  Queue name: {queue_name}")
            print(f"  Job in processing set: {is_processing}")
            print(f"  Job data exists: {bool(job_exists)}")
            print(f"  Queue length: {queue_length}")
            
            if is_processing:
                print(f"  ✅ Job is currently being processed by a {env} worker")
            
            # Get all jobs in processing
            processing_jobs = await r.smembers(processing_key)
            if processing_jobs:
                decoded_jobs = [j.decode() if isinstance(j, bytes) else j for j in processing_jobs]
                print(f"  All jobs in processing: {decoded_jobs}")
            
            print()
    
    if not found:
        print("⚠️  Job not found in any queue or processing set.")
        print("   The job may have:")
        print("   - Already completed")
        print("   - Failed and been removed")
        print("   - Not been enqueued yet")
        print("   - Been processed by a different environment")
    
    print("\nNote: Workers don't currently log their hostname/instance ID.")
    print("To identify the worker:")
    print("  1. Queue name (environment) - shown above")
    print("  2. Check Railway deployment logs if deployed")
    print("  3. Check local worker process if running locally")
    print("  4. Check the ENVIRONMENT env var on the worker")
    
    await r.aclose()

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else "ea1dcef1-60a3-4267-a81c-ab3a8b2619c8"
    asyncio.run(check_job_worker(job_id))

