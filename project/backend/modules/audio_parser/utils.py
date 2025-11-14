"""
Audio file utilities.

Download, hash, and validate audio files.
"""

import hashlib
import io
from typing import Optional

import librosa
from shared.errors import ValidationError, RetryableError
from shared.logging import get_logger
from shared.storage import storage

logger = get_logger("audio_parser")


def calculate_file_hash(audio_bytes: bytes) -> str:
    """
    Calculate MD5 hash of audio file bytes.
    
    Args:
        audio_bytes: Audio file bytes
        
    Returns:
        MD5 hash as hex string
    """
    return hashlib.md5(audio_bytes).hexdigest()


async def download_audio_file(audio_url: str) -> bytes:
    """
    Download audio file from Supabase Storage.
    
    Args:
        audio_url: URL or path to audio file in storage
        
    Returns:
        Audio file bytes
        
    Raises:
        RetryableError: If download fails
    """
    try:
        # Extract bucket and path from URL
        # audio_url format: https://{project}.supabase.co/storage/v1/object/public/{bucket}/{path}
        # or just the path if it's a relative path
        if audio_url.startswith("http"):
            # Extract path from full URL
            parts = audio_url.split("/storage/v1/object/public/")
            if len(parts) == 2:
                bucket_and_path = parts[1]
                bucket, path = bucket_and_path.split("/", 1)
            else:
                raise ValidationError(f"Invalid audio URL format: {audio_url}")
        else:
            # Assume it's a path, extract bucket from path
            # Path format: {user_id}/{job_id}/{filename}
            # Bucket is "audio-uploads"
            bucket = "audio-uploads"
            path = audio_url
        
        logger.info(f"Downloading audio file from {bucket}/{path}")
        audio_bytes = await storage.download_file(bucket=bucket, path=path)
        
        if not audio_bytes:
            raise RetryableError(f"Downloaded audio file is empty: {audio_url}")
        
        logger.info(f"Downloaded audio file: {len(audio_bytes)} bytes")
        return audio_bytes
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to download audio file: {str(e)}", extra={"audio_url": audio_url})
        raise RetryableError(f"Failed to download audio file: {str(e)}") from e


def validate_audio_file(audio_bytes: bytes, max_size_mb: int = 10) -> bool:
    """
    Validate audio file format and size.
    
    Args:
        audio_bytes: Audio file bytes
        max_size_mb: Maximum file size in MB (default: 10)
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If file is invalid
    """
    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if len(audio_bytes) > max_size_bytes:
        file_size_mb = len(audio_bytes) / (1024 * 1024)
        raise ValidationError(
            f"Audio file size ({file_size_mb:.2f} MB) exceeds maximum of {max_size_mb} MB"
        )
    
    # Validate format by trying to load with librosa
    try:
        audio_file = io.BytesIO(audio_bytes)
        y, sr = librosa.load(audio_file, sr=None, duration=1.0)  # Load only first second for validation
        if sr is None or len(y) == 0:
            raise ValidationError("Invalid audio file: unable to load audio data")
        
        logger.info(f"Validated audio file: sample_rate={sr} Hz, duration_sample={len(y)}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate audio file: {str(e)}")
        raise ValidationError(f"Invalid audio file format: {str(e)}") from e

