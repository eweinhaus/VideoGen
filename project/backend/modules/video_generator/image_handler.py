"""
Image handling for video generation.

Downloads images from Supabase Storage and uploads to Replicate.
"""
from typing import Optional, Union
from uuid import UUID
import io
import re
from shared.storage import StorageClient
from shared.retry import retry_with_backoff
from shared.errors import RetryableError
from shared.logging import get_logger

logger = get_logger("video_generator.image_handler")


def parse_supabase_url(url: str) -> tuple[str, str]:
    """
    Parse Supabase Storage URL to extract bucket and path.
    
    Args:
        url: Supabase Storage URL (e.g., "https://project.supabase.co/storage/v1/object/public/bucket/path")
        
    Returns:
        Tuple of (bucket, path)
        
    Raises:
        ValueError: If URL format is invalid
    """
    # Supabase Storage URL format:
    # https://{project}.supabase.co/storage/v1/object/public/{bucket}/{path}
    # or
    # https://{project}.supabase.co/storage/v1/object/sign/{bucket}/{path}?token=...
    
    pattern = r"/storage/v1/object/(?:public|sign)/([^/]+)/(.+)"
    match = re.search(pattern, url)
    
    if not match:
        raise ValueError(
            f"Invalid Supabase Storage URL format: {url}. "
            f"Expected format: https://project.supabase.co/storage/v1/object/public/bucket/path"
        )
    
    bucket = match.group(1)
    path = match.group(2)
    
    # Remove query parameters if present
    if "?" in path:
        path = path.split("?")[0]
    
    return bucket, path


@retry_with_backoff(max_attempts=3, base_delay=2)
async def download_and_upload_image(
    image_url: str,
    job_id: UUID
) -> Optional[Union[str, io.BytesIO]]:
    """
    Download image from Supabase and prepare for Replicate.
    
    Args:
        image_url: Supabase Storage URL
        job_id: Job ID for logging
        
    Returns:
        Signed URL string, file object (io.BytesIO), or None if all attempts fail
        
    Raises:
        RetryableError: If download fails (will retry)
    """
    storage = StorageClient()
    
    try:
        # Parse Supabase URL
        bucket, path = parse_supabase_url(image_url)
        
        # Download from Supabase
        logger.info(
            f"Downloading image from Supabase: {bucket}/{path}",
            extra={"job_id": str(job_id)}
        )
        image_bytes = await storage.download_file(bucket, path)
        
        # Replicate accepts file URLs, file objects, or file paths directly
        # Strategy: Try Supabase signed URL first, fallback to file object
        # Note: Replicate will handle the file automatically when passed in input
        
        # Option 1: Try using Supabase signed URL directly (if Replicate accepts HTTP URLs)
        # This avoids download/upload overhead
        try:
            signed_url = await storage.get_signed_url(bucket, path, expires_in=3600)
            logger.info(
                f"Using Supabase signed URL for Replicate",
                extra={"job_id": str(job_id)}
            )
            return signed_url
        except Exception as e:
            logger.debug(
                f"Signed URL approach failed, using file object: {e}",
                extra={"job_id": str(job_id)}
            )
        
        # Option 2: Pass file bytes as file object (Replicate accepts this in input)
        # Create a temporary file-like object from bytes
        file_obj = io.BytesIO(image_bytes)
        file_obj.name = "image.jpg"  # Replicate may need filename
        
        logger.info(
            f"Prepared file object for Replicate input",
            extra={"job_id": str(job_id), "size": len(image_bytes)}
        )
        
        # Return file object - will be passed directly in Replicate input
        # Note: This returns the file object, not a URL
        # The generator will pass this directly in the input dict
        return file_obj
        
    except RetryableError:
        # Re-raise retryable errors (will be retried by decorator)
        raise
    except Exception as e:
        logger.error(
            f"Failed to download/upload image: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        # Return None to proceed with text-only
        return None

