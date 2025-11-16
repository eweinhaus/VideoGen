#!/usr/bin/env python3
"""
Helper script to upload a local image to Supabase Storage for testing.
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent))

from shared.storage import StorageClient
from shared.logging import get_logger

logger = get_logger("upload_test_image")


async def upload_image(image_path: str, bucket: str = "reference-images") -> str:
    """
    Upload a local image file to Supabase Storage.
    
    Args:
        image_path: Path to local image file
        bucket: Supabase Storage bucket name (default: "reference-images")
        
    Returns:
        Public URL of uploaded image
    """
    image_file = Path(image_path)
    if not image_file.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    # Read image file
    with open(image_file, "rb") as f:
        image_data = f.read()
    
    # Generate a unique path
    test_id = uuid4()
    file_extension = image_file.suffix or ".png"
    storage_path = f"test/{test_id}{file_extension}"
    
    logger.info(f"Uploading {image_path} to {bucket}/{storage_path}")
    
    # Upload to Supabase
    storage = StorageClient()
    url = await storage.upload_file(
        bucket=bucket,
        path=storage_path,
        file_data=image_data,
        content_type=f"image/{file_extension[1:]}"  # Remove the dot
    )
    
    logger.info(f"Uploaded successfully: {url}")
    return url


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload local image to Supabase Storage")
    parser.add_argument("image_path", help="Path to local image file")
    parser.add_argument("--bucket", default="reference-images", help="Supabase Storage bucket (default: reference-images)")
    
    args = parser.parse_args()
    
    try:
        url = asyncio.run(upload_image(args.image_path, args.bucket))
        print(f"\n✅ Image uploaded successfully!")
        print(f"URL: {url}\n")
        print(f"You can use this URL with the test script:")
        print(f'  --image-url "{url}"')
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

