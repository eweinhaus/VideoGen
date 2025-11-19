#!/usr/bin/env python3
"""
Query Supabase for job IDs of videos created in the last 24 hours with duration > 40 seconds.
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


def query_recent_long_videos():
    """Query for jobs created in last 24 hours with duration > 40 seconds."""
    
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
        print(f"With audio duration > 40 seconds")
        print()
        
        # Query using Supabase client
        # First, let's try to find jobs with audio_data that has duration
        # We'll also check completed jobs with video_url
        
        result = client.table("jobs").select("id, created_at, audio_data, status, video_url, completed_at").gte(
            "created_at", twenty_four_hours_ago.isoformat()
        ).order("created_at", desc=True).limit(200).execute()
        
        matching_jobs = []
        all_recent_jobs = []
        
        if result.data:
            print(f"Found {len(result.data)} total job(s) in last 24 hours:")
            print()
            
            # Get job IDs to query job_stages
            job_ids = [job["id"] for job in result.data if job.get("status") == "completed" and job.get("video_url")]
            
            # Query job_stages for composer stage metadata (which may contain video duration)
            duration_from_stages = {}
            if job_ids:
                stages_result = client.table("job_stages").select("job_id, metadata").in_(
                    "job_id", job_ids
                ).eq("stage_name", "composer").execute()
                
                if stages_result.data:
                    for stage in stages_result.data:
                        job_id = stage.get("job_id")
                        metadata = stage.get("metadata")
                        if metadata and isinstance(metadata, dict):
                            # Check for duration in metadata
                            video_duration = metadata.get("duration") or metadata.get("video_duration") or metadata.get("final_duration")
                            if video_duration:
                                duration_from_stages[job_id] = video_duration
            
            for job in result.data:
                audio_data = job.get("audio_data")
                duration = None
                
                if audio_data and isinstance(audio_data, dict):
                    duration = audio_data.get("duration")
                
                # Also check job_stages metadata for duration
                if not duration:
                    duration = duration_from_stages.get(job["id"])
                
                # Also check if job is completed and has video_url
                has_video = job.get("video_url") is not None
                is_completed = job.get("status") == "completed"
                
                job_info = {
                    "id": job["id"],
                    "created_at": job["created_at"],
                    "duration": duration,
                    "status": job.get("status"),
                    "has_audio_data": audio_data is not None,
                    "has_video": has_video,
                    "completed_at": job.get("completed_at")
                }
                all_recent_jobs.append(job_info)
                
                # Check if duration > 40
                if duration and isinstance(duration, (int, float)) and duration > 40:
                    matching_jobs.append(job_info)
            
            # Show completed jobs with videos for debugging
            completed_with_video = [j for j in all_recent_jobs if j['has_video'] and j['status'] == 'completed']
            print(f"Completed jobs with videos: {len(completed_with_video)}")
            
            # Show all recent jobs for debugging (focus on completed ones)
            print("\nRecent completed jobs with videos:")
            for job in completed_with_video[:10]:
                duration_str = f"{job['duration']:.2f}s" if job['duration'] else "N/A (no audio_data)"
                print(f"  {job['id']} | Created: {job['created_at']} | Duration: {duration_str} | Status: {job['status']}")
            
            if len(completed_with_video) == 0:
                print("\nAll recent jobs (first 10):")
                for job in all_recent_jobs[:10]:
                    duration_str = f"{job['duration']:.2f}s" if job['duration'] else "N/A"
                    print(f"  {job['id']} | {job['created_at']} | Duration: {duration_str} | Status: {job['status']} | Has audio_data: {job['has_audio_data']} | Has video: {job['has_video']}")
                if len(all_recent_jobs) > 10:
                    print(f"  ... and {len(all_recent_jobs) - 10} more")
            print()
        
        # If no jobs with duration > 40 found, try to get completed jobs with videos
        # (duration information may not be stored in database)
        if not matching_jobs:
            completed_with_videos = [
                j for j in all_recent_jobs 
                if j['has_video'] and j['status'] == 'completed'
            ]
            completed_with_videos.sort(key=lambda x: x["created_at"], reverse=True)
            matching_jobs = completed_with_videos[:2]
            
            if matching_jobs:
                print("Note: Duration information not available in database.")
                print("Returning 2 most recent completed jobs with videos.")
                print("You may need to check video duration manually.")
                print()
        
        # Sort by created_at descending and take first 2
        matching_jobs.sort(key=lambda x: x["created_at"], reverse=True)
        matching_jobs = matching_jobs[:2]
        
        if matching_jobs:
            print(f"Found {len(matching_jobs)} job(s):")
            print()
            for job in matching_jobs:
                print(f"Job ID: {job['id']}")
                print(f"  Created: {job['created_at']}")
                if job['duration']:
                    print(f"  Duration: {job['duration']:.2f} seconds")
                else:
                    print(f"  Duration: Not available in database (check video file)")
                print(f"  Status: {job['status']}")
                print()
            
            # Print just the IDs for easy copy-paste
            print("Job IDs:")
            for job in matching_jobs:
                print(f"  {job['id']}")
        else:
            print("No jobs found matching the criteria.")
            print("(Jobs created in last 24 hours with duration > 40 seconds)")
        
        return matching_jobs
        
    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    query_recent_long_videos()

