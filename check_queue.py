#!/usr/bin/env python3
"""Check Redis queue status."""
import sys
sys.path.insert(0, '/Users/mylessjs/Desktop/VideoGen/project/backend')

import asyncio
from shared.redis_client import RedisClient

async def main():
    redis_client = RedisClient()

    # Check queue length
    queue_len = await redis_client.client.llen("video_generation:queue")
    print(f"Queue length: {queue_len}")

    # Get all jobs in queue
    jobs = await redis_client.client.lrange("video_generation:queue", 0, -1)
    print(f"\nJobs in queue:")
    for job in jobs:
        print(f"  {job}")

    # Check if our specific job is there
    job_id = "74984f3d-295f-4278-89b0-8c34733867e2"
    is_in_queue = any(job_id.encode() in job for job in jobs)
    print(f"\nJob {job_id} in queue: {is_in_queue}")

if __name__ == "__main__":
    asyncio.run(main())
