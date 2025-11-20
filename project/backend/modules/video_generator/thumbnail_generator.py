"""
Thumbnail generation for video clips.

Generates thumbnails by extracting the first frame from video clips using FFmpeg.
This is an async, non-blocking operation that doesn't interfere with video generation.
"""
import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

from shared.storage import StorageClient
from shared.database import DatabaseClient
from shared.logging import get_logger
from modules.composer.utils import check_ffmpeg_available
from modules.video_generator.image_handler import parse_supabase_url

logger = get_logger("video_generator.thumbnail_generator")


async def generate_clip_thumbnail(
    clip_url: str,
    job_id: UUID,
    clip_index: int
) -> Optional[str]:
    """
    Generate thumbnail for a clip (async, non-blocking).
    
    Uses FFmpeg to extract first frame and resize to 320x180.
    Returns thumbnail URL or None if generation fails.
    
    Args:
        clip_url: URL of the video clip in Supabase Storage
        job_id: Job ID for logging and storage path
        clip_index: Index of the clip (for storage path)
        
    Returns:
        Thumbnail URL if successful, None if generation fails
    """
    try:
        # Check FFmpeg availability (reuse composer check)
        if not check_ffmpeg_available():
            logger.warning(
                "FFmpeg not available, skipping thumbnail generation",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            return None
        
        # Parse clip URL to get bucket and path
        try:
            bucket, path = parse_supabase_url(clip_url)
        except ValueError as e:
            logger.warning(
                f"Failed to parse clip URL: {e}",
                extra={"job_id": str(job_id), "clip_index": clip_index, "clip_url": clip_url}
            )
            return None
        
        # Download clip to temp file
        storage = StorageClient()
        logger.debug(
            f"Downloading clip for thumbnail generation",
            extra={"job_id": str(job_id), "clip_index": clip_index, "bucket": bucket, "path": path}
        )
        
        try:
            clip_bytes = await storage.download_file(bucket, path)
        except Exception as e:
            logger.warning(
                f"Failed to download clip for thumbnail: {e}",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            return None
        
        # Use tempfile context manager for automatic cleanup
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            temp_clip_path = temp_dir_path / f"clip_{clip_index}.mp4"
            temp_clip_path.write_bytes(clip_bytes)
            
            # Extract first frame using FFmpeg
            thumbnail_path = temp_dir_path / f"thumbnail_{clip_index}.jpg"
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", str(temp_clip_path),
                "-vf", "scale=320:180",  # Resize to 320x180 (16:9 aspect ratio)
                "-frames:v", "1",  # Extract only first frame
                "-q:v", "2",  # High quality JPEG (2 = high quality, 31 = low quality)
                "-y",  # Overwrite output file
                str(thumbnail_path)
            ]
            
            logger.debug(
                f"Running FFmpeg to extract thumbnail",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            
            # Run FFmpeg command (use asyncio.create_subprocess_exec for async execution)
            try:
                process = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                    logger.warning(
                        f"FFmpeg thumbnail extraction failed: {error_msg}",
                        extra={"job_id": str(job_id), "clip_index": clip_index, "error": error_msg}
                    )
                    return None
                
                # Verify thumbnail was created
                if not thumbnail_path.exists() or thumbnail_path.stat().st_size == 0:
                    logger.warning(
                        "Thumbnail file not created or empty",
                        extra={"job_id": str(job_id), "clip_index": clip_index}
                    )
                    return None
                
            except asyncio.TimeoutError:
                logger.warning(
                    "FFmpeg thumbnail extraction timed out",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
                return None
            except Exception as e:
                logger.warning(
                    f"FFmpeg thumbnail extraction failed: {e}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
                return None
            
            # Upload thumbnail to Supabase Storage
            thumbnail_bytes = thumbnail_path.read_bytes()
            thumbnail_path_storage = f"{job_id}/clip_{clip_index}_thumbnail.jpg"
            
            logger.debug(
                f"Uploading thumbnail to storage",
                extra={"job_id": str(job_id), "clip_index": clip_index, "size": len(thumbnail_bytes)}
            )
            
            try:
                thumbnail_url = await storage.upload_file(
                    bucket="clip-thumbnails",
                    path=thumbnail_path_storage,
                    file_data=thumbnail_bytes,
                    content_type="image/jpeg",
                    overwrite=True  # Allow overwriting existing thumbnails
                )
            except Exception as e:
                # Check if it's a 409 duplicate error - if so, try to get the existing file URL
                error_str = str(e).lower()
                if "409" in error_str or "duplicate" in error_str or "already exists" in error_str:
                    logger.debug(
                        f"Thumbnail already exists, getting existing URL",
                        extra={"job_id": str(job_id), "clip_index": clip_index}
                    )
                    try:
                        # Try to get the signed URL for the existing file
                        thumbnail_url = await storage.get_signed_url(
                            bucket="clip-thumbnails",
                            path=thumbnail_path_storage,
                            expires_in=31536000  # 1 year
                        )
                        if thumbnail_url:
                            return thumbnail_url
                    except Exception as url_error:
                        logger.warning(
                            f"Failed to get existing thumbnail URL: {url_error}",
                            extra={"job_id": str(job_id), "clip_index": clip_index}
                        )
                
                logger.warning(
                    f"Failed to upload thumbnail: {e}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
                return None
            
            # Store in database (handle duplicate key errors with UPSERT)
            db = DatabaseClient()
            try:
                # Try INSERT first
                await db.table("clip_thumbnails").insert({
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "thumbnail_url": thumbnail_url
                }).execute()
                
                logger.info(
                    f"Thumbnail generated and stored successfully",
                    extra={"job_id": str(job_id), "clip_index": clip_index, "thumbnail_url": thumbnail_url}
                )
                
            except Exception as e:
                # Handle duplicate key (UPDATE instead)
                error_str = str(e).lower()
                if "duplicate" in error_str or "unique" in error_str or "violates unique constraint" in error_str:
                    try:
                        await db.table("clip_thumbnails").update({
                            "thumbnail_url": thumbnail_url
                        }).eq("job_id", str(job_id)).eq("clip_index", clip_index).execute()
                        
                        logger.info(
                            f"Thumbnail updated in database",
                            extra={"job_id": str(job_id), "clip_index": clip_index, "thumbnail_url": thumbnail_url}
                        )
                    except Exception as update_error:
                        logger.warning(
                            f"Failed to update thumbnail in database: {update_error}",
                            extra={"job_id": str(job_id), "clip_index": clip_index}
                        )
                        return None
                else:
                    logger.warning(
                        f"Failed to store thumbnail in database: {e}",
                        extra={"job_id": str(job_id), "clip_index": clip_index}
                    )
                    return None
            
            return thumbnail_url
            
    except Exception as e:
        logger.warning(
            f"Thumbnail generation failed: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index},
            exc_info=True
        )
        return None  # Non-blocking failure

