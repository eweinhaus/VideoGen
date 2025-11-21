#!/usr/bin/env python3
"""
Check if uploaded_character_images was in the queue data for job fdde43cf-b811-4b7f-8143-ed6aecd8f19e
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / "project" / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "project" / "backend"))

from redis import asyncio as aioredis

async def check_queue():
    job_id = "fdde43cf-b811-4b7f-8143-ed6aecd8f19e"
    
    # Get Redis connection
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("ERROR: REDIS_URL not found")
        return
    
    redis = await aioredis.from_url(redis_url, decode_responses=False)
    
    print(f"=== CHECKING REDIS QUEUE DATA FOR JOB {job_id} ===\n")
    
    # Check if job data exists in Redis (job data has 15 min TTL, so likely expired)
    job_data_key = f"video_generation:job:{job_id}"
    job_data = await redis.get(job_data_key)
    
    if job_data:
        print(f"✓ Job data found in Redis (key: {job_data_key})")
        import json
        try:
            job_dict = json.loads(job_data.decode('utf-8'))
            print(f"\nJob Data Keys: {list(job_dict.keys())}")
            
            if "uploaded_character_images" in job_dict:
                print(f"\n✓ uploaded_character_images FOUND in job data")
                print(f"   Value: {job_dict['uploaded_character_images']}")
            else:
                print(f"\n✗ uploaded_character_images NOT FOUND in job data")
                print(f"\n   This means the image was never uploaded or never added to the job queue.")
        except Exception as e:
            print(f"ERROR parsing job data: {e}")
    else:
        print(f"✗ Job data not found in Redis (key: {job_data_key})")
        print(f"   This is expected if job completed > 15 minutes ago (TTL expired)")
        print(f"\n   Checking logs instead...")
    
    await redis.close()
    
    print(f"\n=== CONCLUSION ===")
    print(f"\nSince the job data has expired from Redis, we need to check:")
    print(f"1. Did you actually upload a character image with this job?")
    print(f"2. Check the upload logs (backend logs) for job {job_id}")
    print(f"3. Search for log entries with 'character_image' or 'uploaded_character'")

if __name__ == "__main__":
    asyncio.run(check_queue())

