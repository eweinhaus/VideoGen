#!/usr/bin/env python3
"""
Direct test script for video generator.

Allows testing video generation with a prompt and image without the full UI.

Usage:
    python test_video_generator_direct.py \
        --prompt "A beautiful sunset over mountains" \
        --image-url "https://example.com/image.jpg" \
        --duration 5.0 \
        --environment development

Or with a local image:
    python test_video_generator_direct.py \
        --prompt "A beautiful sunset over mountains" \
        --image-path "./test_image.jpg" \
        --duration 5.0 \
        --environment development
"""
import asyncio
import argparse
import sys
import os
from uuid import uuid4, UUID
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Ensure Replicate API token is set
if not os.getenv("REPLICATE_API_TOKEN"):
    print("ERROR: REPLICATE_API_TOKEN not found in environment. Please set it in .env file.")
    sys.exit(1)

# Set Replicate API token explicitly (replicate library reads from env, but ensure it's set)
os.environ.setdefault("REPLICATE_API_TOKEN", os.getenv("REPLICATE_API_TOKEN"))

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.models.video import ClipPrompt, ClipPrompts
from modules.video_generator.process import process
from modules.video_generator.image_handler import download_and_upload_image
from shared.logging import get_logger

logger = get_logger("test_video_generator")


async def test_single_clip(
    prompt: str,
    image_url: str = None,
    image_path: str = None,
    duration: float = 5.0,
    negative_prompt: str = "blurry, low quality, distorted, watermark, text overlay",
    environment: str = "development",
    job_id: UUID = None
):
    """
    Test video generation with a single clip.
    
    Args:
        prompt: Text prompt for video generation
        image_url: URL to reference image (Supabase Storage URL or public URL)
        image_path: Local path to image file (will be uploaded to Replicate)
        duration: Target duration in seconds (default: 5.0)
        negative_prompt: Negative prompt (default: standard negative prompt)
        environment: "development" or "production" (default: "development")
        job_id: Optional job ID (generates new UUID if not provided)
    """
    if job_id is None:
        job_id = uuid4()
    
    logger.info(f"Starting video generation test (job_id: {job_id})")
    logger.info(f"Prompt: {prompt}")
    logger.info(f"Duration: {duration}s")
    logger.info(f"Environment: {environment}")
    
    # Handle image
    scene_reference_url = None
    if image_path:
        logger.info(f"Uploading local image: {image_path}")
        # For local images, we need to upload to Supabase first or directly to Replicate
        # For simplicity, we'll use the image_handler which expects a Supabase URL
        # In a real test, you'd upload to Supabase first, but for quick testing,
        # we can pass the local path and let the handler deal with it
        # Actually, let's check if it's a URL or path
        if image_path.startswith("http://") or image_path.startswith("https://"):
            scene_reference_url = image_path
        else:
            # Local file - we'll need to handle this differently
            # For now, let's just use the URL if provided, or skip image
            logger.warning("Local image path provided but not yet supported. Use --image-url with a public URL or Supabase Storage URL.")
            scene_reference_url = None
    elif image_url:
        scene_reference_url = image_url
    
    # Create ClipPrompt
    clip_prompt = ClipPrompt(
        clip_index=0,
        prompt=prompt,
        negative_prompt=negative_prompt,
        duration=duration,
        scene_reference_url=scene_reference_url,
        character_reference_urls=[],
        metadata={}
    )
    
    # Create ClipPrompts
    clip_prompts = ClipPrompts(
        job_id=job_id,
        clip_prompts=[clip_prompt],
        total_clips=1,
        generation_time=0.0
    )
    
    try:
        # Call video generator process
        logger.info("Calling video generator process...")
        result = await process(
            job_id=job_id,
            clip_prompts=clip_prompts
        )
        
        # Print results
        print("\n" + "="*60)
        print("VIDEO GENERATION RESULTS")
        print("="*60)
        print(f"Job ID: {job_id}")
        print(f"Total Clips: {result.total_clips}")
        print(f"Successful: {result.successful_clips}")
        print(f"Failed: {result.failed_clips}")
        print(f"Total Cost: ${result.total_cost}")
        print(f"Generation Time: {result.total_generation_time:.2f}s")
        print("\nClips:")
        for clip in result.clips:
            print(f"  Clip {clip.clip_index}:")
            print(f"    Video URL: {clip.video_url}")
            print(f"    Duration: {clip.actual_duration:.2f}s (target: {clip.target_duration:.2f}s)")
            print(f"    Duration Diff: {clip.duration_diff:.2f}s")
            print(f"    Cost: ${clip.cost}")
            print(f"    Generation Time: {clip.generation_time:.2f}s")
            print(f"    Status: {clip.status}")
        
        print("\n" + "="*60)
        print("SUCCESS!")
        print("="*60)
        
        return result
        
    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        raise


async def test_multiple_clips(
    prompts: list,
    image_urls: list = None,
    durations: list = None,
    environment: str = "development",
    job_id: UUID = None
):
    """
    Test video generation with multiple clips.
    
    Args:
        prompts: List of text prompts (one per clip)
        image_urls: Optional list of image URLs (one per clip, or None)
        durations: Optional list of durations (one per clip, or all use first duration)
        environment: "development" or "production"
        job_id: Optional job ID
    """
    if job_id is None:
        job_id = uuid4()
    
    if durations is None:
        durations = [5.0] * len(prompts)
    elif len(durations) == 1:
        durations = durations * len(prompts)
    
    if image_urls is None:
        image_urls = [None] * len(prompts)
    elif len(image_urls) == 1:
        image_urls = image_urls * len(prompts)
    
    # Create clip prompts
    clip_prompts_list = []
    for i, (prompt, image_url, duration) in enumerate(zip(prompts, image_urls, durations)):
        clip_prompt = ClipPrompt(
            clip_index=i,
            prompt=prompt,
            negative_prompt="blurry, low quality, distorted, watermark, text overlay",
            duration=duration,
            scene_reference_url=image_url,
            character_reference_urls=[],
            metadata={}
        )
        clip_prompts_list.append(clip_prompt)
    
    clip_prompts = ClipPrompts(
        job_id=job_id,
        clip_prompts=clip_prompts_list,
        total_clips=len(clip_prompts_list),
        generation_time=0.0
    )
    
    try:
        logger.info(f"Generating {len(clip_prompts_list)} clips in parallel...")
        result = await process(
            job_id=job_id,
            clip_prompts=clip_prompts
        )
        
        print("\n" + "="*60)
        print("VIDEO GENERATION RESULTS")
        print("="*60)
        print(f"Job ID: {job_id}")
        print(f"Total Clips: {result.total_clips}")
        print(f"Successful: {result.successful_clips}")
        print(f"Failed: {result.failed_clips}")
        print(f"Total Cost: ${result.total_cost}")
        print(f"Total Generation Time: {result.total_generation_time:.2f}s")
        print("\nClips:")
        for clip in result.clips:
            print(f"  Clip {clip.clip_index}:")
            print(f"    Video URL: {clip.video_url}")
            print(f"    Duration: {clip.actual_duration:.2f}s (target: {clip.target_duration:.2f}s)")
            print(f"    Cost: ${clip.cost}")
            print(f"    Status: {clip.status}")
        
        return result
        
    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Test video generator directly with prompt and image",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single clip with image URL
  python test_video_generator_direct.py \\
      --prompt "A beautiful sunset" \\
      --image-url "https://example.com/image.jpg" \\
      --duration 5.0

  # Single clip without image (text-only)
  python test_video_generator_direct.py \\
      --prompt "A beautiful sunset" \\
      --duration 5.0

  # Multiple clips
  python test_video_generator_direct.py \\
      --prompts "Sunset scene" "Mountain view" "Ocean waves" \\
      --durations 5.0 6.0 4.0 \\
      --environment development
        """
    )
    
    # Single clip options
    parser.add_argument("--prompt", type=str, help="Text prompt for video generation")
    parser.add_argument("--image-url", type=str, help="URL to reference image (Supabase Storage or public URL)")
    parser.add_argument("--image-path", type=str, help="Local path to image file (not yet fully supported)")
    parser.add_argument("--duration", type=float, default=5.0, help="Target duration in seconds (default: 5.0)")
    parser.add_argument("--negative-prompt", type=str, 
                       default="blurry, low quality, distorted, watermark, text overlay",
                       help="Negative prompt")
    
    # Multiple clips options
    parser.add_argument("--prompts", nargs="+", help="Multiple prompts (one per clip)")
    parser.add_argument("--image-urls", nargs="+", help="Multiple image URLs (one per clip)")
    parser.add_argument("--durations", nargs="+", type=float, help="Multiple durations (one per clip)")
    
    # General options
    parser.add_argument("--environment", type=str, default="development",
                          choices=["development", "production", "staging"],
                          help="Environment (default: development)")
    parser.add_argument("--job-id", type=str, help="Optional job ID (UUID)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.prompts:
        # Multiple clips mode
        if args.prompt:
            print("ERROR: Cannot use both --prompt and --prompts")
            sys.exit(1)
        
        job_id = UUID(args.job_id) if args.job_id else None
        asyncio.run(test_multiple_clips(
            prompts=args.prompts,
            image_urls=args.image_urls,
            durations=args.durations,
            environment=args.environment,
            job_id=job_id
        ))
    elif args.prompt:
        # Single clip mode
        job_id = UUID(args.job_id) if args.job_id else None
        asyncio.run(test_single_clip(
            prompt=args.prompt,
            image_url=args.image_url,
            image_path=args.image_path,
            duration=args.duration,
            negative_prompt=args.negative_prompt,
            environment=args.environment,
            job_id=job_id
        ))
    else:
        parser.print_help()
        print("\nERROR: Must provide either --prompt or --prompts")
        sys.exit(1)


if __name__ == "__main__":
    main()

