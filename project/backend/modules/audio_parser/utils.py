"""
Utility functions for audio parser.

Download, validation, and hash calculation utilities.
"""

import hashlib
import io
import re
from typing import Optional
import httpx
from shared.storage import storage
from shared.validation import validate_audio_file, ValidationError
from shared.errors import AudioAnalysisError
from shared.logging import get_logger

logger = get_logger("audio_parser")


async def download_audio_file(audio_url: str) -> bytes:
    """
    Download audio file from Supabase Storage URL.
    
    Args:
        audio_url: Supabase Storage URL (public or signed)
        
    Returns:
        Audio file bytes
        
    Raises:
        AudioAnalysisError: If download fails
    """
    try:
        # Try to extract bucket and path from URL
        # Supabase Storage URLs format:
        # https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
        # or
        # https://<project>.supabase.co/storage/v1/object/sign/<bucket>/<path>?token=...
        
        bucket_path_match = re.search(
            r'/storage/v1/object/(?:public|sign)/([^/]+)/(.+)',
            audio_url
        )
        
        if bucket_path_match:
            # Extract bucket and path from URL
            bucket = bucket_path_match.group(1)
            path = bucket_path_match.group(2)
            
            # Remove query parameters from path if present
            if '?' in path:
                path = path.split('?')[0]
            
            logger.info(f"Downloading from bucket: {bucket}, path: {path}")
            try:
                return await storage.download_file(bucket, path)
            except Exception as storage_error:
                logger.error(
                    f"Storage download failed: {str(storage_error)}",
                    extra={"bucket": bucket, "path": path, "error_type": type(storage_error).__name__}
                )
                # Re-raise with more context
                raise AudioAnalysisError(
                    f"Failed to download audio file from storage (bucket: {bucket}, path: {path}): {str(storage_error)}"
                ) from storage_error
        else:
            # Fallback: Download directly from URL using HTTP
            logger.info(f"Downloading directly from URL: {audio_url}")
            # Use longer timeout for large files (5 minutes)
            timeout = httpx.Timeout(300.0, connect=30.0)
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(audio_url)
                    response.raise_for_status()
                    return response.content
            except httpx.ConnectError as e:
                logger.error(f"Connection error downloading audio file: {str(e)}", extra={"url": audio_url})
                raise AudioAnalysisError(
                    f"Connection error: Could not connect to download audio file. "
                    f"Please check your network connection and the audio file URL."
                ) from e
            except httpx.TimeoutException as e:
                logger.error(f"Timeout downloading audio file: {str(e)}", extra={"url": audio_url})
                raise AudioAnalysisError(
                    f"Download timeout: The audio file download took too long. "
                    f"The file may be too large or the server is slow."
                ) from e
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error downloading audio file: {e.response.status_code} - {str(e)}",
                    extra={"url": audio_url, "status_code": e.response.status_code}
                )
                raise AudioAnalysisError(
                    f"HTTP error {e.response.status_code}: Failed to download audio file. "
                    f"The file may not exist or you may not have permission to access it."
                ) from e
                
    except AudioAnalysisError:
        # Re-raise AudioAnalysisError as-is
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error downloading audio file: {str(e)}",
            extra={"url": audio_url, "error_type": type(e).__name__},
            exc_info=True
        )
        raise AudioAnalysisError(f"Failed to download audio file: {str(e)}") from e


def validate_audio_file_bytes(audio_bytes: bytes, max_size_mb: int = 10) -> None:
    """
    Validate audio file bytes.
    
    Args:
        audio_bytes: Audio file bytes
        max_size_mb: Maximum file size in MB (default: 10)
        
    Raises:
        ValidationError: If file is invalid
    """
    # Convert bytes to BytesIO for validation
    file_obj = io.BytesIO(audio_bytes)
    file_obj.name = "audio_file"  # Set name for MIME type detection
    
    # Use shared validation function
    from shared.validation import validate_audio_file as validate_audio_file_shared
    validate_audio_file_shared(file_obj, max_size_mb=max_size_mb)


def calculate_file_hash(audio_bytes: bytes) -> str:
    """
    Calculate MD5 hash of audio file bytes.
    
    Args:
        audio_bytes: Audio file bytes
        
    Returns:
        MD5 hash as hex string
    """
    return hashlib.md5(audio_bytes).hexdigest()


def extract_hash_from_url(audio_url: str) -> Optional[str]:
    """
    Try to extract MD5 hash from Supabase Storage URL.
    
    Note: Supabase Storage URLs typically don't include file hashes in the URL.
    This function attempts to extract hash if present in URL parameters or path,
    but will return None if hash is not available (which is the common case).
    
    Args:
        audio_url: Supabase Storage URL
        
    Returns:
        MD5 hash if found in URL, None otherwise
    """
    # Check for hash in URL parameters (if Supabase adds it in future)
    if 'hash=' in audio_url:
        match = re.search(r'hash=([a-f0-9]{32})', audio_url)
        if match:
            return match.group(1)
    
    # Check for hash in path (unlikely but possible)
    hash_match = re.search(r'([a-f0-9]{32})', audio_url)
    if hash_match:
        # Only return if it looks like an MD5 hash (32 hex chars)
        potential_hash = hash_match.group(1)
        if len(potential_hash) == 32:
            return potential_hash
    
    # Default: Hash not in URL, will be calculated after download
    return None
