#!/usr/bin/env python3
"""
Test script for Replicate lipsync model with clip 1 and audio 1 from a specific job.

Usage:
    python scripts/test_lipsync_clip1.py
"""
import sys
import os
import asyncio
from pathlib import Path
from uuid import UUID

# Add project/backend to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_path = os.path.join(project_root, 'project/backend')
sys.path.insert(0, backend_path)

# Change to backend directory to find .env file
os.chdir(backend_path)

from dotenv import load_dotenv

# Load .env from backend directory
env_file = Path(backend_path) / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ Loaded .env from: {env_file}")
else:
    load_dotenv()  # Try current directory
    print(f"⚠️  .env file not found at {env_file}, trying environment variables")

from shared.database import DatabaseClient
from shared.storage import StorageClient
from shared.logging import get_logger
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_audio_data_from_job_stages,
    get_audio_url
)
from modules.lipsync_processor.generator import generate_lipsync_clip
from modules.lipsync_processor.audio_trimmer import trim_audio_to_clip
from modules.video_generator.image_handler import parse_supabase_url
import tempfile

logger = get_logger("test_lipsync_clip1")


async def test_lipsync_clip1():
    """Test lipsync model with clip 5 from job."""
    job_id_str = "4bffe66f-e014-479d-8cac-793a3c2a70c9"
    job_id = UUID(job_id_str)
    clip_index = 4  # Clip 5 (0-indexed, so clip_index=4 is the fifth clip)
    
    print("=" * 80)
    print(f"Testing Lipsync Model - Job: {job_id_str}")
    print(f"Target: Clip 5 (clip_index {clip_index})")
    print("=" * 80)
    print()
    
    try:
        # Step 1: Load clips from job
        print("Step 1: Loading clips from job...")
        clips = await load_clips_from_job_stages(job_id)
        if not clips:
            print(f"❌ ERROR: No clips found for job {job_id_str}")
            return
        
        print(f"✅ Found {len(clips.clips)} clips")
        
        # Find clip 5 (clip_index = 4)
        clip_5 = None
        for clip in clips.clips:
            if clip.clip_index == clip_index:
                clip_5 = clip
                break
        
        if not clip_5:
            available_indices = [c.clip_index for c in clips.clips]
            print(f"❌ ERROR: Clip {clip_index} not found. Available indices: {available_indices}")
            return
        
        print(f"✅ Found clip 5 (clip_index {clip_index}):")
        print(f"   Video URL: {clip_5.video_url}")
        print(f"   Duration: {clip_5.actual_duration}s")
        print()
        
        # Step 2: Get audio URL
        print("Step 2: Getting audio URL...")
        audio_url = await get_audio_url(job_id)
        print(f"✅ Audio URL: {audio_url}")
        print()
        
        # Step 3: Load audio analysis to get clip boundaries
        print("Step 3: Loading audio analysis for clip boundaries...")
        audio_analysis = await load_audio_data_from_job_stages(job_id)
        if not audio_analysis:
            print(f"❌ ERROR: Audio analysis not found for job {job_id_str}")
            return
        
        clip_boundaries = audio_analysis.clip_boundaries
        if not clip_boundaries:
            print(f"❌ ERROR: Clip boundaries not found in audio analysis")
            return
        
        if clip_index >= len(clip_boundaries):
            print(f"❌ ERROR: Clip boundary not found for clip_index {clip_index}. Total boundaries: {len(clip_boundaries)}")
            return
        
        boundary = clip_boundaries[clip_index]
        print(f"✅ Clip boundary for clip {clip_index}:")
        print(f"   Start: {boundary.start}s")
        print(f"   End: {boundary.end}s")
        print(f"   Duration: {boundary.duration}s")
        print()
        
        # Step 4: Download and trim audio
        print("Step 4: Downloading and trimming audio...")
        storage = StorageClient()
        bucket, path = parse_supabase_url(audio_url)
        audio_bytes = await storage.download_file(bucket, path)
        print(f"✅ Downloaded audio: {len(audio_bytes)} bytes")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            trimmed_audio_bytes, duration = await trim_audio_to_clip(
                audio_bytes=audio_bytes,
                start_time=boundary.start,
                end_time=boundary.end,
                job_id=job_id,
                temp_dir=temp_path
            )
            print(f"✅ Trimmed audio: {len(trimmed_audio_bytes)} bytes, duration: {duration}s")
            print()
            
            # Step 5: Upload trimmed audio to storage
            print("Step 5: Uploading trimmed audio to storage...")
            trimmed_audio_path = f"{job_id}/test_audio_trimmed_{clip_index}.mp3"
            trimmed_audio_url = await storage.upload_file(
                bucket="audio-uploads",
                path=trimmed_audio_path,
                file_data=trimmed_audio_bytes,
                content_type="audio/mpeg"
            )
            print(f"✅ Trimmed audio URL: {trimmed_audio_url}")
            print()
            
            # Step 6: Generate lipsynced clip
            print("Step 6: Generating lipsynced clip via Replicate...")
            print("   This may take 60-180 seconds...")
            print()
            
            try:
                lipsynced_clip = await generate_lipsync_clip(
                    video_url=clip_5.video_url,
                    audio_url=trimmed_audio_url,
                    clip_index=clip_index,
                    job_id=job_id,
                    environment="development",
                    progress_callback=None,
                    character_ids=None
                )
                
                print("=" * 80)
                print("✅ SUCCESS! Lipsync generation completed")
                print("=" * 80)
                print(f"Lipsynced video URL: {lipsynced_clip.video_url}")
                print(f"Cost: ${lipsynced_clip.cost}")
                print(f"Generation time: {lipsynced_clip.generation_time:.2f}s")
                print()
                
                # Cleanup trimmed audio
                try:
                    await storage.delete_file("audio-uploads", trimmed_audio_path)
                    print("✅ Cleaned up temporary trimmed audio file")
                except Exception as e:
                    print(f"⚠️  Warning: Failed to cleanup trimmed audio: {e}")
                
            except Exception as e:
                print("=" * 80)
                print(f"❌ ERROR: Lipsync generation failed")
                print("=" * 80)
                print(f"Error: {str(e)}")
                print(f"Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                
                # Cleanup trimmed audio even on error
                try:
                    await storage.delete_file("audio-uploads", trimmed_audio_path)
                except Exception:
                    pass
                raise
        
    except Exception as e:
        print("=" * 80)
        print(f"❌ FATAL ERROR")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_lipsync_clip1())

