"""
Check and fix a specific job - verify Redis queue status and fix state mismatches.
"""
import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger(__name__)
db_client = DatabaseClient()
redis_client = RedisClient()


async def check_and_fix_job(job_id: str, fix: bool = False):
    """Check a specific job and fix any state mismatches."""
    print(f"\n{'='*80}")
    print(f"Checking Job: {job_id}")
    print(f"{'='*80}\n")
    
    # Get job from database
    result = await db_client.table("jobs").select("*").eq("id", job_id).single().execute()
    
    if not result.data:
        print(f"❌ Job {job_id} NOT found in database")
        return
    
    job = result.data
    status = job.get('status')
    current_stage = job.get('current_stage', 'N/A')
    progress = job.get('progress', 0)
    updated_at_str = job.get('updated_at')
    error_message = job.get('error_message')
    
    print("📋 DATABASE STATUS")
    print("-" * 80)
    print(f"Status: {status}")
    print(f"Current Stage: {current_stage}")
    print(f"Progress: {progress}%")
    print(f"Updated: {updated_at_str}")
    if error_message:
        print(f"Error: {error_message}")
    print()
    
    # Check Redis queue status
    env = os.getenv('ENVIRONMENT', 'development')
    queue_name = f"video_generation_{env}"
    queue_key = f"{queue_name}:queue"
    processing_key = f"{queue_name}:processing"
    job_data_key = f"{queue_name}:job:{job_id}"
    
    print("🔍 REDIS QUEUE STATUS")
    print("-" * 80)
    print(f"Environment: {env}")
    print(f"Queue: {queue_name}")
    
    # Check if in queue
    queue_size = await redis_client.client.llen(queue_key)
    is_in_queue = False
    queue_position = None
    
    if queue_size > 0:
        queue_items = await redis_client.client.lrange(queue_key, 0, -1)
        for idx, item in enumerate(queue_items):
            try:
                item_data = json.loads(item)
                if item_data.get('job_id') == job_id:
                    is_in_queue = True
                    queue_position = idx + 1
                    break
            except:
                pass
    
    # Check if in processing set
    is_processing = await redis_client.client.sismember(processing_key, job_id)
    
    # Check if job data exists
    job_data_exists = await redis_client.client.exists(job_data_key)
    
    print(f"Queue size: {queue_size}")
    print(f"In queue: {is_in_queue}")
    if is_in_queue:
        print(f"Queue position: {queue_position}")
    print(f"In processing set: {is_processing}")
    print(f"Job data exists: {bool(job_data_exists)}")
    print()
    
    # Diagnose issues
    issues = []
    fixes_needed = []
    
    if status == "queued":
        if not is_in_queue and not is_processing:
            issues.append("Job status is 'queued' but NOT in Redis queue or processing set")
            fixes_needed.append("Re-queue job or mark as failed")
        elif is_processing:
            issues.append("Job status is 'queued' but is in processing set (state mismatch)")
            fixes_needed.append("Remove from processing set or update status to 'processing'")
    elif status == "processing":
        if not is_processing and not is_in_queue:
            issues.append("Job status is 'processing' but NOT in Redis processing set or queue")
            fixes_needed.append("Mark as failed or re-queue")
        elif is_in_queue:
            issues.append("Job status is 'processing' but is still in queue (state mismatch)")
            fixes_needed.append("Remove from queue or update status to 'queued'")
    
    # Check if stuck (updated more than 30 minutes ago)
    is_stuck = False
    if updated_at_str:
        try:
            updated = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
            now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
            age_minutes = (now - updated).total_seconds() / 60
            
            print("⏱️  TIME ANALYSIS")
            print("-" * 80)
            print(f"Last Updated: {age_minutes:.1f} minutes ago")
            
            if status in ["queued", "processing"] and age_minutes > 30:
                is_stuck = True
                issues.append(f"Job hasn't updated in {age_minutes:.1f} minutes (>30 min threshold)")
                fixes_needed.append("Mark as failed")
            print()
        except Exception as e:
            print(f"⚠️  Could not calculate age: {e}")
            print()
    
    # Print diagnosis
    print("📝 DIAGNOSIS")
    print("-" * 80)
    
    if not issues:
        print("✅ No issues detected - job state is consistent")
    else:
        print("⚠️  Issues detected:")
        for issue in issues:
            print(f"   - {issue}")
        print()
        print("🔧 Fixes needed:")
        for fix_needed in fixes_needed:
            print(f"   - {fix_needed}")
        print()
    
    # Apply fixes if requested
    if fix and (issues or is_stuck):
        print("🔧 APPLYING FIXES")
        print("-" * 80)
        
        if status == "queued" and not is_in_queue and not is_processing:
            # Job should be in queue but isn't - mark as failed
            print(f"Marking job as failed (not in queue)...")
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": "Job was queued but not found in Redis queue - state mismatch fixed"
            }).eq("id", job_id).execute()
            print("✅ Job marked as failed")
        
        elif status == "processing" and not is_processing and not is_in_queue:
            # Job should be processing but isn't - mark as failed
            print(f"Marking job as failed (not in processing set)...")
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": "Job was processing but not found in Redis processing set - state mismatch fixed"
            }).eq("id", job_id).execute()
            print("✅ Job marked as failed")
        
        elif is_stuck:
            # Job is stuck - mark as failed
            print(f"Marking stuck job as failed...")
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": f"Job stuck in {status} status for >30 minutes - marked as failed by cleanup script"
            }).eq("id", job_id).execute()
            print("✅ Job marked as failed")
        
        elif status == "queued" and is_processing:
            # Remove from processing set
            print(f"Removing job from processing set (state mismatch)...")
            await redis_client.client.srem(processing_key, job_id)
            print("✅ Removed from processing set")
        
        elif status == "processing" and is_in_queue:
            # Remove from queue
            print(f"Removing job from queue (state mismatch)...")
            # Need to find and remove the specific item
            queue_items = await redis_client.client.lrange(queue_key, 0, -1)
            for item in queue_items:
                try:
                    item_data = json.loads(item)
                    if item_data.get('job_id') == job_id:
                        await redis_client.client.lrem(queue_key, 1, item)
                        print("✅ Removed from queue")
                        break
                except:
                    pass
        
        print()
        print("✅ Fixes applied")
    elif fix:
        print("✅ No fixes needed - job state is consistent")
    
    print()


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python check_and_fix_job.py <job_id> [--fix]")
        sys.exit(1)
    
    job_id = sys.argv[1]
    fix = "--fix" in sys.argv or "-f" in sys.argv
    
    if fix:
        print("⚠️  WARNING: This will modify job state if issues are found!")
        print()
    
    await check_and_fix_job(job_id, fix=fix)
    
    await redis_client.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

