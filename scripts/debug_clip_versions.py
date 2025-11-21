"""
Debug script to check clip_versions table for specific job and clips.

Usage:
  python scripts/debug_clip_versions.py <job_id> [clip_indices...]
  
Example:
  python scripts/debug_clip_versions.py abc-123-def 2 5
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "project" / "backend"
sys.path.insert(0, str(backend_path))

from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)


async def debug_clip_versions(job_id: str, clip_indices: list[int] = None):
    """
    Check clip_versions table for a job and specific clips.
    
    Args:
        job_id: Job ID to check
        clip_indices: Optional list of specific clip indices to check
    """
    db = DatabaseClient()
    
    print(f"\n{'='*80}")
    print(f"DEBUGGING CLIP VERSIONS FOR JOB: {job_id}")
    print(f"{'='*80}\n")
    
    try:
        # First, check if clip_versions table exists
        try:
            test_query = await db.table("clip_versions").select("*").limit(1).execute()
            print("✅ clip_versions table exists\n")
        except Exception as e:
            print(f"❌ clip_versions table doesn't exist or is inaccessible: {e}\n")
            return
        
        # Check job_stages for original clips
        print(f"📊 CHECKING JOB_STAGES (ORIGINAL CLIPS):")
        print(f"{'-'*80}")
        
        try:
            result = await db.table("job_stages").select("metadata").eq(
                "job_id", job_id
            ).eq("stage_name", "video_generator").execute()
            
            if result.data and len(result.data) > 0:
                import json
                metadata = result.data[0].get("metadata")
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                clips = metadata.get("clips", {})
                if isinstance(clips, dict):
                    clips_array = clips.get("clips", [])
                else:
                    clips_array = clips
                
                print(f"Found {len(clips_array)} clips in job_stages\n")
                
                for clip in clips_array:
                    clip_idx = clip.get("clip_index")
                    video_url = clip.get("video_url", "")
                    # Show only last part of URL for readability
                    url_short = video_url.split("/")[-1] if video_url else "MISSING"
                    
                    if clip_indices is None or clip_idx in clip_indices:
                        print(f"  Clip {clip_idx}: {url_short}")
                print()
            else:
                print("❌ No video_generator stage found in job_stages\n")
        except Exception as e:
            print(f"❌ Error loading job_stages: {e}\n")
        
        # Check clip_versions for regenerated clips
        print(f"🔄 CHECKING CLIP_VERSIONS (REGENERATED CLIPS):")
        print(f"{'-'*80}")
        
        if clip_indices:
            # Check specific clips
            for clip_idx in clip_indices:
                print(f"\nClip {clip_idx}:")
                print(f"  {'-'*40}")
                
                result = await db.table("clip_versions").select("*").eq(
                    "job_id", job_id
                ).eq("clip_index", clip_idx).order("version_number", desc=False).execute()
                
                if result.data and len(result.data) > 0:
                    print(f"  Found {len(result.data)} version(s):")
                    for version_data in result.data:
                        version_num = version_data.get("version_number")
                        video_url = version_data.get("video_url", "")
                        url_short = video_url.split("/")[-1] if video_url else "MISSING"
                        is_current = version_data.get("is_current", False)
                        user_instruction = version_data.get("user_instruction", "")
                        instruction_short = user_instruction[:50] + "..." if len(user_instruction) > 50 else user_instruction
                        
                        current_marker = " [CURRENT]" if is_current else ""
                        print(f"    v{version_num}: {url_short}{current_marker}")
                        if user_instruction:
                            print(f"         Instruction: {instruction_short}")
                else:
                    print(f"  ❌ NO VERSIONS FOUND (Clip was never regenerated)")
        else:
            # Show all clips for this job
            result = await db.table("clip_versions").select("*").eq(
                "job_id", job_id
            ).order("clip_index", desc=False).order("version_number", desc=False).execute()
            
            if result.data and len(result.data) > 0:
                current_clip = None
                for version_data in result.data:
                    clip_idx = version_data.get("clip_index")
                    version_num = version_data.get("version_number")
                    video_url = version_data.get("video_url", "")
                    url_short = video_url.split("/")[-1] if video_url else "MISSING"
                    is_current = version_data.get("is_current", False)
                    
                    if clip_idx != current_clip:
                        if current_clip is not None:
                            print()
                        current_clip = clip_idx
                        print(f"\nClip {clip_idx}:")
                        print(f"  {'-'*40}")
                    
                    current_marker = " [CURRENT]" if is_current else ""
                    print(f"    v{version_num}: {url_short}{current_marker}")
            else:
                print("  ❌ NO VERSIONS FOUND (No clips were ever regenerated)")
        
        print(f"\n{'='*80}")
        print(f"DIAGNOSIS COMPLETE")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_clip_versions.py <job_id> [clip_indices...]")
        print("\nExample:")
        print("  python scripts/debug_clip_versions.py abc-123-def")
        print("  python scripts/debug_clip_versions.py abc-123-def 2 5")
        sys.exit(1)
    
    job_id = sys.argv[1]
    clip_indices = [int(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else None
    
    asyncio.run(debug_clip_versions(job_id, clip_indices))

