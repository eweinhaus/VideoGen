"""
Download endpoint.

Generate signed URLs for video downloads.
"""

from fastapi import APIRouter, Path, Depends, HTTPException, status
from shared.storage import StorageClient
from shared.logging import get_logger
from api_gateway.dependencies import get_current_user, verify_job_ownership

logger = get_logger(__name__)

router = APIRouter()
storage_client = StorageClient()


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
        # Generate signed URL (1 hour expiration)
        # Extract path from video_url if it's a full URL
        # Assuming video_url is stored as path in format: video-outputs/{job_id}/final_video.mp4
        signed_url = await storage_client.get_signed_url(
            bucket="video-outputs",
            path=f"{job_id}/final_video.mp4",
            expires_in=3600  # 1 hour
        )
        
        logger.info("Signed URL generated", extra={"job_id": job_id})
        
        return {
            "download_url": signed_url,
            "expires_in": 3600,
            "filename": f"music_video_{job_id}.mp4"
        }
        
    except Exception as e:
        logger.error("Failed to generate signed URL", exc_info=e, extra={"job_id": job_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL"
        )

