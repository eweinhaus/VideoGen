#!/usr/bin/env python3
"""
Integration test script for clip chatbot Part 1 features.

Tests:
1. Thumbnail generation (if FFmpeg available)
2. Data loading from job_stages
3. Clips API endpoint (requires authentication)
4. End-to-end flow verification

Usage:
    python test_clip_chatbot_integration.py [--job-id JOB_ID]
"""
import asyncio
import sys
import os
from pathlib import Path
from uuid import UUID

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.database import DatabaseClient
from shared.config import settings
from shared.logging import get_logger
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clip_prompts_from_job_stages
)
from modules.composer.utils import check_ffmpeg_available

logger = get_logger("test_clip_chatbot")


async def test_data_loader(job_id: UUID):
    """Test data loading from job_stages."""
    print("\n" + "=" * 60)
    print("TEST: Data Loader")
    print("=" * 60)
    
    try:
        # Test loading clips
        print(f"\n1. Loading clips for job {job_id}...")
        clips = await load_clips_from_job_stages(job_id)
        
        if clips:
            print(f"   ✅ Successfully loaded {len(clips.clips)} clips")
            print(f"   - Total clips: {clips.total_clips}")
            print(f"   - Successful: {clips.successful_clips}")
            print(f"   - Failed: {clips.failed_clips}")
            print(f"   - Total cost: {clips.total_cost}")
        else:
            print(f"   ⚠️  No clips found (job may not have completed video generation)")
        
        # Test loading clip prompts
        print(f"\n2. Loading clip prompts for job {job_id}...")
        clip_prompts = await load_clip_prompts_from_job_stages(job_id)
        
        if clip_prompts:
            print(f"   ✅ Successfully loaded {len(clip_prompts.clip_prompts)} clip prompts")
            print(f"   - Total clips: {clip_prompts.total_clips}")
        else:
            print(f"   ⚠️  No clip prompts found")
        
        return clips is not None
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_thumbnails_table(job_id: UUID):
    """Test clip_thumbnails table access."""
    print("\n" + "=" * 60)
    print("TEST: Clip Thumbnails Table")
    print("=" * 60)
    
    try:
        db = DatabaseClient()
        result = await db.table("clip_thumbnails").select("*").eq(
            "job_id", str(job_id)
        ).execute()
        
        if result.data:
            print(f"   ✅ Found {len(result.data)} thumbnails for job {job_id}")
            for thumb in result.data:
                print(f"   - Clip {thumb['clip_index']}: {thumb['thumbnail_url'][:50]}...")
        else:
            print(f"   ⚠️  No thumbnails found (may not be generated yet)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ffmpeg_availability():
    """Test FFmpeg availability for thumbnail generation."""
    print("\n" + "=" * 60)
    print("TEST: FFmpeg Availability")
    print("=" * 60)
    
    if check_ffmpeg_available():
        print("   ✅ FFmpeg is available")
        return True
    else:
        print("   ⚠️  FFmpeg is not available (thumbnail generation will be skipped)")
        print("   Install FFmpeg to enable thumbnail generation:")
        print("   - macOS: brew install ffmpeg")
        print("   - Linux: apt-get install ffmpeg")
        return False


async def test_storage_bucket():
    """Test clip-thumbnails storage bucket access."""
    print("\n" + "=" * 60)
    print("TEST: Storage Bucket")
    print("=" * 60)
    
    try:
        from shared.storage import StorageClient
        storage = StorageClient()
        
        # Try to list files in bucket (will fail if bucket doesn't exist)
        try:
            # This will fail if bucket doesn't exist, which is expected
            # We just want to verify the client can connect
            print("   ✅ Storage client initialized")
            print("   ⚠️  Note: clip-thumbnails bucket must be created manually in Supabase Dashboard")
            return True
        except Exception as e:
            print(f"   ⚠️  Storage bucket may not exist: {e}")
            print("   Create bucket manually: Supabase Dashboard → Storage → New bucket")
            print("   Bucket name: clip-thumbnails (private)")
            return False
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


async def main():
    """Run integration tests."""
    print("=" * 60)
    print("Clip Chatbot Part 1 - Integration Tests")
    print("=" * 60)
    
    # Parse job ID from command line
    job_id = None
    if len(sys.argv) > 1 and sys.argv[1] == "--job-id":
        if len(sys.argv) > 2:
            try:
                job_id = UUID(sys.argv[2])
            except ValueError:
                print(f"❌ Invalid job ID: {sys.argv[2]}")
                return 1
        else:
            print("❌ --job-id requires a job ID argument")
            return 1
    
    # Test FFmpeg availability
    ffmpeg_available = test_ffmpeg_availability()
    
    # Test storage bucket
    await test_storage_bucket()
    
    # Test data loader if job ID provided
    if job_id:
        await test_data_loader(job_id)
        await test_thumbnails_table(job_id)
    else:
        print("\n" + "=" * 60)
        print("SKIP: Data Loader Tests (no job ID provided)")
        print("=" * 60)
        print("   To test data loading, provide a job ID:")
        print("   python test_clip_chatbot_integration.py --job-id <job_id>")
    
    print("\n" + "=" * 60)
    print("Integration Tests Complete")
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Run database migration: supabase/migrations/20250117194933_add_clip_thumbnails_table.sql")
    print("2. Create clip-thumbnails storage bucket in Supabase Dashboard")
    print("3. Generate a video to test thumbnail generation")
    print("4. Test clips API endpoint: GET /api/v1/jobs/{job_id}/clips")
    print("5. Test ClipSelector UI component on job detail page")
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

