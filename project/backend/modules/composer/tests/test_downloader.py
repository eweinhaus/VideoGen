"""
Unit tests for composer downloader.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from modules.composer.downloader import download_all_clips, download_audio
from shared.models.video import Clip
from shared.errors import RetryableError, CompositionError
from decimal import Decimal


def sample_clip(clip_index: int, video_url: str) -> Clip:
    """Create a sample clip for testing."""
    return Clip(
        clip_index=clip_index,
        video_url=video_url,
        actual_duration=5.0,
        target_duration=5.0,
        duration_diff=0.0,
        status="success",
        cost=Decimal("0.10"),
        generation_time=10.0
    )


class TestDownloadAllClips:
    """Tests for download_all_clips function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.downloader.StorageClient')
    @patch('modules.composer.downloader.parse_supabase_url')
    async def test_download_all_clips_success(self, mock_parse_url, mock_storage_class):
        """Test successful parallel downloads."""
        job_id = uuid4()
        clips = [
            sample_clip(0, "https://project.supabase.co/storage/v1/object/public/video-clips/clip0.mp4"),
            sample_clip(1, "https://project.supabase.co/storage/v1/object/public/video-clips/clip1.mp4"),
        ]
        
        # Mock storage client
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(side_effect=[
            b"x" * 2048,  # 2KB - valid size
            b"y" * 2048   # 2KB - valid size
        ])
        mock_storage_class.return_value = mock_storage
        
        # Mock URL parsing
        mock_parse_url.side_effect = [
            ("video-clips", "clip0.mp4"),
            ("video-clips", "clip1.mp4")
        ]
        
        result = await download_all_clips(clips, job_id)
        
        assert len(result) == 2
        assert len(result[0]) == 2048
        assert len(result[1]) == 2048
        assert mock_storage.download_file.call_count == 2
    
    @pytest.mark.asyncio
    @patch('modules.composer.downloader.StorageClient')
    @patch('modules.composer.downloader.parse_supabase_url')
    async def test_download_all_clips_file_too_small(self, mock_parse_url, mock_storage_class):
        """Test download fails when file is too small."""
        job_id = uuid4()
        clips = [sample_clip(0, "https://project.supabase.co/storage/v1/object/public/video-clips/clip0.mp4")]
        
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(return_value=b"x" * 500)  # Less than 1KB
        mock_storage_class.return_value = mock_storage
        
        mock_parse_url.return_value = ("video-clips", "clip0.mp4")
        
        with pytest.raises(RetryableError, match="file too small"):
            await download_all_clips(clips, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.downloader.StorageClient')
    @patch('modules.composer.downloader.parse_supabase_url')
    async def test_download_all_clips_failure(self, mock_parse_url, mock_storage_class):
        """Test download failure raises RetryableError."""
        job_id = uuid4()
        clips = [sample_clip(0, "https://project.supabase.co/storage/v1/object/public/video-clips/clip0.mp4")]
        
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(side_effect=Exception("Network error"))
        mock_storage_class.return_value = mock_storage
        
        mock_parse_url.return_value = ("video-clips", "clip0.mp4")
        
        with pytest.raises(RetryableError):
            await download_all_clips(clips, job_id)


class TestDownloadAudio:
    """Tests for download_audio function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.downloader.StorageClient')
    @patch('modules.composer.downloader.parse_supabase_url')
    async def test_download_audio_success(self, mock_parse_url, mock_storage_class):
        """Test successful audio download."""
        job_id = uuid4()
        audio_url = "https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3"
        
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(return_value=b"x" * 2048)  # 2KB - valid size
        mock_storage_class.return_value = mock_storage
        
        mock_parse_url.return_value = ("audio-uploads", "audio.mp3")
        
        result = await download_audio(audio_url, job_id)
        
        assert len(result) == 2048
        mock_storage.download_file.assert_called_once_with("audio-uploads", "audio.mp3")
    
    @pytest.mark.asyncio
    @patch('modules.composer.downloader.StorageClient')
    @patch('modules.composer.downloader.parse_supabase_url')
    async def test_download_audio_failure(self, mock_parse_url, mock_storage_class):
        """Test audio download failure raises RetryableError."""
        job_id = uuid4()
        audio_url = "https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3"
        
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(side_effect=Exception("Network error"))
        mock_storage_class.return_value = mock_storage
        
        mock_parse_url.return_value = ("audio-uploads", "audio.mp3")
        
        with pytest.raises(RetryableError):
            await download_audio(audio_url, job_id)

