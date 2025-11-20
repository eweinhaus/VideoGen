#!/usr/bin/env python3
"""
Check job status in database and rerun if needed.
"""
import sys
import os
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
env_paths = [
    Path(__file__).parent / ".env",
    Path(__file__).parent / "project" / "backend" / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

# Add project/backend to path
project_root = Path(__file__).parent
backend_path = project_root / 'project' / 'backend'
sys.path.insert(0, str(backend_path))

from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from api_gateway.services.queue_service import enqueue_job

async def check_and_rerun_job(job_id: str, rerun: bool = False):
    """Check job status and optionally rerun it."""
    db_client = DatabaseClient()
    redis_client = RedisClient()
    
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
    print(f"Video URL: {job.get('video_url', 'N/A')}")
    print(f"Created: {job.get('created_at')}")
    print(f"Updated: {job.get('updated_at')}")
    if job.get('completed_at'):
        print(f"Completed: {job.get('completed_at')}")
    if job.get('error_message'):
        print(f"❌ Error: {job.get('error_message')}")
    print()
    
    # Check if job is stuck (updated more than 30 minutes ago and still processing)
    status = job.get('status')
    updated_str = job.get('updated_at')
    is_stuck = False
    
    if updated_str and status in ['processing', 'queued']:
        try:
            if isinstance(updated_str, str):
                updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
            else:
                updated = updated_str
            now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
            age_minutes = (now - updated).total_seconds() / 60
            if age_minutes > 30:
                is_stuck = True
                print(f"⚠️  WARNING: Job hasn't updated in {age_minutes:.1f} minutes - may be stuck!")
                print()
        except Exception as e:
            print(f"⚠️  Could not calculate age: {e}")
            print()
    
    # Check job_stages
    stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).order("created_at").execute()
    if stages_result.data:
        print("📊 STAGE STATUS")
        print("-" * 80)
        completed_stages = []
        failed_stages = []
        for stage in stages_result.data:
            stage_name = stage.get("stage_name")
            stage_status = stage.get("status", "unknown")
            duration = stage.get("duration_seconds")
            
            status_icon = "✅" if stage_status == "completed" else "❌" if stage_status == "failed" else "⏳"
            print(f"{status_icon} {stage_name}: {stage_status}" + (f" ({duration}s)" if duration else ""))
            
            if stage_status == "completed":
                completed_stages.append(stage_name)
            elif stage_status == "failed":
                failed_stages.append(stage_name)
        print()
        
        print(f"✅ Completed stages: {len(completed_stages)}")
        print(f"❌ Failed stages: {len(failed_stages)}")
        if failed_stages:
            print(f"   Failed: {', '.join(failed_stages)}")
        print()
    else:
        print("⚠️  No stages found for this job")
        print()
    
    # Check queue status
    print("🔍 QUEUE STATUS")
    print("-" * 80)
    try:
        queue_key = "video_generation_development:queue"
        processing_key = "video_generation_development:processing"
        
        queue_size = await redis_client.client.llen(queue_key)
        is_in_queue = False
        is_processing = await redis_client.client.sismember(processing_key, job_id)
        
        # Check if job is in queue
        if queue_size > 0:
            queue_items = await redis_client.client.lrange(queue_key, 0, -1)
            for item in queue_items:
                try:
                    item_data = json.loads(item)
                    if item_data.get('job_id') == job_id:
                        is_in_queue = True
                        break
                except:
                    pass
        
        print(f"Queue size: {queue_size}")
        print(f"In queue: {is_in_queue}")
        print(f"In processing set: {is_processing}")
        print()
    except Exception as e:
        print(f"⚠️  Could not check Redis: {e}")
        print()
    
    # Determine if rerun is needed
    needs_rerun = False
    rerun_reason = ""
    needs_fix = False
    fix_reason = ""
    
    # Special case: regenerating status with video URL means regeneration got stuck
    if status == "regenerating" and job.get('video_url') and job.get('completed_at'):
        needs_fix = True
        fix_reason = "Job is stuck in regenerating status but has completed video"
    elif status == "failed":
        needs_rerun = True
        rerun_reason = "Job has failed status"
    elif status == "processing" and is_stuck:
        needs_rerun = True
        rerun_reason = "Job is stuck in processing status"
    elif status == "queued" and is_stuck:
        needs_rerun = True
        rerun_reason = "Job is stuck in queued status"
    elif failed_stages and not is_processing and not is_in_queue:
        needs_rerun = True
        rerun_reason = "Job has failed stages and is not being processed"
    
    # Fix stuck regenerating job
    if needs_fix and rerun:
        print("🔧 FIXING STUCK REGENERATION")
        print("-" * 80)
        print(f"Reason: {fix_reason}")
        print()
        
        # Mark composer stage as completed if it's stuck
        composer_stage = [s for s in stages_result.data if s.get("stage_name") == "composer" and s.get("status") == "processing"]
        if composer_stage:
            print("Marking composer stage as completed...")
            await db_client.table("job_stages").update({
                "status": "completed"
            }).eq("job_id", job_id).eq("stage_name", "composer").execute()
            print("✅ Composer stage marked as completed")
            print()
        
        # Restore job to completed status
        print("Restoring job to completed status...")
        await db_client.table("jobs").update({
            "status": "completed",
            "progress": 100,
            "current_stage": "composer",
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        # Invalidate cache
        cache_key = f"job_status:{job_id}"
        await redis_client.client.delete(cache_key)
        
        print("✅ Job restored to completed status!")
        print(f"\n📝 Job URL: http://localhost:3000/jobs/{job_id}")
        print()
        return
    
    # Rerun logic
    if needs_rerun and rerun:
        print("🔄 RERUNNING JOB")
        print("-" * 80)
        print(f"Reason: {rerun_reason}")
        print()
        
        # Get job data needed for rerun
        audio_url = job.get('audio_url')
        user_prompt = job.get('user_prompt')
        user_id = job.get('user_id')
        video_model = job.get('video_model', 'kling_v21')
        aspect_ratio = job.get('aspect_ratio', '16:9')
        template = job.get('template', 'standard')
        
        if not audio_url or not user_prompt or not user_id:
            print("❌ Cannot rerun: Missing required job data (audio_url, user_prompt, or user_id)")
            return
        
        # Mark old job as failed if it's stuck
        if status in ['processing', 'queued'] and is_stuck:
            print(f"Marking old job {job_id} as failed...")
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": f"Job stuck - rerun requested. Original status: {status}"
            }).eq("id", job_id).execute()
            print("✅ Old job marked as failed")
            print()
        
        # Create new job
        print("Creating new job...")
        from uuid import uuid4
        new_job_id = str(uuid4())
        
        # Insert new job record
        await db_client.table("jobs").insert({
            "id": new_job_id,
            "user_id": user_id,
            "status": "queued",
            "audio_url": audio_url,
            "user_prompt": user_prompt,
            "video_model": video_model,
            "aspect_ratio": aspect_ratio,
            "template": template,
            "progress": 0,
            "total_cost": 0,
            "created_at": "now()",
            "updated_at": "now()"
        }).execute()
        
        print(f"✅ New job created: {new_job_id}")
        
        # Enqueue the job
        print("Enqueuing job...")
        await enqueue_job(
            job_id=new_job_id,
            user_id=user_id,
            audio_url=audio_url,
            user_prompt=user_prompt,
            stop_at_stage=None,
            video_model=video_model,
            aspect_ratio=aspect_ratio,
            template=template
        )
        
        print(f"✅ Job {new_job_id} enqueued successfully!")
        print(f"\n📝 New job URL: http://localhost:3000/jobs/{new_job_id}")
        print()
        
    elif needs_fix and not rerun:
        print("💡 FIX RECOMMENDED")
        print("-" * 80)
        print(f"Reason: {fix_reason}")
        print()
        print("To fix this job (mark as completed), run:")
        print(f"  python3 check_and_rerun_job.py {job_id} --rerun")
        print()
    elif needs_rerun and not rerun:
        print("💡 RERUN RECOMMENDED")
        print("-" * 80)
        print(f"Reason: {rerun_reason}")
        print()
        print("To rerun this job, run:")
        print(f"  python3 check_and_rerun_job.py {job_id} --rerun")
        print()
    elif status == "completed":
        print("✅ Job is completed successfully!")
        if job.get('video_url'):
            print(f"Video URL: {job.get('video_url')}")
        print()
    else:
        print("ℹ️  Job appears to be in progress or completed")
        print()

if __name__ == "__main__":
    job_id = "0e644281-677d-4a23-ae56-a12ce884b49e"
    rerun = False
    
    if len(sys.argv) > 1:
        job_id = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--rerun":
        rerun = True
    
    asyncio.run(check_and_rerun_job(job_id, rerun))

