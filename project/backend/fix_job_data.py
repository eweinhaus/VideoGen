#!/usr/bin/env python3
"""
Backfill thumbnails for existing jobs.

This script generates thumbnails for video clips from completed jobs that don't have thumbnails yet.
Useful after creating the clip-thumbnails bucket or fixing missing thumbnails.
"""
import sys
import asyncio
from pathlib import Path
from uuid import UUID
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from shared.database import DatabaseClient
from shared.logging import get_logger
from modules.clip_regenerator.data_loader import load_clips_from_job_stages
from modules.video_generator.thumbnail_generator import generate_clip_thumbnail

logger = get_logger("fix_job_data")


async def get_jobs_needing_thumbnails(limit: int = None) -> list:
    """
    Get list of completed jobs that may need thumbnails.
    
    Args:
        limit: Optional limit on number of jobs to process
        
    Returns:
        List of job IDs
    """
    db = DatabaseClient()
    
    try:
        # Get completed jobs
        query = db.table("jobs").select("id, status").eq("status", "completed")
        
        if limit:
            query = query.limit(limit)
        
        result = await query.execute()
        
        job_ids = [job["id"] for job in result.data]
        logger.info(f"Found {len(job_ids)} completed jobs to check")
        return job_ids
        
    except Exception as e:
        logger.error(f"Failed to get jobs: {e}", exc_info=True)
        return []


async def check_job_thumbnails(job_id: str) -> dict:
    """
    Check which clips in a job are missing thumbnails.
    
    Args:
        job_id: Job ID
        
    Returns:
        Dict with job_id, total_clips, missing_clips (list of clip indices)
    """
    db = DatabaseClient()
    
    try:
        # Load clips from job_stages
        clips = await load_clips_from_job_stages(UUID(job_id))
        if not clips:
            return {
                "job_id": job_id,
                "total_clips": 0,
                "missing_clips": []
            }
        
        # Get existing thumbnails
        thumbnails_result = await db.table("clip_thumbnails").select(
            "clip_index"
        ).eq("job_id", job_id).execute()
        
        existing_indices = {t["clip_index"] for t in thumbnails_result.data}
        
        # Find missing thumbnails
        missing_clips = [
            clip.clip_index
            for clip in clips.clips
            if clip.clip_index not in existing_indices
        ]
        
        return {
            "job_id": job_id,
            "total_clips": len(clips.clips),
            "missing_clips": missing_clips,
            "clips": clips.clips  # Include clips for thumbnail generation
        }
        
    except Exception as e:
        logger.warning(
            f"Failed to check thumbnails for job {job_id}: {e}",
            extra={"job_id": job_id}
        )
        return {
            "job_id": job_id,
            "total_clips": 0,
            "missing_clips": []
        }


async def generate_missing_thumbnails(job_info: dict) -> dict:
    """
    Generate thumbnails for missing clips in a job.
    
    Args:
        job_info: Dict from check_job_thumbnails with clips included
        
    Returns:
        Dict with success count and failure count
    """
    job_id = job_info["job_id"]
    missing_clips = job_info["missing_clips"]
    clips = job_info.get("clips", [])
    
    if not missing_clips or not clips:
        return {"success": 0, "failed": 0}
    
    # Create clip map for easy lookup
    clip_map = {clip.clip_index: clip for clip in clips}
    
    success_count = 0
    failed_count = 0
    
    logger.info(
        f"Generating {len(missing_clips)} thumbnails for job {job_id}",
        extra={"job_id": job_id, "missing_count": len(missing_clips)}
    )
    
    for clip_index in missing_clips:
        clip = clip_map.get(clip_index)
        if not clip:
            logger.warning(
                f"Clip {clip_index} not found in clips list",
                extra={"job_id": job_id, "clip_index": clip_index}
            )
            failed_count += 1
            continue
        
        try:
            thumbnail_url = await generate_clip_thumbnail(
                clip_url=clip.video_url,
                job_id=UUID(job_id),
                clip_index=clip_index
            )
            
            if thumbnail_url:
                success_count += 1
                logger.info(
                    f"Generated thumbnail for clip {clip_index}",
                    extra={"job_id": job_id, "clip_index": clip_index}
                )
            else:
                failed_count += 1
                logger.warning(
                    f"Failed to generate thumbnail for clip {clip_index}",
                    extra={"job_id": job_id, "clip_index": clip_index}
                )
                
        except Exception as e:
            failed_count += 1
            logger.error(
                f"Error generating thumbnail for clip {clip_index}: {e}",
                extra={"job_id": job_id, "clip_index": clip_index},
                exc_info=True
            )
    
    return {"success": success_count, "failed": failed_count}


async def process_jobs(job_ids: list, dry_run: bool = False) -> dict:
    """
    Process jobs to backfill missing thumbnails.
    
    Args:
        job_ids: List of job IDs to process
        dry_run: If True, only check and report, don't generate
        
    Returns:
        Summary dict with statistics
    """
    total_jobs = len(job_ids)
    jobs_processed = 0
    jobs_with_missing = 0
    total_missing = 0
    total_generated = 0
    total_failed = 0
    
    print(f"\nProcessing {total_jobs} jobs...")
    print("=" * 60)
    
    for i, job_id in enumerate(job_ids, 1):
        print(f"\n[{i}/{total_jobs}] Job: {job_id}")
        
        try:
            job_info = await check_job_thumbnails(job_id)
            missing_count = len(job_info["missing_clips"])
            
            if missing_count == 0:
                print(f"  ✅ All thumbnails exist ({job_info['total_clips']} clips)")
                jobs_processed += 1
                continue
            
            jobs_with_missing += 1
            total_missing += missing_count
            print(f"  ⚠️  Missing {missing_count} thumbnails (out of {job_info['total_clips']} clips)")
            
            if not dry_run:
                result = await generate_missing_thumbnails(job_info)
                total_generated += result["success"]
                total_failed += result["failed"]
                print(f"  ✅ Generated: {result['success']}, Failed: {result['failed']}")
            else:
                print(f"  [DRY RUN] Would generate {missing_count} thumbnails")
            
            jobs_processed += 1
            
        except Exception as e:
            print(f"  ❌ Error processing job: {e}")
            logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
    
    return {
        "total_jobs": total_jobs,
        "jobs_processed": jobs_processed,
        "jobs_with_missing": jobs_with_missing,
        "total_missing": total_missing,
        "total_generated": total_generated,
        "total_failed": total_failed
    }


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill thumbnails for existing jobs"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of jobs to process (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check and report only, don't generate thumbnails"
    )
    parser.add_argument(
        "--job-id",
        type=str,
        help="Process specific job ID only"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Backfill Thumbnails for Existing Jobs")
    print("=" * 60)
    
    if args.dry_run:
        print("DRY RUN MODE - No thumbnails will be generated")
    
    # Get jobs to process
    if args.job_id:
        job_ids = [args.job_id]
        print(f"\nProcessing specific job: {args.job_id}")
    else:
        job_ids = await get_jobs_needing_thumbnails(limit=args.limit)
        if not job_ids:
            print("\nNo completed jobs found.")
            return 0
    
    # Process jobs
    summary = await process_jobs(job_ids, dry_run=args.dry_run)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total jobs checked: {summary['total_jobs']}")
    print(f"Jobs processed: {summary['jobs_processed']}")
    print(f"Jobs with missing thumbnails: {summary['jobs_with_missing']}")
    print(f"Total missing thumbnails: {summary['total_missing']}")
    
    if not args.dry_run:
        print(f"Thumbnails generated: {summary['total_generated']}")
        print(f"Thumbnails failed: {summary['total_failed']}")
    
    if summary['total_missing'] > 0 and args.dry_run:
        print("\nRun without --dry-run to generate missing thumbnails")
    
    return 0 if summary['total_failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

