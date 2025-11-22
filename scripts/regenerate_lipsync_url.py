#!/usr/bin/env python3
"""
Regenerate a signed URL for a lipsynced clip.

Usage:
    python scripts/regenerate_lipsync_url.py <job_id> <clip_index>
    
Example:
    python scripts/regenerate_lipsync_url.py 4bffe66f-e014-479d-8cac-793a3c2a70c9 4
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
    load_dotenv()
    print(f"⚠️  .env file not found at {env_file}, trying environment variables")

from shared.storage import StorageClient


async def regenerate_lipsync_url(job_id_str: str, clip_index: int):
    """Regenerate a signed URL for a lipsynced clip."""
    job_id = UUID(job_id_str)
    clip_path = f"{job_id}/clip_{clip_index}_lipsync.mp4"
    
    print("=" * 80)
    print(f"Regenerating Signed URL for Lipsynced Clip")
    print("=" * 80)
    print(f"Job ID: {job_id_str}")
    print(f"Clip Index: {clip_index}")
    print(f"File Path: {clip_path}")
    print()
    
    try:
        storage = StorageClient()
        
        # Check if file exists
        print("Step 1: Checking if file exists...")
        try:
            # Try to get file info by attempting to generate a signed URL
            # If file doesn't exist, this will fail
            test_url = await storage.get_signed_url(
                bucket="video-clips",
                path=clip_path,
                expires_in=3600  # 1 hour for testing
            )
            print(f"✅ File exists")
            print()
        except Exception as e:
            print(f"❌ ERROR: File not found or cannot be accessed")
            print(f"   Path: video-clips/{clip_path}")
            print(f"   Error: {str(e)}")
            return
        
        # Generate new signed URL with 1 year expiration
        print("Step 2: Generating new signed URL...")
        signed_url = await storage.get_signed_url(
            bucket="video-clips",
            path=clip_path,
            expires_in=31536000  # 1 year
        )
        
        print("=" * 80)
        print("✅ SUCCESS! New signed URL generated")
        print("=" * 80)
        print(f"Signed URL: {signed_url}")
        print()
        print("📋 Copy this URL to access the lipsynced clip")
        print()
        
    except Exception as e:
        print("=" * 80)
        print(f"❌ ERROR")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/regenerate_lipsync_url.py <job_id> <clip_index>")
        print()
        print("Example:")
        print("  python scripts/regenerate_lipsync_url.py 4bffe66f-e014-479d-8cac-793a3c2a70c9 4")
        sys.exit(1)
    
    job_id_str = sys.argv[1]
    try:
        clip_index = int(sys.argv[2])
    except ValueError:
        print(f"❌ ERROR: Invalid clip_index '{sys.argv[2]}'. Must be a number.")
        sys.exit(1)
    
    asyncio.run(regenerate_lipsync_url(job_id_str, clip_index))

