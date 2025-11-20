#!/usr/bin/env python3
"""
Check the status of a specific job in detail.
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project/backend to path
project_root = Path(__file__).parent
backend_path = project_root / 'project' / 'backend'
sys.path.insert(0, str(backend_path))

from shared.database import DatabaseClient
import json

async def check_job(job_id: str):
    """Check detailed status of a job."""
    db_client = DatabaseClient()
    
    print(f"\n{'='*80}")
    print(f"Checking Job: {job_id}")
    print(f"{'='*80}\n")
    
    # Get job status
    result = await db_client.table("jobs").select("*").eq("id", job_id).single().execute()
    
    if not result.data:
        print(f"❌ Job {job_id} NOT found in database")
        return
    
    job = result.data
    print("📋 JOB STATUS")
    print("-" * 80)
    print(f"ID: {job['id']}")
    print(f"Status: {job.get('status', 'unknown')}")
    print(f"Progress: {job.get('progress', 0)}%")
    print(f"Current Stage: {job.get('current_stage', 'N/A')}")
    print(f"Total Cost: ${job.get('total_cost', 0)}")
    print(f"Created: {job.get('created_at')}")
    print(f"Updated: {job.get('updated_at')}")
    if job.get('completed_at'):
        print(f"Completed: {job.get('completed_at')}")
    if job.get('error_message'):
        print(f"❌ Error: {job.get('error_message')}")
    print()
    
    # Check job_stages
    stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).order("created_at").execute()
    if stages_result.data:
        print("📊 STAGE STATUS")
        print("-" * 80)
        for stage in stages_result.data:
            stage_name = stage.get("stage_name")
            stage_status = stage.get("status", "unknown")
            duration = stage.get("duration_seconds")
            created = stage.get("created_at")
            updated = stage.get("updated_at")
            
            status_icon = "✅" if stage_status == "completed" else "❌" if stage_status == "failed" else "⏳"
            print(f"{status_icon} {stage_name}: {stage_status}" + (f" ({duration}s)" if duration else ""))
            if created:
                print(f"   Created: {created}")
            if updated:
                print(f"   Updated: {updated}")
            
            # Show error if failed
            if stage_status == "failed" and stage.get("metadata"):
                metadata = stage.get("metadata")
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        pass
                if isinstance(metadata, dict) and metadata.get("error"):
                    print(f"   Error: {metadata.get('error')}")
        print()
    else:
        print("⚠️  No stages found for this job")
        print()
    
    # Check if job is in queue
    try:
        from shared.redis_client import RedisClient
        redis_client = RedisClient()
        queue_key = "video_generation:queue"
        processing_key = "video_generation:processing"
        
        # Check if in queue
        queue_size = await redis_client.client.llen(queue_key)
        is_processing = await redis_client.client.sismember(processing_key, job_id)
        
        print("🔍 QUEUE STATUS")
        print("-" * 80)
        print(f"Queue size: {queue_size}")
        print(f"In processing set: {is_processing}")
        
        # Check job data in Redis
        job_data_key = f"video_generation:job:{job_id}"
        job_data = await redis_client.client.get(job_data_key)
        if job_data:
            print(f"Job data in Redis: Yes")
            try:
                job_data_dict = json.loads(job_data)
                print(f"  Audio URL: {job_data_dict.get('audio_url', 'N/A')[:50]}...")
                print(f"  User Prompt: {job_data_dict.get('user_prompt', 'N/A')[:50]}...")
            except:
                pass
        else:
            print(f"Job data in Redis: No (may have been processed)")
        print()
    except Exception as e:
        print(f"⚠️  Could not check Redis: {e}")
        print()
    
    # Check for cancellation flag
    try:
        from shared.redis_client import RedisClient
        redis_client = RedisClient()
        cancel_key = f"job_cancel:{job_id}"
        is_cancelled = await redis_client.client.get(cancel_key)
        if is_cancelled:
            print("⚠️  Job has cancellation flag set")
            print()
    except:
        pass
    
    # Summary
    print("📝 SUMMARY")
    print("-" * 80)
    status = job.get('status')
    if status == "completed":
        print("✅ Job is completed")
    elif status == "failed":
        print("❌ Job has failed")
        if job.get('error_message'):
            print(f"   Reason: {job.get('error_message')}")
    elif status == "processing":
        current_stage = job.get('current_stage', 'unknown')
        progress = job.get('progress', 0)
        print(f"⏳ Job is processing")
        print(f"   Current stage: {current_stage}")
        print(f"   Progress: {progress}%")
        
        # Check if stuck (updated more than 30 minutes ago)
        try:
            updated_str = job.get('updated_at')
            if updated_str:
                if isinstance(updated_str, str):
                    updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                else:
                    updated = updated_str
                now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
                age_minutes = (now - updated).total_seconds() / 60
                if age_minutes > 30:
                    print(f"   ⚠️  WARNING: Job hasn't updated in {age_minutes:.1f} minutes - may be stuck!")
        except Exception as e:
            print(f"   ⚠️  Could not calculate age: {e}")
    elif status == "queued":
        print("⏳ Job is queued (waiting to be picked up by worker)")
    else:
        print(f"❓ Job status: {status}")
    print()

if __name__ == "__main__":
    job_id = "0e644281-677d-4a23-ae56-a12ce884b49e"
    if len(sys.argv) > 1:
        job_id = sys.argv[1]
    asyncio.run(check_job(job_id))

