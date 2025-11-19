#!/usr/bin/env python3
"""
Monitor job queue and worker status.

Shows:
- Queue size (jobs waiting)
- Active jobs (currently processing)
- Recent job activity
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)
redis_client = RedisClient()
db_client = DatabaseClient()

QUEUE_NAME = "video_generation"


async def get_queue_status():
    """Get current queue status."""
    queue_key = f"{QUEUE_NAME}:queue"
    processing_key = f"{QUEUE_NAME}:processing"
    
    try:
        queue_size = await redis_client.client.llen(queue_key)
        processing_jobs = await redis_client.client.smembers(processing_key)
        processing_count = len(processing_jobs) if processing_jobs else 0
        
        # Get job IDs from processing set
        processing_job_ids = []
        if processing_jobs:
            for job_id_bytes in processing_jobs:
                if isinstance(job_id_bytes, bytes):
                    processing_job_ids.append(job_id_bytes.decode('utf-8'))
                else:
                    processing_job_ids.append(str(job_id_bytes))
        
        return {
            "queue_size": queue_size,
            "processing_count": processing_count,
            "processing_jobs": processing_job_ids
        }
    except Exception as e:
        logger.error("Failed to get queue status", exc_info=e)
        return {
            "queue_size": 0,
            "processing_count": 0,
            "processing_jobs": []
        }


async def get_recent_jobs(limit=10):
    """Get recent jobs from database."""
    try:
        result = await db_client.table("jobs").select("*").order("created_at", desc=True).limit(limit).execute()
        jobs = result.data if result.data else []
        return jobs
    except Exception as e:
        logger.error("Failed to get recent jobs", exc_info=e)
        return []


async def main():
    """Main monitoring loop."""
    print("=" * 60)
    print("Job Queue & Worker Monitor")
    print("=" * 60)
    print()
    
    queue_status = await get_queue_status()
    print(f"📊 Queue Status:")
    print(f"   Queue Size (waiting): {queue_status['queue_size']}")
    print(f"   Processing: {queue_status['processing_count']}")
    
    if queue_status['processing_jobs']:
        print(f"\n   Active Jobs:")
        for job_id in queue_status['processing_jobs']:
            print(f"     - {job_id}")
    
    print()
    print(f"📋 Recent Jobs (last 10):")
    recent_jobs = await get_recent_jobs(10)
    
    if not recent_jobs:
        print("   No jobs found")
    else:
        for job in recent_jobs:
            status_icon = {
                "queued": "⏳",
                "processing": "🔄",
                "completed": "✅",
                "failed": "❌"
            }.get(job.get("status"), "❓")
            
            print(f"   {status_icon} {job.get('id', 'unknown')[:8]}... | "
                  f"Status: {job.get('status', 'unknown')} | "
                  f"Progress: {job.get('progress', 0)}% | "
                  f"Stage: {job.get('current_stage', 'N/A')}")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

