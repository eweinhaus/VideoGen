#!/usr/bin/env python3
"""
Query Supabase for the 5 most recent job IDs with timestamps.
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
    """Get the 5 most recent job IDs with timestamps."""
    
    # Get Supabase credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_service_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment or .env file", file=sys.stderr)
        return []
    
    try:
        # Create Supabase client
        client: Client = create_client(supabase_url, supabase_service_key)
        
        print("Querying for the 5 most recent jobs...")
        print()
        
        # Query for the 5 most recent jobs (no time filter)
        result = client.table("jobs").select("id, created_at, status").order(
            "created_at", desc=True
        ).limit(5).execute()
        
        job_ids = []
        
        if result.data:
            print(f"Most recent 5 jobs:")
            print()
            for job in result.data:
                job_id = job["id"]
                created_at = job["created_at"]
                status = job.get("status", "unknown")
                job_ids.append(job_id)
                
                # Format timestamp nicely
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except:
                    formatted_time = created_at
                
                print(f"Job ID: {job_id}")
                print(f"  Created: {formatted_time} ({created_at})")
                print(f"  Status: {status}")
                print()
        else:
            print("No jobs found.")
        
        return job_ids
        
    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    get_recent_job_ids()

