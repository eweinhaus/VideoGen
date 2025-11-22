"""
Download endpoint.

Generate signed URLs for video downloads.
"""

import re
from fastapi import APIRouter, Path, Depends, HTTPException, status
from shared.storage import StorageClient
from shared.logging import get_logger
from api_gateway.dependencies import get_current_user, verify_job_ownership

logger = get_logger(__name__)

router = APIRouter()
storage_client = StorageClient()


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


@router.get("/jobs/{job_id}/download")
async def download_video(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Download final video file via signed URL.
    
    Args:
        job_id: Job ID
        current_user: Current authenticated user
        
    Returns:
        Signed URL with expiration and filename
    """
    # Verify ownership
    job = await verify_job_ownership(job_id, current_user)
    
    # Verify job status is completed
    if job.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not completed or video not available"
        )
    
    video_url = job.get("video_url")
    if not video_url:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Video file no longer available"
        )
    
    try:
        # Extract bucket and path from video_url
        # video_url is stored as a full Supabase URL (signed URL) from composer
        try:
            bucket, path = parse_supabase_url(video_url)
        except ValueError as e:
            logger.error(
                f"Failed to parse video_url: {video_url}",
                exc_info=e,
                extra={"job_id": job_id, "video_url": video_url}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid video URL format"
            )
        
        # Generate signed URL (1 hour expiration)
        signed_url = await storage_client.get_signed_url(
            bucket=bucket,
            path=path,
            expires_in=3600  # 1 hour
        )
        
        # Extract filename from path for download
        filename = path.split("/")[-1] if "/" in path else f"music_video_{job_id}.mp4"
        
        logger.info(
            "Signed URL generated",
            extra={"job_id": job_id, "bucket": bucket, "path": path}
        )
        
        return {
            "download_url": signed_url,
            "expires_in": 3600,
            "filename": filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to generate signed URL",
            exc_info=e,
            extra={"job_id": job_id, "video_url": video_url}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL"
        )

