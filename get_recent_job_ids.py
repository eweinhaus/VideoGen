#!/usr/bin/env python3
"""
Query Supabase for all job IDs created in the last 24 hours.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
env_paths = [
    Path(__file__).parent / ".env",
    Path(__file__).parent / "project" / "backend" / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    # Try loading from current directory
    load_dotenv()


def get_recent_job_ids():
    """Get all job IDs created in the last 24 hours."""
    
    # Get Supabase credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_service_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment or .env file", file=sys.stderr)
        return []
    
    try:
        # Create Supabase client
        client: Client = create_client(supabase_url, supabase_service_key)
        
        # Calculate 24 hours ago
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        print(f"Querying for jobs created after {twenty_four_hours_ago.isoformat()}")
        print()
        
        # Query for all jobs created in last 24 hours
        result = client.table("jobs").select("id, created_at, status").gte(
            "created_at", twenty_four_hours_ago.isoformat()
        ).order("created_at", desc=True).execute()
        
        job_ids = []
        
        if result.data:
            job_ids = [job["id"] for job in result.data]
            print(f"Found {len(job_ids)} job(s) created in the last 24 hours:")
            print()
            for job_id in job_ids:
                print(job_id)
        else:
            print("No jobs found in the last 24 hours.")
        
        return job_ids
        
    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    get_recent_job_ids()

