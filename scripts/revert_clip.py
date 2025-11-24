#!/usr/bin/env python3
"""
Script to revert a clip to a specific version.

Usage:
    python scripts/revert_clip.py <job_id> <ui_clip_number> [version_number]

Example:
    python scripts/revert_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 3 1
    python scripts/revert_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 5 1

Note: UI clips are labeled from 1 and up, but Supabase clips are labeled from 0 and up.
      So UI clip 3 = Supabase clip index 2.
      Version 1 is always the original clip.
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
    get_audio_url,
    load_transitions_from_job_stages,
    load_beat_timestamps_from_job_stages,
    get_aspect_ratio
)
from modules.composer.process import process as compose_video
from api_gateway.services.db_helpers import update_job_stage, make_json_serializable

logger = get_logger(__name__)
db = DatabaseClient()


async def revert_clip(job_id: str, ui_clip_number: int, version_number: int = 1):
    """
    Revert a clip to a specific version and recompose the video.
    
    Args:
        job_id: Job ID
        ui_clip_number: UI clip number (1-indexed)
        version_number: Version number to revert to (1 = original, default)
    """
    # Convert UI clip number to Supabase clip index (0-indexed)
    clip_index = ui_clip_number - 1
    
    print(f"🔄 Reverting UI clip {ui_clip_number} (Supabase index {clip_index}) to version {version_number}...")
    print(f"   Job ID: {job_id}")
    print("-" * 80)
    
    # Step 1: Load clips with latest versions
    print(f"\n📦 STEP 1: Loading clips with latest versions...")
    try:
        clips = await load_clips_with_latest_versions(UUID(job_id))
        
        if not clips:
            print(f"❌ No clips found for job {job_id}")
            return
        
        if clip_index >= len(clips.clips):
            print(f"❌ Clip index {clip_index} out of range. Total clips: {len(clips.clips)}")
            return
        
        current_clip = clips.clips[clip_index]
        print(f"✅ Found {len(clips.clips)} clips")
        print(f"   Current clip index: {clip_index}")
        print(f"   Current video URL: {current_clip.video_url[:80]}...")
        
    except Exception as e:
        print(f"❌ Failed to load clips: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 2: Get the version to revert to
    print(f"\n🔍 STEP 2: Finding version {version_number}...")
    try:
        if version_number == 1:
            # Load original from job_stages
            original_clips = await load_clips_from_job_stages(UUID(job_id))
            if not original_clips or clip_index >= len(original_clips.clips):
                print(f"❌ Original clip not found")
                return
            
            target_clip = original_clips.clips[clip_index]
            print(f"✅ Found original clip (version 1)")
            print(f"   Original video URL: {target_clip.video_url[:80]}...")
        else:
            # Load from clip_versions table
            result = await db.table("clip_versions").select("*").eq(
                "job_id", job_id
            ).eq("clip_index", clip_index).eq("version_number", version_number).limit(1).execute()
            
            if not result.data or len(result.data) == 0:
                print(f"❌ Version {version_number} not found for clip {clip_index}")
                return
            
            version_data = result.data[0]
            from shared.models.video import Clip
            from decimal import Decimal
            
            # Create Clip object from version data
            target_clip = Clip(
                clip_index=clip_index,
                video_url=version_data.get("video_url"),
                actual_duration=current_clip.actual_duration,  # Preserve current duration
                target_duration=current_clip.target_duration,
                original_target_duration=current_clip.original_target_duration,
                duration_diff=current_clip.duration_diff,
                status="success",
                cost=Decimal(str(version_data.get("cost", 0))),
                retry_count=0,
                generation_time=0.0,
                metadata={}
            )
            print(f"✅ Found version {version_number}")
            print(f"   Version video URL: {target_clip.video_url[:80]}...")
        
        if current_clip.video_url == target_clip.video_url:
            print(f"⚠️  Clip is already at version {version_number}, no change needed")
            return
        
    except Exception as e:
        print(f"❌ Failed to find version: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Update clip in clips list
    print(f"\n💾 STEP 3: Updating clip in memory...")
    try:
        # Replace the clip in the clips list
        clips.clips[clip_index] = target_clip
        print(f"✅ Updated clip in memory")
        
    except Exception as e:
        print(f"❌ Failed to update clip: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 4: Update job_stages metadata
    print(f"\n💾 STEP 4: Updating job_stages metadata...")
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
                # Convert target_clip to dict for storage
                target_clip_dict = target_clip.model_dump()
                # Ensure all fields are JSON serializable
                target_clip_dict = make_json_serializable(target_clip_dict)
                clips_list[i] = target_clip_dict
                clip_found = True
                print(f"✅ Updated clip at position {i} in metadata")
                break
        
        if not clip_found:
            print(f"⚠️  Clip not found in metadata, adding as new clip")
            target_clip_dict = target_clip.model_dump()
            target_clip_dict = make_json_serializable(target_clip_dict)
            clips_list.append(target_clip_dict)
        
        # Update metadata structure
        clips_data["clips"] = clips_list
        metadata["clips"] = clips_data
        
        # Update job_stages
        await update_job_stage(
            job_id=job_id,
            stage_name="video_generator",
            status="completed",
            metadata=metadata
        )
        
        print(f"✅ Successfully updated job_stages metadata")
        
    except Exception as e:
        print(f"❌ Failed to update job_stages: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Update clip_versions is_current flags
    print(f"\n🏷️  STEP 5: Updating clip_versions is_current flags...")
    try:
        # Set all versions for this clip to is_current=False
        await db.table("clip_versions").update({"is_current": False}).eq(
            "job_id", job_id
        ).eq("clip_index", clip_index).execute()
        
        # Set the target version to is_current=True (if it exists in clip_versions)
        if version_number > 1:
            await db.table("clip_versions").update({"is_current": True}).eq(
                "job_id", job_id
            ).eq("clip_index", clip_index).eq("version_number", version_number).execute()
            print(f"✅ Set version {version_number} as current")
        else:
            print(f"✅ Cleared is_current flags (reverted to original)")
        
    except Exception as e:
        print(f"⚠️  Warning: Failed to update clip_versions flags: {e}")
        # Non-critical, continue
    
    # Step 6: Recompose final video
    print(f"\n🎞️  STEP 6: Recomposing final video with reverted clip...")
    try:
        # Load composer inputs
        composer_audio_url = await get_audio_url(UUID(job_id))
        transitions = await load_transitions_from_job_stages(UUID(job_id))
        beat_timestamps = await load_beat_timestamps_from_job_stages(UUID(job_id))
        aspect_ratio = await get_aspect_ratio(UUID(job_id))
        
        print(f"✅ Loaded composer inputs")
        
        # Call composer with updated clips
        print(f"   Starting video composition...")
        video_output = await compose_video(
            job_id=job_id,
            clips=clips,
            audio_url=composer_audio_url,
            transitions=transitions or [],
            beat_timestamps=beat_timestamps or [],
            aspect_ratio=aspect_ratio,
            changed_clip_index=clip_index
        )
        
        print(f"✅ Video recomposition complete")
        print(f"   New video URL: {video_output.video_url[:80]}...")
        print(f"   Duration: {video_output.duration:.2f}s")
        
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
        return
    
    print("\n" + "=" * 80)
    print("✅ SUCCESS: Clip reverted and final video recomposed")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Job ID: {job_id}")
    print(f"  UI Clip Number: {ui_clip_number}")
    print(f"  Supabase Clip Index: {clip_index}")
    print(f"  Reverted to Version: {version_number}")
    print(f"  Old URL: {current_clip.video_url[:80]}...")
    print(f"  New URL: {target_clip.video_url[:80]}...")
    print(f"  Final Video URL: {video_output.video_url[:80]}...")


async def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python scripts/revert_clip.py <job_id> <ui_clip_number> [version_number]")
        print("\nExample:")
        print("  python scripts/revert_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 3 1")
        print("  python scripts/revert_clip.py ec23b2a2-94ad-4f5c-a274-4cc5cbbff458 5 1")
        print("\nNote: UI clips are labeled from 1 and up, but Supabase clips are labeled from 0 and up.")
        print("      So UI clip 3 = Supabase clip index 2.")
        print("      Version 1 is always the original clip.")
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
    
    version_number = 1  # Default to original
    if len(sys.argv) >= 4:
        try:
            version_number = int(sys.argv[3])
            if version_number < 1:
                print("❌ Version number must be >= 1")
                sys.exit(1)
        except ValueError:
            print("❌ Invalid version number. Must be an integer >= 1")
            sys.exit(1)
    
    try:
        await revert_clip(job_id, ui_clip_number, version_number)
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

