#!/usr/bin/env python3
"""Check the most recent job failures with detailed error messages."""
import asyncio
import json
from datetime import datetime, timedelta
from shared.database import DatabaseClient

async def main():
    db_client = DatabaseClient()
    
    # Get most recent jobs (ordered by created_at descending)
    result = await db_client.table("jobs").select("*").order("created_at", desc=True).limit(10).execute()
    
    if not result.data:
        print("No jobs found in database")
        return
    
    recent_jobs = result.data
    
    print(f"\n=== MOST RECENT JOBS (Last 2 hours) ===\n")
    print(f"Found {len(recent_jobs)} recent jobs\n")
    
    for job in recent_jobs[:10]:  # Only show last 10
        print(f"\nJob ID: {job['id']}")
        print(f"Status: {job['status']}")
        print(f"Current Stage: {job.get('current_stage', 'N/A')}")
        print(f"Progress: {job.get('progress', 0)}%")
        print(f"Created: {job.get('created_at')}")
        
        if job['status'] == 'failed':
            print(f"\n❌ ERROR MESSAGE:")
            print(f"   {job.get('error_message', 'N/A')}")
            
            # Check video_generator stage for detailed clip errors
            stages_result = await db_client.table("job_stages").select("*").eq("job_id", job['id']).eq("stage_name", "video_generator").execute()
            
            if stages_result.data:
                stage = stages_result.data[0]
                if stage.get('metadata'):
                    metadata = stage['metadata']
                    
                    print(f"\n📊 VIDEO GENERATOR METADATA:")
                    print(f"   Model used: {metadata.get('model_used', 'N/A')}")
                    print(f"   Clips attempted: {metadata.get('clips_attempted', 'N/A')}")
                    print(f"   Clips succeeded: {metadata.get('clips_succeeded', 'N/A')}")
                    print(f"   Clips failed: {metadata.get('clips_failed', 'N/A')}")
                    
                    # Show detailed clip errors
                    if 'clip_errors' in metadata:
                        print(f"\n🔍 DETAILED CLIP ERRORS:")
                        for clip_idx, error_info in metadata['clip_errors'].items():
                            print(f"\n   Clip {clip_idx}:")
                            print(f"     Error Type: {error_info.get('error_type', 'N/A')}")
                            print(f"     Error: {error_info.get('error', 'N/A')}")
                            if 'model' in error_info:
                                print(f"     Model: {error_info['model']}")
                            if 'attempts' in error_info:
                                print(f"     Attempts: {error_info['attempts']}")
        
        print("-" * 120)

if __name__ == "__main__":
    asyncio.run(main())

