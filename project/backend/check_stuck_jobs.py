"""
Utility script to check for stuck jobs in the database.

Usage:
    cd project/backend
    source venv/bin/activate
    python check_stuck_jobs.py [--fix]
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)
db_client = DatabaseClient()


async def check_stuck_jobs(fix: bool = False):
    """Check for stuck jobs (queued or processing for > 30 minutes)."""
    try:
        # Get all queued or processing jobs
        # Query queued jobs
        queued_result = await db_client.table("jobs").select(
            "id, status, current_stage, created_at, updated_at, error_message"
        ).eq("status", "queued").execute()
        
        # Query processing jobs
        processing_result = await db_client.table("jobs").select(
            "id, status, current_stage, created_at, updated_at, error_message"
        ).eq("status", "processing").execute()
        
        # Combine results
        result_data = (queued_result.data or []) + (processing_result.data or [])
        result = type('obj', (object,), {'data': result_data})()
        
        if not result.data:
            print("\n✅ No stuck jobs found")
            return
        
        stuck_threshold = datetime.now() - timedelta(minutes=30)
        stuck_jobs = []
        
        print(f"\n{'='*60}")
        print(f"Checking {len(result.data)} job(s) with status 'queued' or 'processing'")
        print(f"{'='*60}\n")
        
        for job in result.data:
            job_id = job.get("id")
            status = job.get("status")
            current_stage = job.get("current_stage")
            updated_at_str = job.get("updated_at")
            created_at_str = job.get("created_at")
            
            # Parse updated_at
            try:
                if updated_at_str:
                    updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                elif created_at_str:
                    updated_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                else:
                    updated_at = None
                
                if updated_at:
                    age = datetime.now(updated_at.tzinfo) - updated_at
                    age_minutes = age.total_seconds() / 60
                    
                    is_stuck = age_minutes > 30
                    
                    print(f"  Job ID: {job_id}")
                    print(f"    Status: {status}")
                    print(f"    Current Stage: {current_stage or 'none'}")
                    print(f"    Last Updated: {age_minutes:.1f} minutes ago")
                    
                    if is_stuck:
                        print(f"    ⚠️  STUCK (>{30} minutes old)")
                        stuck_jobs.append({
                            "id": job_id,
                            "status": status,
                            "current_stage": current_stage,
                            "age_minutes": age_minutes
                        })
                    else:
                        print(f"    ✅ Active (recently updated)")
                    print()
                    
            except Exception as e:
                print(f"  ⚠️  Job {job_id}: Could not parse timestamps: {e}")
                print()
        
        if stuck_jobs:
            print(f"\n{'='*60}")
            print(f"Found {len(stuck_jobs)} stuck job(s)")
            print(f"{'='*60}\n")
            
            if fix:
                print("⚠️  Marking stuck jobs as failed...\n")
                for job in stuck_jobs:
                    try:
                        await db_client.table("jobs").update({
                            "status": "failed",
                            "error_message": f"Job stuck in {job['status']} status for {job['age_minutes']:.1f} minutes - marked as failed by cleanup script"
                        }).eq("id", job["id"]).execute()
                        print(f"  ✅ Marked job {job['id']} as failed")
                    except Exception as e:
                        print(f"  ❌ Failed to update job {job['id']}: {e}")
                
                print(f"\n✅ Fixed {len(stuck_jobs)} stuck job(s)")
            else:
                print("💡 To mark these jobs as failed, run: python check_stuck_jobs.py --fix")
        else:
            print("\n✅ No stuck jobs found (all jobs updated within last 30 minutes)")
            
    except Exception as e:
        print(f"❌ Error checking stuck jobs: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def main():
    """Main entry point."""
    fix = "--fix" in sys.argv or "-f" in sys.argv
    skip_confirm = "--yes" in sys.argv or "-y" in sys.argv
    
    if fix and not skip_confirm:
        # Check if stdin is a TTY (interactive)
        if sys.stdin.isatty():
            print("\n⚠️  WARNING: This will mark stuck jobs as failed!")
            response = input("Are you sure? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled.")
                return
        else:
            # Non-interactive mode - require explicit --yes flag
            print("\n⚠️  WARNING: This will mark stuck jobs as failed!")
            print("⚠️  Running in non-interactive mode. Use --yes to confirm.")
            return
    
    await check_stuck_jobs(fix=fix)


if __name__ == "__main__":
    asyncio.run(main())

