"""
Unit tests for video_generator.image_handler module.
"""
import pytest
import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from modules.video_generator.image_handler import (
    parse_supabase_url,
    download_and_upload_image
)
from shared.errors import RetryableError


class TestParseSupabaseUrl:
    """Tests for parse_supabase_url() function."""
    
    def test_public_url_format(self):
        """Test parsing public URL format."""
        url = "https://project.supabase.co/storage/v1/object/public/bucket/path/to/image.jpg"
        bucket, path = parse_supabase_url(url)
        assert bucket == "bucket"
        assert path == "path/to/image.jpg"
    
    def test_signed_url_format(self):
        """Test parsing signed URL format."""
        url = "https://project.supabase.co/storage/v1/object/sign/bucket/path/to/image.jpg?token=abc123"
        bucket, path = parse_supabase_url(url)
        assert bucket == "bucket"
        assert path == "path/to/image.jpg"  # Query params should be stripped
    
    def test_url_with_query_parameters(self):
        """Test URL with query parameters are stripped."""
        url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg?token=xyz&expires=123"
        bucket, path = parse_supabase_url(url)
        assert bucket == "bucket"
        assert path == "image.jpg"
    
    def test_nested_paths(self):
        """Test URL with nested paths."""
        url = "https://project.supabase.co/storage/v1/object/public/bucket/folder1/folder2/deep/nested/image.png"
        bucket, path = parse_supabase_url(url)
        assert bucket == "bucket"
        assert path == "folder1/folder2/deep/nested/image.png"
    
    def test_invalid_url_format_raises_error(self):
        """Test invalid URL format raises ValueError."""
        url = "https://invalid-url.com/file.jpg"
        with pytest.raises(ValueError, match="Invalid Supabase Storage URL format"):
            parse_supabase_url(url)
    
    def test_missing_storage_path_raises_error(self):
        """Test URL missing storage path raises error."""
        url = "https://project.supabase.co/some/other/path"
        with pytest.raises(ValueError):
            parse_supabase_url(url)


class TestDownloadAndUploadImage:
    """Tests for download_and_upload_image() function."""
    
    @pytest.mark.asyncio
    async def test_successful_download_and_signed_url(self):
        """Test successful download and signed URL generation."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        test_bytes = b"fake image data"
        signed_url = "https://project.supabase.co/storage/v1/object/sign/bucket/image.jpg?token=signed"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(return_value=test_bytes)
            mock_storage.get_signed_url = AsyncMock(return_value=signed_url)
            mock_storage_class.return_value = mock_storage
            
            result = await download_and_upload_image(image_url, job_id)
            
            assert result == signed_url
            assert isinstance(result, str)
            mock_storage.download_file.assert_called_once_with("bucket", "image.jpg")
            mock_storage.get_signed_url.assert_called_once_with("bucket", "image.jpg", expires_in=3600)
    
    @pytest.mark.asyncio
    async def test_signed_url_failure_fallback_to_file_object(self):
        """Test fallback to file object when signed URL generation fails."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        test_bytes = b"fake image data"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(return_value=test_bytes)
            mock_storage.get_signed_url = AsyncMock(side_effect=Exception("Signed URL failed"))
            mock_storage_class.return_value = mock_storage
            
            result = await download_and_upload_image(image_url, job_id)
            
            assert isinstance(result, io.BytesIO)
            assert result.read() == test_bytes
            assert result.name == "image.jpg"
            mock_storage.download_file.assert_called_once()
            mock_storage.get_signed_url.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self):
        """Test that download failure returns None after retries."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            # Simulate retryable error that eventually fails
            mock_storage.download_file = AsyncMock(side_effect=RetryableError("Download failed"))
            mock_storage_class.return_value = mock_storage
            
            # The retry decorator will retry 3 times, then raise
            # We need to catch the final exception
            with pytest.raises(RetryableError):
                await download_and_upload_image(image_url, job_id)
    
    @pytest.mark.asyncio
    async def test_non_retryable_error_returns_none(self):
        """Test non-retryable error returns None."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            # Non-retryable error (not RetryableError)
            mock_storage.download_file = AsyncMock(side_effect=ValueError("Invalid input"))
            mock_storage_class.return_value = mock_storage
            
            result = await download_and_upload_image(image_url, job_id)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_retryable_error_is_re_raised(self):
        """Test that RetryableError is re-raised for decorator to handle."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(side_effect=RetryableError("Network error"))
            mock_storage_class.return_value = mock_storage
            
            # RetryableError should be re-raised (decorator handles retry)
            with pytest.raises(RetryableError):
                await download_and_upload_image(image_url, job_id)
    
    @pytest.mark.asyncio
    async def test_file_object_has_name_attribute(self):
        """Test that returned file object has name attribute set."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        test_bytes = b"fake image data"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(return_value=test_bytes)
            mock_storage.get_signed_url = AsyncMock(side_effect=Exception("Failed"))
            mock_storage_class.return_value = mock_storage
            
            result = await download_and_upload_image(image_url, job_id)
            
            assert isinstance(result, io.BytesIO)
            assert hasattr(result, "name")
            assert result.name == "image.jpg"
    
    @pytest.mark.asyncio
    async def test_logging_includes_job_id(self):
        """Test that logging includes job_id in extra context."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        image_url = "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg"
        test_bytes = b"fake image data"
        signed_url = "https://project.supabase.co/storage/v1/object/sign/bucket/image.jpg?token=signed"
        
        with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class, \
             patch("modules.video_generator.image_handler.logger") as mock_logger:
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(return_value=test_bytes)
            mock_storage.get_signed_url = AsyncMock(return_value=signed_url)
            mock_storage_class.return_value = mock_storage
            
            await download_and_upload_image(image_url, job_id)
            
            # Verify logger was called with job_id in extra
            assert mock_logger.info.called
            # Check that at least one call has job_id in extra
            calls_with_job_id = [
                call for call in mock_logger.info.call_args_list
                if call.kwargs.get("extra", {}).get("job_id") == str(job_id)
            ]
            assert len(calls_with_job_id) > 0
    
    @pytest.mark.asyncio
    async def test_various_supabase_url_formats(self):
        """Test function works with various Supabase URL formats."""
        job_id = UUID("12345678-1234-1234-1234-123456789012")
        test_bytes = b"fake image data"
        signed_url = "https://project.supabase.co/storage/v1/object/sign/bucket/image.jpg?token=signed"
        
        test_urls = [
            "https://project.supabase.co/storage/v1/object/public/bucket/image.jpg",
            "https://project.supabase.co/storage/v1/object/sign/bucket/image.jpg?token=abc",
            "https://project.supabase.co/storage/v1/object/public/bucket/folder/image.png",
        ]
        
        for url in test_urls:
            with patch("modules.video_generator.image_handler.StorageClient") as mock_storage_class:
                mock_storage = AsyncMock()
                mock_storage.download_file = AsyncMock(return_value=test_bytes)
                mock_storage.get_signed_url = AsyncMock(return_value=signed_url)
                mock_storage_class.return_value = mock_storage
                
                result = await download_and_upload_image(url, job_id)
                assert result is not None

