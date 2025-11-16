#!/usr/bin/env python3
"""Check recent job errors in database."""
import asyncio
import json
from shared.database import DatabaseClient

async def main():
    db_client = DatabaseClient()
    
    # Get recent failed jobs
    query = db_client.table("jobs").select("*")
    result = await query.execute()
    
    if not result.data:
        print("No jobs found in database")
        return
    
    print("\n=== RECENT JOBS ===\n")
    for job in result.data:
        print(f"\nJob ID: {job['id']}")
        print(f"Status: {job['status']}")
        print(f"Progress: {job.get('progress', 0)}%")
        print(f"Current Stage: {job.get('current_stage', 'N/A')}")
        print(f"Error Message: {job.get('error_message', 'N/A')}")
        print(f"Created: {job.get('created_at')}")
        
        # Check job_stages for more detail
        stages_result = await db_client.table("job_stages").select("*").eq("job_id", job['id']).execute()
        if stages_result.data:
            print(f"  Stages completed: {len([s for s in stages_result.data if s['status'] == 'completed'])}")
            print(f"  Stages failed: {len([s for s in stages_result.data if s['status'] == 'failed'])}")
            
            # Show failed stages
            failed_stages = [s for s in stages_result.data if s['status'] == 'failed']
            for stage in failed_stages:
                print(f"    FAILED: {stage['stage_name']}")
                if stage.get('metadata'):
                    print(f"      Metadata: {json.dumps(stage['metadata'], indent=6)}")
        
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())

