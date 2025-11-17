"""
Utility script to check and clear Redis queue.

Usage:
    cd project/backend
    source venv/bin/activate
    python check_queue.py [--clear]
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.redis_client import RedisClient
from shared.logging import get_logger
from shared.config import settings

logger = get_logger(__name__)
redis_client = RedisClient()


async def check_queue(clear: bool = False):
    """Check and optionally clear the queue."""
    # Use environment-aware queue name
    queue_name = settings.queue_name
    queue_key = f"{queue_name}:queue"
    
    try:
        length = await redis_client.client.llen(queue_key)
        print(f"\n{'='*60}")
        print(f"Queue Status: {length} job(s) in queue")
        print(f"{'='*60}\n")
        
        if length == 0:
            print("✅ Queue is empty - no jobs to process")
            return
        
        # Get all jobs
        jobs = await redis_client.client.lrange(queue_key, 0, -1)
        
        print(f"Found {len(jobs)} job(s):\n")
        for i, job_json in enumerate(jobs, 1):
            try:
                job_data = json.loads(job_json)
                job_id = job_data.get('job_id', 'unknown')
                created_at = job_data.get('created_at', 'unknown')
                stop_at_stage = job_data.get('stop_at_stage')
                
                # Parse created_at to show age
                age_str = "unknown"
                if created_at != "unknown":
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        age = datetime.now(created_dt.tzinfo) - created_dt
                        age_str = f"{age.total_seconds():.0f} seconds ago"
                    except:
                        age_str = created_at
                
                print(f"  [{i}] Job ID: {job_id}")
                print(f"      Created: {created_at} ({age_str})")
                if stop_at_stage:
                    print(f"      Stop at stage: {stop_at_stage}")
                print()
                
            except Exception as e:
                print(f"  [{i}] ⚠️  Invalid job data: {str(e)[:100]}")
                print()
        
        if clear:
            print(f"\n{'='*60}")
            print("⚠️  CLEARING QUEUE...")
            print(f"{'='*60}\n")
            
            cleared = await redis_client.client.delete(queue_key)
            if cleared:
                print(f"✅ Cleared {length} job(s) from queue")
            else:
                print("⚠️  Queue was already empty or couldn't be cleared")
        else:
            print(f"\n💡 To clear the queue, run: python check_queue.py --clear")
            print(f"   Or manually: redis-cli DEL video_generation:queue")
        
    except Exception as e:
        print(f"❌ Error checking queue: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def main():
    """Main entry point."""
    clear = "--clear" in sys.argv or "-c" in sys.argv
    
    if clear:
        print("\n⚠️  WARNING: This will clear all jobs from the queue!")
        response = input("Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            return
    
    await check_queue(clear=clear)


if __name__ == "__main__":
    asyncio.run(main())

