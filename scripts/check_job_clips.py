#!/usr/bin/env python3
"""Check job status and clip generation progress."""
import sys
import os

# Add project/backend to path
project_root = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(project_root, 'project/backend')
sys.path.insert(0, backend_path)

import asyncio
from shared.database import DatabaseClient

async def main():
    db_client = DatabaseClient()
    job_id = "489ddeaa-557a-4eee-b7ab-4877c437e7e0"

    print(f"Checking job: {job_id}\n")
    
    # Get job status
    result = await db_client.table("jobs").select("*").eq("id", job_id).single().execute()
    
    if not result.data:
        print(f"❌ Job {job_id} NOT found in database")
        return
    
    job = result.data
    print("=" * 60)
    print("JOB STATUS")
    print("=" * 60)
    print(f"ID: {job['id']}")
    print(f"Status: {job.get('status', 'unknown')}")
    print(f"Progress: {job.get('progress', 0)}%")
    print(f"Current Stage: {job.get('current_stage', 'N/A')}")
    print(f"Total Cost: ${job.get('total_cost', 0)}")
    print(f"Created: {job.get('created_at')}")
    print(f"Updated: {job.get('updated_at')}")
    if job.get('error_message'):
        print(f"❌ Error: {job.get('error_message')}")
    print()
    
    # Check job_stages for video_generation stage
    stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).execute()
    if stages_result.data:
        print("=" * 60)
        print("STAGE STATUS")
        print("=" * 60)
        for stage in stages_result.data:
            stage_name = stage.get("stage_name")
            stage_status = stage.get("status", "unknown")
            duration = stage.get("duration_seconds")
            print(f"{stage_name}: {stage_status}" + (f" ({duration}s)" if duration else ""))
        print()
    
    # Check if there's any clip data in the job_data JSONB column
    job_data = job.get('job_data')
    if job_data:
        print("=" * 60)
        print("JOB DATA")
        print("=" * 60)
        if isinstance(job_data, dict):
            # Check for video generator data
            if 'video_generator' in job_data:
                vg_data = job_data['video_generator']
                print("Video Generator Data:")
                if 'clips' in vg_data:
                    clips = vg_data['clips']
                    if isinstance(clips, list):
                        print(f"  Total Clips: {len(clips)}")
                        completed = sum(1 for c in clips if c.get('status') == 'success')
                        failed = sum(1 for c in clips if c.get('status') == 'failed')
                        processing = sum(1 for c in clips if c.get('status') == 'processing')
                        print(f"  ✅ Completed: {completed}")
                        print(f"  ❌ Failed: {failed}")
                        print(f"  ⏳ Processing: {processing}")
                        print()
                        print("  Clip Details:")
                        for i, clip in enumerate(clips):
                            status = clip.get('status', 'unknown')
                            clip_idx = clip.get('clip_index', i)
                            duration = clip.get('actual_duration', 'N/A')
                            cost = clip.get('cost', 0)
                            print(f"    Clip {clip_idx}: {status} | Duration: {duration}s | Cost: ${cost}")
                    else:
                        print(f"  Clips: {clips}")
                else:
                    print(f"  Data: {vg_data}")
            else:
                print("No video generator data found in job_data")
        else:
            print(f"Job data type: {type(job_data)}")
            print(f"Job data: {str(job_data)[:200]}...")
    else:
        print("No job_data found")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

