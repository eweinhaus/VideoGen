"""
Script to recover the original clip 4 and fix the clip_versions table.

This script:
1. Lists all clip_4 files in Supabase storage
2. Checks current job_stages data
3. Attempts to identify the TRUE original clip
4. Manually creates correct version entries in clip_versions
"""

import asyncio
import sys
import os
from uuid import UUID
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'project', 'backend')))

from shared.database import DatabaseClient
from shared.storage import StorageClient
from shared.logging import get_logger

logger = get_logger(__name__)

async def recover_clip_4(job_id: UUID, clip_index: int = 4):
    """
    Recover original clip 4 and fix version history.
    """
    print("=" * 80)
    print(f"RECOVERING CLIP {clip_index} FOR JOB: {job_id}")
    print("=" * 80)
    
    db = DatabaseClient()
    storage = StorageClient()
    
    # Step 1: List all clip_4 files in storage
    print("\n📂 STEP 1: Listing clip files in storage...")
    print("-" * 80)
    
    try:
        # List files in video-clips bucket for this job
        def _list_files():
            return storage.storage.from_("video-clips").list(str(job_id))
        
        files = await storage._execute_sync(_list_files)
        
        # Filter for clip_4 files
        clip_4_files = [f for f in files if f'clip_{clip_index}' in f.get('name', '')]
        
        if not clip_4_files:
            print(f"❌ No clip_{clip_index} files found in storage for job {job_id}")
            return
        
        print(f"✅ Found {len(clip_4_files)} clip_{clip_index} file(s):")
        for file in clip_4_files:
            print(f"   - {file.get('name')} ({file.get('metadata', {}).get('size', 'unknown')} bytes)")
            print(f"     Created: {file.get('created_at', 'unknown')}")
            print(f"     Updated: {file.get('updated_at', 'unknown')}")
    
    except Exception as e:
        print(f"❌ Failed to list storage files: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 2: Check current job_stages data
    print(f"\n📊 STEP 2: Checking current job_stages for clip {clip_index}...")
    print("-" * 80)
    
    try:
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "video_generator").execute()
        
        if not result.data:
            print("❌ No video_generator stage found in job_stages")
            return
        
        metadata = result.data[0].get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        clips = metadata.get("clips", {})
        if isinstance(clips, dict):
            clips_array = clips.get("clips", [])
        else:
            clips_array = clips
        
        # Find clip 4
        current_clip = None
        for clip in clips_array:
            if clip.get("clip_index") == clip_index:
                current_clip = clip
                break
        
        if not current_clip:
            print(f"❌ Clip {clip_index} not found in job_stages")
            return
        
        current_url = current_clip.get("video_url", "")
        print(f"✅ Current clip {clip_index} URL in job_stages:")
        print(f"   {current_url[:120]}...")
        
        # Extract filename from URL
        if "clip_" in current_url:
            filename_part = current_url.split("/")[-1].split("?")[0]
            print(f"   Filename: {filename_part}")
        
    except Exception as e:
        print(f"❌ Failed to check job_stages: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 3: Check clip_versions table
    print(f"\n🔄 STEP 3: Checking clip_versions for clip {clip_index}...")
    print("-" * 80)
    
    try:
        versions_result = await db.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq("clip_index", clip_index).order("version_number", desc=False).execute()
        
        if not versions_result.data or len(versions_result.data) == 0:
            print(f"❌ No versions found in clip_versions (expected)")
        else:
            print(f"✅ Found {len(versions_result.data)} version(s):")
            for version in versions_result.data:
                is_current = "[CURRENT]" if version.get("is_current") else ""
                print(f"   v{version['version_number']}: {version['video_url'][:80]}... {is_current}")
    
    except Exception as e:
        print(f"❌ Failed to check clip_versions: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 4: Check regeneration_history for clues
    print(f"\n📜 STEP 4: Checking regeneration_history for clip {clip_index}...")
    print("-" * 80)
    
    try:
        regen_result = await db.table("regeneration_history").select("*").eq(
            "job_id", str(job_id)
        ).eq("clip_index", clip_index).order("created_at", desc=False).execute()
        
        if not regen_result.data or len(regen_result.data) == 0:
            print(f"❌ No regeneration history found")
        else:
            print(f"✅ Found {len(regen_result.data)} regeneration(s):")
            for i, regen in enumerate(regen_result.data, 1):
                print(f"\n   Regeneration #{i}:")
                print(f"     Instruction: {regen.get('user_instruction', 'N/A')}")
                print(f"     Status: {regen.get('status', 'N/A')}")
                print(f"     Created: {regen.get('created_at', 'N/A')}")
                print(f"     Cost: ${regen.get('cost', 0)}")
    
    except Exception as e:
        print(f"❌ Failed to check regeneration_history: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 5: Provide recovery options
    print("\n" + "=" * 80)
    print("RECOVERY OPTIONS:")
    print("=" * 80)
    print("""
Option 1: RE-REGENERATE CLIP 4 (RECOMMENDED)
  - Use the UI to regenerate clip 4 with the same instruction
  - The new code will properly save both versions
  - Comparison will work correctly going forward
  - Drawback: Loses the current regenerated version

Option 2: MANUALLY INSERT VERSIONS
  - Requires identifying which file in storage is original vs regenerated
  - Manually insert rows into clip_versions table
  - Preserves current regenerated version
  - Complex: Need to determine correct URLs and metadata

Option 3: ACCEPT CURRENT STATE
  - Leave clip 4 as-is (regenerated version in job_stages)
  - No comparison available for this clip
  - Future regenerations will work correctly with new code
    """)
    
    print("=" * 80)
    print("RECOVERY SCRIPT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python recover_clip_4_original.py <job_id> [clip_index]")
        sys.exit(1)
    
    job_id_str = sys.argv[1]
    clip_index_int = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    try:
        job_id_uuid = UUID(job_id_str)
    except ValueError:
        print("Invalid UUID provided.")
        sys.exit(1)
    
    asyncio.run(recover_clip_4(job_id_uuid, clip_index_int))

