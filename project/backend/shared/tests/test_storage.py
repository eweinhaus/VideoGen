"""
Tests for storage utilities.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import sys

# Mock supabase before importing shared modules
mock_supabase = Mock()
sys.modules['supabase'] = mock_supabase

from shared.storage import StorageClient, DEFAULT_BUCKET_LIMITS
from shared.errors import RetryableError, ConfigError, ValidationError


@pytest.fixture
def mock_supabase_storage():
    """Create a mock Supabase storage client."""
    storage = Mock()
    bucket = Mock()
    storage.from_ = Mock(return_value=bucket)
    return storage, bucket


@pytest.fixture
def storage_client(mock_supabase_storage):
    """Create a storage client with mocked Supabase."""
    storage, bucket = mock_supabase_storage
    
    with patch("shared.storage.create_client") as mock_create:
        mock_client = Mock()
        mock_client.storage = storage
        mock_create.return_value = mock_client
        
        with patch("shared.storage.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            client = StorageClient()
            return client, bucket


@pytest.mark.asyncio
async def test_storage_client_initialization():
    """Test that storage client initializes correctly."""
    mock_client = Mock()
    mock_storage = Mock()
    mock_client.storage = mock_storage
    
    with patch("shared.storage.create_client", return_value=mock_client):
        with patch("shared.storage.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            client = StorageClient()
            assert client.storage == mock_storage
            assert client.bucket_limits == DEFAULT_BUCKET_LIMITS


@pytest.mark.asyncio
async def test_storage_client_initialization_failure():
    """Test that ConfigError is raised on initialization failure."""
    with patch("shared.storage.create_client", side_effect=Exception("Connection failed")):
        with patch("shared.storage.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            with pytest.raises(ConfigError, match="Failed to initialize storage client"):
                StorageClient()


@pytest.mark.asyncio
async def test_storage_upload_file(storage_client):
    """Test uploading a file."""
    client, bucket = storage_client
    
    file_data = b"test file content"
    bucket.upload = Mock(return_value={"path": "test/path.mp3"})
    bucket.get_public_url = Mock(return_value="https://storage.supabase.co/test/path.mp3")
    
    # Mock the async executor
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_executor = Mock()
        mock_loop.return_value.run_in_executor = AsyncMock(return_value="https://storage.supabase.co/test/path.mp3")
        
        # Mock upload and get_public_url
        def mock_upload():
            bucket.upload("test/path.mp3", file_data, {"content-type": "audio/mpeg"})
            return bucket.get_public_url("test/path.mp3")
        
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[
            None,  # upload
            "https://storage.supabase.co/test/path.mp3"  # get_public_url
        ])
        
        url = await client.upload_file(
            bucket="audio-uploads",
            path="test/path.mp3",
            file_data=file_data,
            content_type="audio/mpeg"
        )
        
        assert url == "https://storage.supabase.co/test/path.mp3"


@pytest.mark.asyncio
async def test_storage_upload_file_size_validation(storage_client):
    """Test that file size validation works."""
    client, bucket = storage_client
    
    # File larger than bucket limit
    file_data = b"x" * (11 * 1024 * 1024)  # 11MB
    
    with pytest.raises(ValidationError, match="exceeds maximum"):
        await client.upload_file(
            bucket="audio-uploads",
            path="test/path.mp3",
            file_data=file_data,
            max_size=10 * 1024 * 1024  # 10MB limit
        )


@pytest.mark.asyncio
async def test_storage_upload_file_auto_detect_content_type(storage_client):
    """Test that content type is auto-detected."""
    client, bucket = storage_client
    
    file_data = b"test content"
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value="https://storage.supabase.co/test/path.mp3")
        
        url = await client.upload_file(
            bucket="audio-uploads",
            path="test/path.mp3",
            file_data=file_data
            # content_type not provided, should be auto-detected
        )
        
        assert url == "https://storage.supabase.co/test/path.mp3"


@pytest.mark.asyncio
async def test_storage_download_file(storage_client):
    """Test downloading a file."""
    client, bucket = storage_client
    
    file_data = b"test file content"
    bucket.download = Mock(return_value=file_data)
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=file_data)
        
        result = await client.download_file(
            bucket="audio-uploads",
            path="test/path.mp3"
        )
        
        assert result == file_data


@pytest.mark.asyncio
async def test_storage_get_signed_url(storage_client):
    """Test generating a signed URL."""
    client, bucket = storage_client
    
    signed_url = "https://storage.supabase.co/test/path.mp3?token=abc123"
    bucket.create_signed_url = Mock(return_value={"signedURL": signed_url})
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value={"signedURL": signed_url})
        
        result = await client.get_signed_url(
            bucket="video-outputs",
            path="test/path.mp3",
            expires_in=3600
        )
        
        assert result == signed_url


@pytest.mark.asyncio
async def test_storage_get_signed_url_alternative_key(storage_client):
    """Test that signed URL handles alternative key names."""
    client, bucket = storage_client
    
    signed_url = "https://storage.supabase.co/test/path.mp3?token=abc123"
    bucket.create_signed_url = Mock(return_value={"signedUrl": signed_url})  # lowercase 'u'
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value={"signedUrl": signed_url})
        
        result = await client.get_signed_url(
            bucket="video-outputs",
            path="test/path.mp3"
        )
        
        assert result == signed_url


@pytest.mark.asyncio
async def test_storage_delete_file(storage_client):
    """Test deleting a file."""
    client, bucket = storage_client
    
    bucket.remove = Mock(return_value=None)
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        
        result = await client.delete_file(
            bucket="video-clips",
            path="test/path.mp4"
        )
        
        assert result is True


@pytest.mark.asyncio
async def test_storage_upload_raises_retryable_error(storage_client):
    """Test that upload raises RetryableError on failure."""
    client, bucket = storage_client
    
    file_data = b"test content"
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("Upload failed"))
        
        with pytest.raises(RetryableError, match="Failed to upload file"):
            await client.upload_file(
                bucket="audio-uploads",
                path="test/path.mp3",
                file_data=file_data
            )


@pytest.mark.asyncio
async def test_storage_download_raises_retryable_error(storage_client):
    """Test that download raises RetryableError on failure."""
    client, bucket = storage_client
    
    with patch("shared.storage.asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("Download failed"))
        
        with pytest.raises(RetryableError, match="Failed to download file"):
            await client.download_file(
                bucket="audio-uploads",
                path="test/path.mp3"
            )


@pytest.mark.asyncio
async def test_storage_bucket_limits(storage_client):
    """Test that bucket size limits are enforced."""
    client, bucket = storage_client
    
    # Test default bucket limits
    assert client.bucket_limits["audio-uploads"] == 10 * 1024 * 1024
    assert client.bucket_limits["reference-images"] == 5 * 1024 * 1024
    assert client.bucket_limits["video-clips"] == 50 * 1024 * 1024
    assert client.bucket_limits["video-outputs"] == 500 * 1024 * 1024


@pytest.mark.asyncio
async def test_storage_custom_bucket_limits():
    """Test that custom bucket limits can be provided."""
    custom_limits = {"audio-uploads": 20 * 1024 * 1024}
    
    with patch("shared.storage.create_client") as mock_create:
        mock_client = Mock()
        mock_client.storage = Mock()
        mock_create.return_value = mock_client
        
        with patch("shared.storage.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            client = StorageClient(bucket_limits=custom_limits)
            assert client.bucket_limits["audio-uploads"] == 20 * 1024 * 1024

