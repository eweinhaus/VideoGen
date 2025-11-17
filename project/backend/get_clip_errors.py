#!/usr/bin/env python3
"""Get detailed clip errors from the most recent failed job."""
import asyncio
import json
from shared.database import DatabaseClient

async def main():
    db_client = DatabaseClient()
    
    # Get most recent failed job
    result = await db_client.table("jobs").select("*").execute()
    failed_jobs = [j for j in result.data if j['status'] == 'failed' and j.get('current_stage') == 'video_generator']
    failed_jobs.sort(key=lambda x: x['created_at'], reverse=True)
    
    if not failed_jobs:
        print("No failed video_generator jobs found")
        return
    
    job = failed_jobs[0]
    job_id = job['id']
    
    print(f"\n=== MOST RECENT FAILED JOB ===")
    print(f"Job ID: {job_id}")
    print(f"Created: {job['created_at']}")
    print(f"Error: {job.get('error_message', 'N/A')}\n")
    
    # Get video_generator stage details
    stages_result = await db_client.table("job_stages").select("*").eq("job_id", job_id).eq("stage_name", "video_generator").execute()
    
    if not stages_result.data:
        print("No video_generator stage data found")
        return
    
    stage = stages_result.data[0]
    metadata = stage.get('metadata', {})
    
    print("=== STAGE METADATA ===")
    print(json.dumps(metadata, indent=2))
    
    # Look for error details in various places
    if 'error_details' in metadata:
        print("\n=== ERROR DETAILS ===")
        print(json.dumps(metadata['error_details'], indent=2))
    
    if 'clip_errors' in metadata:
        print("\n=== CLIP ERRORS ===")
        print(json.dumps(metadata['clip_errors'], indent=2))
    
    if 'failed_clips' in metadata:
        print("\n=== FAILED CLIPS ===")
        print(json.dumps(metadata['failed_clips'], indent=2))

if __name__ == "__main__":
    asyncio.run(main())

