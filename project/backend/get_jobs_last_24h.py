#!/usr/bin/env python3
"""
Query Supabase for all jobs created in the last 48 hours with timestamp and video length.
Uses the shared database client from the backend.
"""

import sys
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project/backend to path so we can import shared modules
sys.path.insert(0, str(Path(__file__).parent))

from shared.database import db


def format_duration(seconds):
    """Format duration in seconds to human-readable format."""
    if seconds is None:
        return "N/A"
    try:
        seconds = float(seconds)
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    except (ValueError, TypeError):
        return "N/A"


async def get_jobs_last_48h():
    """Get all jobs created in the last 48 hours with timestamp and video length (only jobs with video)."""
    
    try:
        # Calculate 48 hours ago (UTC)
        now = datetime.now(timezone.utc)
        forty_eight_hours_ago = now - timedelta(hours=48)
        # Format as ISO string for Supabase query
        cutoff_time = forty_eight_hours_ago.isoformat()
        
        print(f"Querying for jobs with video created after {cutoff_time} (last 48 hours)...")
        print()
        
        # Query for jobs created in the last 48 hours
        result = await db.table("jobs").select(
            "id, created_at, status, audio_data, video_url"
        ).gte("created_at", cutoff_time).order("created_at", desc=True).execute()
        
        if not result.data:
            print("No jobs found in the last 48 hours.")
            return []
        
        # Filter to only jobs with video_url
        jobs_with_video = [job for job in result.data if job.get("video_url")]
        
        if not jobs_with_video:
            print("No jobs with video found in the last 48 hours.")
            return []
        
        # Get all job IDs to query composer stages
        job_ids = [job["id"] for job in jobs_with_video]
        
        # Query job_stages for both composer and audio_parser stage metadata
        duration_from_stages = {}
        if job_ids:
            job_ids_set = set(job_ids)
            
            # Query audio_parser stages
            audio_stages_result = await db.table("job_stages").select(
                "job_id, metadata"
            ).eq("stage_name", "audio_parser").execute()
            
            if audio_stages_result.data:
                for stage in audio_stages_result.data:
                    job_id = stage.get("job_id")
                    if job_id not in job_ids_set:
                        continue
                    
                    metadata = stage.get("metadata")
                    if metadata and isinstance(metadata, dict):
                        # Check audio_analysis in metadata
                        audio_analysis = metadata.get("audio_analysis")
                        if isinstance(audio_analysis, dict):
                            audio_duration = audio_analysis.get("duration")
                            if audio_duration and job_id not in duration_from_stages:
                                duration_from_stages[job_id] = audio_duration
            
            # Query composer stages
            composer_stages_result = await db.table("job_stages").select(
                "job_id, metadata"
            ).eq("stage_name", "composer").execute()
            
            if composer_stages_result.data:
                for stage in composer_stages_result.data:
                    job_id = stage.get("job_id")
                    if job_id not in job_ids_set:
                        continue
                    
                    metadata = stage.get("metadata")
                    if metadata and isinstance(metadata, dict):
                        # Check for video duration in composer metadata
                        video_output = metadata.get("video_output")
                        if isinstance(video_output, dict):
                            video_duration = video_output.get("duration")
                        else:
                            video_duration = (
                                metadata.get("duration") or 
                                metadata.get("video_duration") or 
                                metadata.get("final_duration")
                            )
                        if video_duration:
                            duration_from_stages[job_id] = video_duration
        
        jobs_with_info = []
        
        print(f"Found {len(jobs_with_video)} job(s) with video created in the last 48 hours:")
        print()
        
        for job in jobs_with_video:
            job_id = job["id"]
            created_at = job["created_at"]
            status = job.get("status", "unknown")
            audio_data = job.get("audio_data")
            video_url = job.get("video_url")
            
            # Get audio duration from audio_data (this should be the video length)
            duration = None
            if audio_data:
                if isinstance(audio_data, dict):
                    # Try different possible structures
                    duration = (
                        audio_data.get("duration") or
                        audio_data.get("audio_analysis", {}).get("duration") if isinstance(audio_data.get("audio_analysis"), dict) else None
                    )
                elif isinstance(audio_data, (int, float)):
                    # Sometimes audio_data might just be the duration value
                    duration = audio_data
            
            # If we didn't get duration from audio_data, try stage metadata
            if not duration:
                duration = duration_from_stages.get(job_id)
                
                # If still not found, try querying this specific job's stages
                if not duration:
                    try:
                        # Try audio_parser first (most reliable)
                        audio_stage_result = await db.table("job_stages").select(
                            "metadata"
                        ).eq("job_id", job_id).eq("stage_name", "audio_parser").limit(1).execute()
                        
                        if audio_stage_result.data and audio_stage_result.data[0].get("metadata"):
                            metadata = audio_stage_result.data[0].get("metadata")
                            if isinstance(metadata, dict):
                                audio_analysis = metadata.get("audio_analysis")
                                if isinstance(audio_analysis, dict):
                                    duration = audio_analysis.get("duration")
                        
                        # If still not found, try composer
                        if not duration:
                            composer_stage_result = await db.table("job_stages").select(
                                "metadata"
                            ).eq("job_id", job_id).eq("stage_name", "composer").limit(1).execute()
                            
                            if composer_stage_result.data and composer_stage_result.data[0].get("metadata"):
                                metadata = composer_stage_result.data[0].get("metadata")
                                if isinstance(metadata, dict):
                                    video_output = metadata.get("video_output")
                                    if isinstance(video_output, dict):
                                        duration = video_output.get("duration")
                                    else:
                                        duration = (
                                            metadata.get("duration") or 
                                            metadata.get("video_duration") or 
                                            metadata.get("final_duration")
                                        )
                    except Exception as e:
                        # Silently continue if we can't get the stage
                        pass
            
            # Format timestamp nicely
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except:
                formatted_time = created_at
            
            job_info = {
                "id": job_id,
                "created_at": formatted_time,
                "status": status,
                "duration": duration,
                "video_url": video_url
            }
            jobs_with_info.append(job_info)
            
            # Display job info
            print(f"Job ID: {job_id}")
            print(f"  Created: {formatted_time}")
            print(f"  Status: {status}")
            print(f"  Video Length: {format_duration(duration)}")
            print()
        
        print(f"\nTotal jobs with video: {len(jobs_with_info)}")
        print(f"Jobs with duration info: {sum(1 for j in jobs_with_info if j['duration'] is not None)}")
        
        # Print summary table
        print("\n" + "="*100)
        print("SUMMARY TABLE - Jobs with Video from Last 48 Hours")
        print("="*100)
        print(f"{'Job ID':<40} {'Created At':<20} {'Status':<12} {'Video Length':<15}")
        print("-"*100)
        for job in jobs_with_info:
            length = format_duration(job['duration'])
            print(f"{job['id']:<40} {job['created_at']:<20} {job['status']:<12} {length:<15}")
        
        return jobs_with_info
        
    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    jobs = asyncio.run(get_jobs_last_48h())
    sys.exit(0 if jobs else 1)

