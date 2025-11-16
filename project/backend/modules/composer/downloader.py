"""
File download logic for composer module.

Downloads clips and audio from Supabase Storage in parallel.
"""
import asyncio
from typing import List
from uuid import UUID

from shared.storage import StorageClient
from modules.video_generator.image_handler import parse_supabase_url
from shared.errors import RetryableError, CompositionError
from shared.logging import get_logger
from shared.models.video import Clip

logger = get_logger("composer.downloader")


async def download_all_clips(clips: List[Clip], job_id: UUID) -> List[bytes]:
    """
    Download all clips in parallel from Supabase Storage.
    
    Args:
        clips: List of Clip objects (already sorted by clip_index)
        job_id: Job ID for logging
        
    Returns:
        List of clip file bytes (in order)
        
    Raises:
        RetryableError: If download fails
    """
    storage = StorageClient()
    
    async def download_clip(clip: Clip) -> bytes:
        """Download single clip."""
        try:
            bucket, path = parse_supabase_url(clip.video_url)
            logger.info(
                f"Downloading clip {clip.clip_index} from {bucket}/{path}",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index}
            )
            clip_bytes = await storage.download_file(bucket, path)
            
            # Validate file size
            if len(clip_bytes) < 1024:  # Less than 1KB is suspicious
                raise CompositionError(f"Clip {clip.clip_index} file too small: {len(clip_bytes)} bytes")
            if len(clip_bytes) > 200 * 1024 * 1024:  # Warn if >200MB
                logger.warning(
                    f"Clip {clip.clip_index} is large: {len(clip_bytes) / 1024 / 1024:.2f} MB",
                    extra={"job_id": str(job_id), "clip_index": clip.clip_index}
                )
            
            return clip_bytes
        except Exception as e:
            logger.error(
                f"Failed to download clip {clip.clip_index}: {e}",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index, "error": str(e)}
            )
            raise RetryableError(f"Failed to download clip {clip.clip_index}: {e}") from e
    
    # Download all clips in parallel
    tasks = [download_clip(clip) for clip in clips]
    clip_bytes_list = await asyncio.gather(*tasks)
    
    logger.info(
        f"Downloaded {len(clip_bytes_list)} clips",
        extra={"job_id": str(job_id), "count": len(clip_bytes_list)}
    )
    
    return clip_bytes_list


async def download_audio(audio_url: str, job_id: UUID) -> bytes:
    """
    Download audio file from Supabase Storage.
    
    Args:
        audio_url: Audio file URL
        job_id: Job ID for logging
        
    Returns:
        Audio file bytes
        
    Raises:
        RetryableError: If download fails
    """
    storage = StorageClient()
    
    try:
        bucket, path = parse_supabase_url(audio_url)
        logger.info(
            f"Downloading audio from {bucket}/{path}",
            extra={"job_id": str(job_id)}
        )
        audio_bytes = await storage.download_file(bucket, path)
        
        # Validate file size
        if len(audio_bytes) < 1024:  # Less than 1KB is suspicious
            raise CompositionError(f"Audio file too small: {len(audio_bytes)} bytes")
        
        return audio_bytes
    except Exception as e:
        logger.error(
            f"Failed to download audio: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        raise RetryableError(f"Failed to download audio: {e}") from e

