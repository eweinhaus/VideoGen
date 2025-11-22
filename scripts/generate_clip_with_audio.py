#!/usr/bin/env python3
"""
Generate a video clip with audio attached.

This script takes a clip from a job, downloads it, trims the audio to match
the clip boundaries, and combines them into a single video file with audio.

Usage:
    python scripts/generate_clip_with_audio.py <job_id> <clip_index>
    
Example:
    python scripts/generate_clip_with_audio.py 4bffe66f-e014-479d-8cac-793a3c2a70c9 4
"""
import sys
import os
import asyncio
from pathlib import Path
from uuid import UUID
import tempfile

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
    load_dotenv()
    print(f"⚠️  .env file not found at {env_file}, trying environment variables")

from shared.storage import StorageClient
from shared.logging import get_logger
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_audio_data_from_job_stages,
    get_audio_url
)
from modules.lipsync_processor.audio_trimmer import trim_audio_to_clip
from modules.composer.audio_syncer import sync_audio
from modules.video_generator.image_handler import parse_supabase_url

logger = get_logger("generate_clip_with_audio")


async def generate_clip_with_audio(job_id_str: str, clip_index: int):
    """Generate a video clip with audio attached."""
    job_id = UUID(job_id_str)
    
    print("=" * 80)
    print(f"Generating Clip with Audio")
    print("=" * 80)
    print(f"Job ID: {job_id_str}")
    print(f"Clip Index: {clip_index}")
    print()
    
    try:
        # Step 1: Load clips from job
        print("Step 1: Loading clips from job...")
        clips = await load_clips_from_job_stages(job_id)
        if not clips:
            print(f"❌ ERROR: No clips found for job {job_id_str}")
            return
        
        print(f"✅ Found {len(clips.clips)} clips")
        
        # Find the target clip
        target_clip = None
        for clip in clips.clips:
            if clip.clip_index == clip_index:
                target_clip = clip
                break
        
        if not target_clip:
            available_indices = [c.clip_index for c in clips.clips]
            print(f"❌ ERROR: Clip {clip_index} not found. Available indices: {available_indices}")
            return
        
        print(f"✅ Found clip {clip_index}:")
        print(f"   Video URL: {target_clip.video_url}")
        print(f"   Duration: {target_clip.actual_duration}s")
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
        
        # Step 4: Download video clip
        print("Step 4: Downloading video clip...")
        storage = StorageClient()
        video_bucket, video_path = parse_supabase_url(target_clip.video_url)
        video_bytes = await storage.download_file(video_bucket, video_path)
        print(f"✅ Downloaded video: {len(video_bytes)} bytes")
        print()
        
        # Step 5: Download and trim audio
        print("Step 5: Downloading and trimming audio...")
        audio_bucket, audio_path = parse_supabase_url(audio_url)
        audio_bytes = await storage.download_file(audio_bucket, audio_path)
        print(f"✅ Downloaded audio: {len(audio_bytes)} bytes")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Write video to temp file
            video_file = temp_path / "video.mp4"
            video_file.write_bytes(video_bytes)
            print(f"✅ Wrote video to temp file: {video_file}")
            
            # Trim audio to clip boundaries
            trimmed_audio_bytes, duration = await trim_audio_to_clip(
                audio_bytes=audio_bytes,
                start_time=boundary.start,
                end_time=boundary.end,
                job_id=job_id,
                temp_dir=temp_path
            )
            print(f"✅ Trimmed audio: {len(trimmed_audio_bytes)} bytes, duration: {duration}s")
            print()
            
            # Step 6: Sync audio with video
            print("Step 6: Combining video and audio...")
            print("   This may take a few seconds...")
            print()
            
            try:
                output_path, sync_drift = await sync_audio(
                    video_path=video_file,
                    audio_bytes=trimmed_audio_bytes,
                    temp_dir=temp_path,
                    job_id=job_id
                )
                
                print(f"✅ Video and audio combined successfully")
                print(f"   Output file: {output_path}")
                print(f"   Sync drift: {sync_drift:.3f}s")
                print()
                
                # Step 7: Upload result to storage
                print("Step 7: Uploading clip with audio to storage...")
                output_bytes = output_path.read_bytes()
                output_storage_path = f"{job_id}/clip_{clip_index}_with_audio.mp4"
                
                output_url = await storage.upload_file(
                    bucket="video-clips",
                    path=output_storage_path,
                    file_data=output_bytes,
                    content_type="video/mp4"
                )
                
                print("=" * 80)
                print("✅ SUCCESS! Clip with audio generated")
                print("=" * 80)
                print(f"Output URL: {output_url}")
                print(f"File size: {len(output_bytes)} bytes")
                print(f"Sync drift: {sync_drift:.3f}s")
                print()
                print("📋 Copy this URL to access the clip with audio")
                print()
                
            except Exception as e:
                print("=" * 80)
                print(f"❌ ERROR: Failed to combine video and audio")
                print("=" * 80)
                print(f"Error: {str(e)}")
                print(f"Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
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
    if len(sys.argv) != 3:
        print("Usage: python scripts/generate_clip_with_audio.py <job_id> <clip_index>")
        print()
        print("Example:")
        print("  python scripts/generate_clip_with_audio.py 4bffe66f-e014-479d-8cac-793a3c2a70c9 4")
        sys.exit(1)
    
    job_id_str = sys.argv[1]
    try:
        clip_index = int(sys.argv[2])
    except ValueError:
        print(f"❌ ERROR: Invalid clip_index '{sys.argv[2]}'. Must be a number.")
        sys.exit(1)
    
    asyncio.run(generate_clip_with_audio(job_id_str, clip_index))

