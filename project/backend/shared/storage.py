"""
Storage utilities.

Supabase Storage operations for file upload/download.
"""

import asyncio
import mimetypes
from typing import Optional, Dict, Any, Callable
from supabase import create_client
from shared.config import settings
from shared.errors import RetryableError, ConfigError
from shared.retry import retry_with_backoff
from shared.logging import get_logger

logger = get_logger("storage")

# Default file size limits per bucket (in bytes)
DEFAULT_BUCKET_LIMITS: Dict[str, int] = {
    "audio-uploads": 10 * 1024 * 1024,  # 10MB
    "reference-images": 5 * 1024 * 1024,  # 5MB
    "video-clips": 50 * 1024 * 1024,  # 50MB
    "video-outputs": 100 * 1024 * 1024,  # 100MB
}


class StorageClient:
    """Supabase Storage client for file operations."""
    
    def __init__(self, bucket_limits: Optional[Dict[str, int]] = None):
        """
        Initialize storage client.
        
        Args:
            bucket_limits: Optional dict of bucket name to max file size in bytes
        """
        try:
            self.client = create_client(
                settings.supabase_url,
                settings.supabase_service_key
            )
            self.storage = self.client.storage
            self.bucket_limits = bucket_limits or DEFAULT_BUCKET_LIMITS.copy()
        except Exception as e:
            raise ConfigError(f"Failed to initialize storage client: {str(e)}") from e
    
    async def _execute_sync(self, func: Callable[[], Any]) -> Any:
        """
        Execute a synchronous Supabase storage operation in an async context.
        
        Args:
            func: Synchronous function to execute
            
        Returns:
            Function result
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)
    
    def _detect_content_type(self, path: str, default: Optional[str] = None) -> str:
        """
        Detect content type from file path.
        
        Args:
            path: File path
            default: Default content type if detection fails
            
        Returns:
            Content type string
        """
        content_type, _ = mimetypes.guess_type(path)
        if content_type:
            return content_type
        return default or "application/octet-stream"
    
    @retry_with_backoff(max_attempts=3, base_delay=2)
    async def upload_file(
        self,
        bucket: str,
        path: str,
        file_data: bytes,
        content_type: Optional[str] = None,
        max_size: Optional[int] = None
    ) -> str:
        """
        Upload a file to Supabase Storage.
        
        Args:
            bucket: Storage bucket name
            path: File path in bucket
            file_data: File data as bytes
            content_type: Content type (auto-detected if not provided)
            max_size: Maximum file size in bytes (uses bucket default if not provided)
            
        Returns:
            Public URL of uploaded file
            
        Raises:
            RetryableError: If upload fails after retries
            ValidationError: If file size exceeds limit
        """
        from shared.errors import ValidationError
        
        try:
            # Detect content type if not provided
            if not content_type:
                content_type = self._detect_content_type(path)
            
            # Validate file size
            max_size = max_size or self.bucket_limits.get(bucket, 10 * 1024 * 1024)
            if len(file_data) > max_size:
                max_size_mb = max_size / (1024 * 1024)
                file_size_mb = len(file_data) / (1024 * 1024)
                raise ValidationError(
                    f"File size ({file_size_mb:.2f} MB) exceeds maximum of {max_size_mb:.2f} MB for bucket {bucket}"
                )
            
            # Upload file (wrap sync operation in executor)
            def _upload():
                return self.storage.from_(bucket).upload(
                    path=path,
                    file=file_data,
                    file_options={"content-type": content_type}
                )
            
            response = await self._execute_sync(_upload)
            
            # Get URL - use signed URL for private buckets, public URL for public buckets
            # For now, all buckets are private, so use signed URL
            def _get_url():
                # Try to get signed URL (works for both public and private buckets)
                signed_url_response = self.storage.from_(bucket).create_signed_url(
                    path=path,
                    expires_in=31536000  # 1 year expiration for uploaded files
                )
                # Return signed URL if available
                if isinstance(signed_url_response, dict):
                    return signed_url_response.get("signedURL") or signed_url_response.get("signedUrl") or ""
                return str(signed_url_response) if signed_url_response else ""
            
            file_url = await self._execute_sync(_get_url)
            
            # Fallback to public URL if signed URL fails (for public buckets)
            if not file_url:
                def _get_public_url():
                    return self.storage.from_(bucket).get_public_url(path)
                file_url = await self._execute_sync(_get_public_url)
            
            logger.info(
                f"Uploaded file to {bucket}/{path}",
                extra={"bucket": bucket, "path": path, "size": len(file_data)}
            )
            
            return file_url
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to upload file to {bucket}/{path}: {str(e)}",
                extra={"bucket": bucket, "path": path, "error": str(e)}
            )
            raise RetryableError(f"Failed to upload file: {str(e)}") from e
    
    @retry_with_backoff(max_attempts=3, base_delay=2)
    async def download_file(self, bucket: str, path: str) -> bytes:
        """
        Download a file from Supabase Storage.
        
        Args:
            bucket: Storage bucket name
            path: File path in bucket
            
        Returns:
            File data as bytes
            
        Raises:
            RetryableError: If download fails after retries
        """
        try:
            def _download():
                return self.storage.from_(bucket).download(path)
            
            response = await self._execute_sync(_download)
            
            logger.info(
                f"Downloaded file from {bucket}/{path}",
                extra={"bucket": bucket, "path": path}
            )
            
            return response
            
        except ConnectionError as e:
            logger.error(
                f"Connection error downloading file from {bucket}/{path}: {str(e)}",
                extra={"bucket": bucket, "path": path, "error_type": "ConnectionError"}
            )
            raise RetryableError(
                f"Connection error: Could not connect to Supabase Storage. "
                f"Please check your network connection and Supabase configuration."
            ) from e
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(
                f"Failed to download file from {bucket}/{path}: {error_msg}",
                extra={"bucket": bucket, "path": path, "error": error_msg, "error_type": error_type},
                exc_info=True
            )
            # Check if it's a connection-related error
            if "connection" in error_msg.lower() or "connect" in error_msg.lower():
                raise RetryableError(
                    f"Connection error downloading file: {error_msg}. "
                    f"Please check your network connection and Supabase Storage configuration."
                ) from e
            raise RetryableError(f"Failed to download file: {error_msg}") from e
    
    async def get_signed_url(
        self,
        bucket: str,
        path: str,
        expires_in: int = 3600
    ) -> str:
        """
        Generate a signed URL for a file.
        
        Args:
            bucket: Storage bucket name
            path: File path in bucket
            expires_in: Expiration time in seconds (default: 3600)
            
        Returns:
            Signed URL
            
        Raises:
            RetryableError: If URL generation fails
        """
        try:
            def _create_signed_url():
                return self.storage.from_(bucket).create_signed_url(
                    path=path,
                    expires_in=expires_in
                )
            
            response = await self._execute_sync(_create_signed_url)
            
            logger.info(
                f"Generated signed URL for {bucket}/{path}",
                extra={"bucket": bucket, "path": path, "expires_in": expires_in}
            )
            
            return response.get("signedURL") or response.get("signedUrl") or ""
            
        except Exception as e:
            logger.error(
                f"Failed to generate signed URL for {bucket}/{path}: {str(e)}",
                extra={"bucket": bucket, "path": path, "error": str(e)}
            )
            raise RetryableError(f"Failed to generate signed URL: {str(e)}") from e
    
    @retry_with_backoff(max_attempts=3, base_delay=2)
    async def delete_file(self, bucket: str, path: str) -> bool:
        """
        Delete a file from Supabase Storage.
        
        Args:
            bucket: Storage bucket name
            path: File path in bucket
            
        Returns:
            True if file was deleted, False otherwise
            
        Raises:
            RetryableError: If deletion fails after retries
        """
        try:
            def _delete():
                return self.storage.from_(bucket).remove([path])
            
            await self._execute_sync(_delete)
            
            logger.info(
                f"Deleted file from {bucket}/{path}",
                extra={"bucket": bucket, "path": path}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to delete file from {bucket}/{path}: {str(e)}",
                extra={"bucket": bucket, "path": path, "error": str(e)}
            )
            raise RetryableError(f"Failed to delete file: {str(e)}") from e


# Singleton instance
storage = StorageClient()
