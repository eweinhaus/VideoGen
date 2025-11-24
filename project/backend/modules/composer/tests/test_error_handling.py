"""
Unit tests for error handling in composer module.

Tests error classification, retry logic, and edge case handling.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from decimal import Decimal
from pathlib import Path

from modules.composer.process import process
from modules.composer.downloader import download_all_clips, download_audio
from modules.composer.utils import run_ffmpeg_command, check_ffmpeg_available
from shared.models.video import Clips, Clip
from shared.errors import CompositionError, RetryableError


def sample_clip(clip_index: int, video_url: str = None) -> Clip:
    """Create a sample clip for testing."""
    if video_url is None:
        video_url = f"https://project.supabase.co/storage/v1/object/public/video-clips/clip{clip_index}.mp4"
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


def sample_clips(job_id, num_clips: int = 3) -> Clips:
    """Create sample clips collection."""
    clips_list = [sample_clip(i) for i in range(num_clips)]
    return Clips(
        job_id=job_id,
        clips=clips_list,
        total_clips=num_clips,
        successful_clips=num_clips,
        failed_clips=0,
        total_cost=Decimal("0.30"),
        total_generation_time=30.0
    )


class TestErrorClassification:
    """Tests for error classification (permanent vs retryable)."""
    
    @pytest.mark.asyncio
    async def test_composition_error_permanent_failure(self):
        """Test CompositionError is raised for permanent failures."""
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=2)  # <3 clips = permanent failure
        
        with patch('modules.composer.utils.check_ffmpeg_available', return_value=True), \
             patch('modules.composer.process.check_ffmpeg_available', return_value=True, create=True):
            with pytest.raises(CompositionError):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                    transitions=[]
                )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_retryable_error_network_failure(self, mock_check_ffmpeg):
        """Test RetryableError is raised for network failures."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        # Need to patch where it's imported in process.py
        with \
             patch('modules.composer.downloader.download_all_clips', new_callable=AsyncMock) as mock_download, \
             patch('modules.composer.downloader.download_audio', new_callable=AsyncMock):
            
            # Simulate network failure
            mock_download.side_effect = RetryableError("Network connection failed")
            
            with pytest.raises(RetryableError):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                    transitions=[]
                )


class TestDownloadErrorHandling:
    """Tests for download error handling."""
    
    @pytest.mark.asyncio
    async def test_download_file_too_small(self):
        """Test download fails when file is too small (<1KB)."""
        job_id = uuid4()
        clips = [sample_clip(0)]
        
        with patch('modules.composer.downloader.StorageClient') as mock_storage, \
             patch('modules.composer.downloader.parse_supabase_url', return_value=("video-clips", "clip0.mp4")):
            mock_storage_instance = MagicMock()
            # Return file that's too small
            mock_storage_instance.download_file = AsyncMock(return_value=b"x" * 500)  # <1KB
            mock_storage.return_value = mock_storage_instance
            
            # CompositionError is raised, then wrapped in RetryableError
            with pytest.raises(RetryableError) as exc_info:
                await download_all_clips(clips, job_id)
            # Check that the underlying error mentions file too small
            assert "file too small" in str(exc_info.value) or "too small" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_download_large_file_warning(self):
        """Test large file (>200MB) triggers warning but continues."""
        job_id = uuid4()
        clips = [sample_clip(0)]
        
        with patch('modules.composer.downloader.StorageClient') as mock_storage, \
             patch('modules.composer.downloader.parse_supabase_url', return_value=("video-clips", "clip0.mp4")), \
             patch('modules.composer.downloader.logger') as mock_logger:
            mock_storage_instance = MagicMock()
            # Return large file (>200MB)
            mock_storage_instance.download_file = AsyncMock(return_value=b"x" * (201 * 1024 * 1024))
            mock_storage.return_value = mock_storage_instance
            
            # Should succeed but log warning
            result = await download_all_clips(clips, job_id)
            assert len(result) == 1
            # Verify warning was logged
            assert mock_logger.warning.called


class TestFFmpegErrorHandling:
    """Tests for FFmpeg error handling."""
    
    @pytest.mark.asyncio
    async def test_ffmpeg_command_retryable_error(self):
        """Test FFmpeg errors are treated as retryable."""
        job_id = uuid4()
        cmd = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            # Simulate FFmpeg failure
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"FFmpeg error"))
            mock_subprocess.return_value = mock_process
            
            # Should raise RetryableError (will be retried)
            with pytest.raises(RetryableError):
                await run_ffmpeg_command(cmd, job_id, timeout=300)
    
    @pytest.mark.asyncio
    async def test_ffmpeg_timeout_retryable(self):
        """Test FFmpeg timeout is treated as retryable."""
        job_id = uuid4()
        cmd = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        
        with patch('asyncio.create_subprocess_exec') as mock_subprocess, \
             patch('asyncio.wait_for') as mock_wait:
            # Simulate timeout
            import asyncio
            mock_wait.side_effect = asyncio.TimeoutError()
            
            # Should raise RetryableError
            with pytest.raises(RetryableError, match="timeout"):
                await run_ffmpeg_command(cmd, job_id, timeout=300)


class TestEdgeCaseHandling:
    """Tests for edge case handling."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_empty_clips_list(self, mock_check_ffmpeg):
        """Test empty clips list is handled."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = Clips(
            job_id=job_id,
            clips=[],
            total_clips=0,
            successful_clips=0,
            failed_clips=0,
            total_cost=Decimal("0.00"),
            total_generation_time=0.0
        )
        
        # Empty list will fail minimum clips check (after FFmpeg check)
        with pytest.raises(CompositionError) as exc_info:
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
        # Should fail on minimum clips (after FFmpeg check passes)
        assert "Minimum 3 clips" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_invalid_audio_url_format(self, mock_check_ffmpeg):
        """Test invalid audio URL format is handled."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        # Patch to avoid real downloads and force parse error on audio URL
        with \
             patch('modules.composer.downloader.download_all_clips', new_callable=AsyncMock, return_value=[b"clip0", b"clip1", b"clip2"]) as mock_download, \
             patch('modules.composer.downloader.parse_supabase_url') as mock_parse:
            
            # Make parse_supabase_url raise for audio URL only
            def parse_side_effect(url: str):
                if url == "invalid-url":
                    raise ValueError("Invalid URL format")
                # Return dummy bucket/path for clip URLs
                return ("video-clips", "clip0.mp4")
            
            mock_parse.side_effect = parse_side_effect
            
            # Expect RetryableError from download_audio wrapping the parse error
            with pytest.raises(RetryableError):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="invalid-url",
                    transitions=[]
                )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=False)
    async def test_ffmpeg_not_installed(self, mock_check_ffmpeg):
        """Test FFmpeg not installed is handled with clear error message."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        with pytest.raises(CompositionError, match="FFmpeg not found"):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                    transitions=[]
                )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_non_sequential_clip_indices(self, mock_check_ffmpeg):
        """Test non-sequential clip indices are detected."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        clips.clips[1].clip_index = 5  # Gap in indices
        
        with pytest.raises(CompositionError) as exc_info:
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
        # Should fail on sequential indices (after FFmpeg check passes)
        assert "Clip indices must be sequential" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_job_id_type_conversion(self, mock_check_ffmpeg):
        """Test job_id string to UUID conversion works."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        # Mock all dependencies
        with \
             patch('modules.composer.downloader.download_all_clips', new_callable=AsyncMock) as mock_download, \
             patch('modules.composer.downloader.download_audio', new_callable=AsyncMock) as mock_download_audio, \
             patch('modules.composer.normalizer.normalize_clip', new_callable=AsyncMock) as mock_normalize, \
             patch('modules.composer.duration_handler.handle_clip_duration', new_callable=AsyncMock) as mock_duration, \
             patch('modules.composer.transition_applier.apply_transitions', new_callable=AsyncMock) as mock_transitions, \
             patch('modules.composer.audio_syncer.sync_audio', new_callable=AsyncMock) as mock_sync, \
             patch('modules.composer.encoder.encode_final_video', new_callable=AsyncMock) as mock_encode, \
             patch('shared.storage.StorageClient') as mock_storage, \
             patch('modules.composer.utils.get_video_duration', new_callable=AsyncMock) as mock_get_duration, \
             patch('api_gateway.services.event_publisher.publish_event', new_callable=AsyncMock):
            
            from pathlib import Path
            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True
            mock_path.stat.return_value = MagicMock(st_size=1024 * 1024 * 10)
            mock_path.read_bytes.return_value = b"video_bytes"
            
            mock_download.return_value = [b"clip0", b"clip1", b"clip2"]
            mock_download_audio.return_value = b"audio"
            mock_normalize.return_value = mock_path
            mock_duration.return_value = (mock_path, False, False)
            mock_transitions.return_value = mock_path
            mock_sync.return_value = (mock_path, 0.0)
            mock_encode.return_value = mock_path
            mock_get_duration.return_value = 15.0
            
            mock_storage_instance = MagicMock()
            mock_storage_instance.upload_file = AsyncMock(return_value="https://example.com/video.mp4")
            mock_storage.return_value = mock_storage_instance
            
            # Pass job_id as string - should convert to UUID internally
            result = await process(
                job_id=str(job_id),  # String format
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
            
            # Should succeed (conversion worked)
            assert result.job_id == job_id  # UUID format


class TestOutputValidation:
    """Tests for output validation."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_output_file_too_small(self, mock_check_ffmpeg):
        """Test output validation fails when file is too small."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        # Mock all dependencies
        process_module_reloaded = sys.modules.get('modules.composer.process')
        with patch.object(process_module_reloaded, 'publish_progress', new_callable=AsyncMock), \
             patch('modules.composer.downloader.download_all_clips', new_callable=AsyncMock) as mock_download, \
             patch('modules.composer.downloader.download_audio', new_callable=AsyncMock) as mock_download_audio, \
             patch('modules.composer.normalizer.normalize_clip', new_callable=AsyncMock) as mock_normalize, \
             patch('modules.composer.duration_handler.handle_clip_duration', new_callable=AsyncMock) as mock_duration, \
             patch('modules.composer.transition_applier.apply_transitions', new_callable=AsyncMock) as mock_transitions, \
             patch('modules.composer.audio_syncer.sync_audio', new_callable=AsyncMock) as mock_sync, \
             patch('modules.composer.encoder.encode_final_video', new_callable=AsyncMock) as mock_encode, \
             patch('shared.storage.StorageClient') as mock_storage, \
             patch('modules.composer.utils.get_video_duration', new_callable=AsyncMock) as mock_get_duration, \
             patch('api_gateway.services.event_publisher.publish_event', new_callable=AsyncMock):
            
            from pathlib import Path
            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True
            # File too small (<1KB)
            mock_path.stat.return_value = MagicMock(st_size=500)
            mock_path.read_bytes.return_value = b"x" * 500
            
            mock_download.return_value = [b"clip0", b"clip1", b"clip2"]
            mock_download_audio.return_value = b"audio"
            mock_normalize.return_value = mock_path
            mock_duration.return_value = (mock_path, False, False)
            mock_transitions.return_value = mock_path
            mock_sync.return_value = (mock_path, 0.0)
            # Encoder will check file size and fail
            mock_encode.side_effect = CompositionError("Final video too small: 500 bytes")
            mock_get_duration.return_value = 15.0
            
            mock_storage_instance = MagicMock()
            mock_storage_instance.upload_file = AsyncMock(return_value="https://example.com/video.mp4")
            mock_storage.return_value = mock_storage_instance
            
            # Should fail validation in encoder
            with pytest.raises(CompositionError, match="too small"):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                    transitions=[]
                )

