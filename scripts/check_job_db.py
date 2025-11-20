#!/usr/bin/env python3
"""Check job status in database."""
import sys
sys.path.insert(0, '/Users/mylessjs/Desktop/VideoGen/project/backend')

import asyncio
from shared.database import DatabaseClient

async def main():
    db_client = DatabaseClient()
    job_id = "74984f3d-295f-4278-89b0-8c34733867e2"

    result = await db_client.table("jobs").select("*").eq("id", job_id).execute()

    if result.data:
        job = result.data[0]
        print(f"Job found in database:")
        print(f"  ID: {job['id']}")
        print(f"  Status: {job['status']}")
        print(f"  Progress: {job.get('progress', 0)}%")
        print(f"  Current Stage: {job.get('current_stage', 'N/A')}")
        print(f"  Created: {job.get('created_at')}")
        print(f"  User Prompt: {job.get('user_prompt', 'N/A')[:100]}")
    else:
        print(f"Job {job_id} NOT found in database")

if __name__ == "__main__":
    asyncio.run(main())
