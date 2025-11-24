#!/usr/bin/env python3
"""
Script to re-process a specific clip through lipsync and replace it in Supabase.

Usage:
    python scripts/relipsync_clip.py <job_id> <ui_clip_number>

Example:
    python scripts/relipsync_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 3

Note: UI clips are labeled from 1 and up, but Supabase clips are labeled from 0 and up.
      So UI clip 3 = Supabase clip index 2.
"""
import asyncio
import sys
import json
import os
from uuid import UUID
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
project_root = Path(__file__).parent.parent
env_paths = [
    project_root / ".env",
    project_root / "project" / "backend" / ".env",
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    # Try loading from current directory if no .env found
    load_dotenv()

# Add project root to path
sys.path.insert(0, str(project_root / "project" / "backend"))

from shared.database import DatabaseClient
from shared.logging import get_logger
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clips_with_latest_versions,
    load_audio_data_from_job_stages,
    load_transitions_from_job_stages,
    load_beat_timestamps_from_job_stages,
    get_audio_url,
    get_aspect_ratio
)
from modules.lipsync_processor.process import process_single_clip_lipsync
from modules.composer.process import process as compose_video
from shared.models.video import Clip
from api_gateway.services.db_helpers import update_job_stage, make_json_serializable

logger = get_logger(__name__)
db = DatabaseClient()


async def relipsync_clip(job_id: str, ui_clip_number: int):
    """
    Re-process a specific clip through lipsync and replace it in Supabase.
    
    Args:
        job_id: Job ID
        ui_clip_number: UI clip number (1-indexed)
    """
    # Convert UI clip number to Supabase clip index (0-indexed)
    clip_index = ui_clip_number - 1
    
    print(f"🔄 Re-processing UI clip {ui_clip_number} (Supabase index {clip_index}) through lipsync...")
    print(f"   Job ID: {job_id}")
    print("-" * 80)
    
    # Step 1: Load job to get audio URL
    print(f"\n📋 STEP 1: Loading job data...")
    try:
        job_result = await db.table("jobs").select("audio_url, status").eq("id", job_id).execute()
        
        if not job_result.data or len(job_result.data) == 0:
            print(f"❌ Job {job_id} not found")
            return
        
        job_data = job_result.data[0]
        audio_url = job_data.get("audio_url")
        job_status = job_data.get("status")
        
        if not audio_url:
            print(f"❌ No audio URL found for job {job_id}")
            return
        
        print(f"✅ Job found (status: {job_status})")
        print(f"   Audio URL: {audio_url[:80]}...")
        
    except Exception as e:
        print(f"❌ Failed to load job: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 2: Load clips with latest versions (includes regenerated versions)
    print(f"\n📦 STEP 2: Loading clips with latest versions...")
    try:
        # Use load_clips_with_latest_versions to get current version of clips
        # This includes any regenerated versions, not just the originals
        clips = await load_clips_with_latest_versions(UUID(job_id))
        
        if not clips:
            print(f"❌ No clips found for job {job_id}")
            return
        
        if clip_index >= len(clips.clips):
            print(f"❌ Clip index {clip_index} out of range. Total clips: {len(clips.clips)}")
            print(f"   Available clip indices: 0-{len(clips.clips) - 1}")
            return
        
        target_clip = clips.clips[clip_index]
        print(f"✅ Found {len(clips.clips)} clips (with latest versions)")
        print(f"   Target clip index: {clip_index}")
        print(f"   Current video URL: {target_clip.video_url[:80]}...")
        print(f"   Duration: {target_clip.actual_duration:.2f}s (target: {target_clip.target_duration:.2f}s)")
        print(f"   Note: Using current version of clip (may be regenerated version)")
        
    except Exception as e:
        print(f"❌ Failed to load clips: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Verify audio analysis exists
    print(f"\n🎵 STEP 3: Verifying audio analysis...")
    try:
        audio_analysis = await load_audio_data_from_job_stages(UUID(job_id))
        
        if not audio_analysis:
            print(f"❌ No audio analysis found for job {job_id}")
            return
        
        if not audio_analysis.clip_boundaries or clip_index >= len(audio_analysis.clip_boundaries):
            print(f"❌ Clip boundary not found for clip index {clip_index}")
            if audio_analysis.clip_boundaries:
                print(f"   Available boundaries: 0-{len(audio_analysis.clip_boundaries) - 1}")
            return
        
        boundary = audio_analysis.clip_boundaries[clip_index]
        print(f"✅ Audio analysis found")
        print(f"   Clip boundary: {boundary.start:.2f}s - {boundary.end:.2f}s (duration: {boundary.duration:.2f}s)")
        
    except Exception as e:
        print(f"❌ Failed to load audio analysis: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 4: Clean up any existing trimmed audio file first
    print(f"\n🧹 STEP 4a: Cleaning up any existing trimmed audio file...")
    try:
        from shared.storage import StorageClient
        storage = StorageClient()
        trimmed_audio_path = f"{job_id}/audio_trimmed_{clip_index}.mp3"
        try:
            await storage.delete_file("audio-uploads", trimmed_audio_path)
            print(f"✅ Deleted existing trimmed audio file")
        except Exception as e:
            # File might not exist, which is fine
            print(f"   ℹ️  No existing file to delete (or already deleted): {e}")
    except Exception as e:
        print(f"⚠️  Warning: Could not clean up existing file: {e}")
        # Continue anyway
    
    # Step 4: Process clip through lipsync
    print(f"\n🎬 STEP 4: Processing clip through lipsync...")
    try:
        # Create a simple async event publisher for logging
        async def event_publisher(event_type: str, event_data: dict):
            print(f"   📢 Event: {event_type} - {json.dumps(event_data, indent=6)[:100]}...")
        
        lipsynced_clip = await process_single_clip_lipsync(
            clip=target_clip,
            clip_index=clip_index,
            audio_url=audio_url,
            job_id=UUID(job_id),
            environment="production",
            event_publisher=event_publisher
        )
        
        print(f"✅ Lipsync processing complete")
        print(f"   New video URL: {lipsynced_clip.video_url[:80]}...")
        print(f"   Cost: ${lipsynced_clip.cost}")
        print(f"   Generation time: {lipsynced_clip.generation_time:.2f}s")
        
    except Exception as e:
        print(f"❌ Failed to process lipsync: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Update clip in job_stages metadata
    print(f"\n💾 STEP 5: Updating clip in job_stages metadata...")
    try:
        # Load current metadata
        stage_result = await db.table("job_stages").select("metadata").eq(
            "job_id", job_id
        ).eq("stage_name", "video_generator").execute()
        
        if not stage_result.data or len(stage_result.data) == 0:
            print(f"❌ No video_generator stage found in job_stages")
            return
        
        metadata = stage_result.data[0].get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        elif not isinstance(metadata, dict):
            metadata = {}
        
        # Update clips in metadata
        if "clips" not in metadata:
            metadata["clips"] = {"clips": []}
        
        clips_data = metadata.get("clips", {})
        if isinstance(clips_data, list):
            clips_data = {"clips": clips_data}
        
        clips_list = clips_data.get("clips", [])
        
        # Find and update the clip
        clip_found = False
        for i, existing_clip in enumerate(clips_list):
            if existing_clip.get("clip_index") == clip_index:
                # Convert lipsynced_clip to dict for storage
                lipsynced_clip_dict = lipsynced_clip.model_dump()
                # Ensure all fields are JSON serializable
                lipsynced_clip_dict = make_json_serializable(lipsynced_clip_dict)
                clips_list[i] = lipsynced_clip_dict
                clip_found = True
                print(f"✅ Updated clip at position {i} in metadata")
                break
        
        if not clip_found:
            print(f"⚠️  Clip not found in metadata, adding as new clip")
            lipsynced_clip_dict = lipsynced_clip.model_dump()
            lipsynced_clip_dict = make_json_serializable(lipsynced_clip_dict)
            clips_list.append(lipsynced_clip_dict)
        
        # Update metadata structure
        clips_data["clips"] = clips_list
        metadata["clips"] = clips_data
        
        # Recalculate totals if needed
        successful_clips = sum(1 for clip in clips_list if clip.get("status") == "success")
        failed_clips = sum(1 for clip in clips_list if clip.get("status") == "failed")
        clips_data["total_clips"] = len(clips_list)
        clips_data["successful_clips"] = successful_clips
        clips_data["failed_clips"] = failed_clips
        
        # Calculate total cost
        from decimal import Decimal
        total_cost = Decimal("0.00")
        for clip in clips_list:
            cost = clip.get("cost", 0)
            if isinstance(cost, str):
                total_cost += Decimal(cost)
            elif isinstance(cost, (int, float)):
                total_cost += Decimal(str(cost))
            elif isinstance(cost, Decimal):
                total_cost += cost
        clips_data["total_cost"] = str(total_cost)
        
        # Calculate total generation time
        total_time = sum(clip.get("generation_time", 0) for clip in clips_list)
        clips_data["total_generation_time"] = total_time
        
        # Update job_stages
        await update_job_stage(
            job_id=job_id,
            stage_name="video_generator",
            status="completed",
            metadata=metadata
        )
        
        print(f"✅ Successfully updated job_stages metadata")
        print(f"   Total clips: {clips_data['total_clips']}")
        print(f"   Successful: {clips_data['successful_clips']}")
        print(f"   Failed: {clips_data['failed_clips']}")
        print(f"   Total cost: ${clips_data['total_cost']}")
        
    except Exception as e:
        print(f"❌ Failed to update job_stages: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 6: Recompose final video with updated clip
    print(f"\n🎞️  STEP 6: Recomposing final video with updated clip...")
    try:
        # Load composer inputs
        composer_audio_url = await get_audio_url(UUID(job_id))
        transitions = await load_transitions_from_job_stages(UUID(job_id))
        beat_timestamps = await load_beat_timestamps_from_job_stages(UUID(job_id))
        aspect_ratio = await get_aspect_ratio(UUID(job_id))
        
        print(f"✅ Loaded composer inputs")
        print(f"   Audio URL: {composer_audio_url[:80]}...")
        print(f"   Transitions: {len(transitions)}")
        print(f"   Beat timestamps: {len(beat_timestamps) if beat_timestamps else 0}")
        print(f"   Aspect ratio: {aspect_ratio}")
        
        # Reload clips with latest versions to get the updated version
        updated_clips = await load_clips_with_latest_versions(UUID(job_id))
        if not updated_clips:
            print(f"❌ Failed to reload clips for recomposition")
            return
        
        print(f"✅ Reloaded {len(updated_clips.clips)} clips for recomposition")
        
        # Call composer
        print(f"   Starting video composition...")
        video_output = await compose_video(
            job_id=job_id,
            clips=updated_clips,
            audio_url=composer_audio_url,
            transitions=transitions or [],
            beat_timestamps=beat_timestamps or [],
            aspect_ratio=aspect_ratio,
            changed_clip_index=clip_index
        )
        
        print(f"✅ Video recomposition complete")
        print(f"   New video URL: {video_output.video_url[:80]}...")
        print(f"   Duration: {video_output.duration:.2f}s")
        print(f"   Composition time: {video_output.composition_time:.2f}s")
        print(f"   File size: {video_output.file_size_mb:.2f} MB")
        
        # Update job with new video URL
        await db.table("jobs").update({
            "video_url": video_output.video_url,
            "status": "completed",
            "progress": 100,
            "current_stage": "composer",
            "updated_at": "now()"
        }).eq("id", job_id).execute()
        
        print(f"✅ Updated job with new final video URL")
        
    except Exception as e:
        print(f"❌ Failed to recompose video: {e}")
        import traceback
        traceback.print_exc()
        print(f"⚠️  Warning: Clip was updated but final video was not recomposed")
        print(f"   You may need to manually trigger recomposition")
        return
    
    print("\n" + "=" * 80)
    print("✅ SUCCESS: Clip re-processed through lipsync, updated in Supabase, and final video recomposed")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Job ID: {job_id}")
    print(f"  UI Clip Number: {ui_clip_number}")
    print(f"  Supabase Clip Index: {clip_index}")
    print(f"  Old Clip URL: {target_clip.video_url[:80]}...")
    print(f"  New Clip URL: {lipsynced_clip.video_url[:80]}...")
    print(f"  Lipsync Cost: ${lipsynced_clip.cost}")
    print(f"  Lipsync Time: {lipsynced_clip.generation_time:.2f}s")
    print(f"  Final Video URL: {video_output.video_url[:80]}...")
    print(f"  Final Video Duration: {video_output.duration:.2f}s")


async def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python scripts/relipsync_clip.py <job_id> <ui_clip_number>")
        print("\nExample:")
        print("  python scripts/relipsync_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 3")
        print("\nNote: UI clips are labeled from 1 and up, but Supabase clips are labeled from 0 and up.")
        print("      So UI clip 3 = Supabase clip index 2.")
        sys.exit(1)
    
    job_id = sys.argv[1]
    try:
        ui_clip_number = int(sys.argv[2])
        if ui_clip_number < 1:
            print("❌ UI clip number must be >= 1")
            sys.exit(1)
    except ValueError:
        print("❌ Invalid UI clip number. Must be an integer >= 1")
        sys.exit(1)
    
    try:
        await relipsync_clip(job_id, ui_clip_number)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

