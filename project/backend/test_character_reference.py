#!/usr/bin/env python3
"""
Test video generation with character reference image.

Tests the new implementation that uses character reference images with Kling model.
"""
import asyncio
import sys
import os
from uuid import uuid4, UUID
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Ensure Replicate API token is set
if not os.getenv("REPLICATE_API_TOKEN"):
    print("ERROR: REPLICATE_API_TOKEN not found in environment.")
    sys.exit(1)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.models.video import ClipPrompt, ClipPrompts
from modules.video_generator.process import process
from shared.storage import StorageClient
from shared.logging import get_logger

logger = get_logger("test_character_reference")


async def upload_character_reference(image_path: str, job_id: UUID) -> str:
    """Upload character reference image to Supabase Storage."""
    storage = StorageClient()
    
    # Read image file
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    # Upload to Supabase Storage
    bucket = "reference-images"
    path = f"{job_id}/character_reference.png"
    
    logger.info(f"Uploading character reference image to {bucket}/{path}")
    url = await storage.upload_file(
        bucket=bucket,
        path=path,
        file_data=image_bytes,
        content_type="image/png"
    )
    
    logger.info(f"Character reference image uploaded: {url}")
    return url


async def test_character_reference(
    prompt: str,
    character_image_path: str,
    duration: float = 5.0,
    environment: str = "development"
):
    """Test video generation with character reference image."""
    job_id = uuid4()
    
    print("="*70)
    print("TESTING CHARACTER REFERENCE IMAGE WITH KLING MODEL")
    print("="*70)
    print(f"Job ID: {job_id}")
    print(f"Prompt: {prompt[:100]}...")
    print(f"Character Reference: {character_image_path}")
    print(f"Duration: {duration}s")
    print(f"Environment: {environment}")
    print()
    
    try:
        # Upload character reference image
        print("Step 1: Uploading character reference image to Supabase...")
        character_ref_url = await upload_character_reference(character_image_path, job_id)
        print(f"✓ Character reference uploaded: {character_ref_url}")
        print()
        
        # Create ClipPrompt with character reference
        print("Step 2: Creating clip prompt with character reference...")
        clip_prompt = ClipPrompt(
            clip_index=0,
            prompt=prompt,
            negative_prompt="blurry, low quality, distorted, watermark, text overlay",
            duration=duration,
            scene_reference_url=None,  # No scene reference - test character reference only
            character_reference_urls=[character_ref_url],  # Use character reference
            metadata={}
        )
        
        clip_prompts = ClipPrompts(
            job_id=job_id,
            clip_prompts=[clip_prompt],
            total_clips=1,
            generation_time=0.0
        )
        print("✓ Clip prompt created")
        print(f"  - Character reference URLs: {clip_prompt.character_reference_urls}")
        print(f"  - Scene reference URL: {clip_prompt.scene_reference_url}")
        print()
        
        # Generate video
        print("Step 3: Generating video with Kling model...")
        print("  (This may take 1-2 minutes)")
        print()
        
        # Temporarily set minimum clips to 1 for testing
        import os
        original_min = os.environ.get("VIDEO_GENERATOR_MIN_CLIPS", "3")
        os.environ["VIDEO_GENERATOR_MIN_CLIPS"] = "1"
        
        try:
            result = await process(
                job_id=job_id,
                clip_prompts=clip_prompts
            )
        finally:
            # Restore original setting
            if original_min:
                os.environ["VIDEO_GENERATOR_MIN_CLIPS"] = original_min
            else:
                os.environ.pop("VIDEO_GENERATOR_MIN_CLIPS", None)
        
        # Print results
        print()
        print("="*70)
        print("RESULTS")
        print("="*70)
        print(f"Job ID: {job_id}")
        print(f"Total Clips: {result.total_clips}")
        print(f"Successful: {result.successful_clips}")
        print(f"Failed: {result.failed_clips}")
        print(f"Total Cost: ${result.total_cost}")
        print(f"Generation Time: {result.total_generation_time:.2f}s")
        print()
        
        if result.clips:
            clip = result.clips[0]
            print("Generated Clip:")
            print(f"  Video URL: {clip.video_url}")
            print(f"  Duration: {clip.actual_duration:.2f}s (target: {clip.target_duration:.2f}s)")
            print(f"  Duration Diff: {clip.duration_diff:.2f}s")
            print(f"  Cost: ${clip.cost}")
            print(f"  Generation Time: {clip.generation_time:.2f}s")
            print(f"  Status: {clip.status}")
            print()
            print("="*70)
            print("SUCCESS! Video generated with character reference image.")
            print("="*70)
            print()
            print("Check the video to verify:")
            print("  1. Character appearance matches the reference image")
            print("  2. Background/scene comes from the prompt, NOT from the character reference")
            print(f"  3. Video URL: {clip.video_url}")
        else:
            print("ERROR: No clips generated")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print()
        print("="*70)
        print("ERROR")
        print("="*70)
        print(f"Test failed: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    # Read prompt from file
    # VideoGenTest is at the root level, not inside project
    project_root = Path(__file__).parent.parent.parent
    prompt_file = project_root / "VideoGenTest" / "prompt.txt"
    character_image = project_root / "VideoGenTest" / "character_reference.png"
    
    if not prompt_file.exists():
        print(f"ERROR: Prompt file not found: {prompt_file}")
        sys.exit(1)
    
    if not character_image.exists():
        print(f"ERROR: Character reference image not found: {character_image}")
        sys.exit(1)
    
    # Read prompt (first line after "Clip 1" and duration)
    with open(prompt_file, "r") as f:
        lines = f.readlines()
        # Get the full prompt (line 3, which is index 2)
        if len(lines) >= 3:
            prompt = lines[2].strip()
        else:
            print("ERROR: Prompt file format incorrect")
            sys.exit(1)
    
    # Extract duration from line 2 (format: "8.6s")
    duration = 5.0  # Default
    if len(lines) >= 2:
        duration_str = lines[1].strip().replace("s", "")
        try:
            duration = float(duration_str)
        except ValueError:
            pass
    
    # Run test
    success = asyncio.run(test_character_reference(
        prompt=prompt,
        character_image_path=str(character_image),
        duration=duration,
        environment="development"
    ))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

