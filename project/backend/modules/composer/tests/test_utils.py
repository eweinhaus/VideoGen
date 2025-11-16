"""
Unit tests for composer utils.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from modules.composer.utils import (
    check_ffmpeg_available,
    run_ffmpeg_command,
    get_video_duration,
    get_audio_duration
)
from shared.errors import RetryableError, CompositionError


class TestCheckFFmpegAvailable:
    """Tests for check_ffmpeg_available function."""
    
    @patch('modules.composer.utils.shutil.which')
    def test_ffmpeg_available(self, mock_which):
        """Test when FFmpeg is available."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        assert check_ffmpeg_available() is True
    
    @patch('modules.composer.utils.shutil.which')
    def test_ffmpeg_not_available(self, mock_which):
        """Test when FFmpeg is not available."""
        mock_which.return_value = None
        assert check_ffmpeg_available() is False


class TestRunFFmpegCommand:
    """Tests for run_ffmpeg_command function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.asyncio.create_subprocess_exec')
    async def test_run_ffmpeg_success(self, mock_subprocess):
        """Test successful FFmpeg command execution."""
        from uuid import uuid4
        job_id = uuid4()
        
        # Mock successful subprocess
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        
        cmd = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        await run_ffmpeg_command(cmd, job_id=job_id, timeout=300)
        
        mock_subprocess.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.asyncio.create_subprocess_exec')
    async def test_run_ffmpeg_failure(self, mock_subprocess):
        """Test FFmpeg command failure."""
        from uuid import uuid4
        job_id = uuid4()
        
        # Mock failed subprocess
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))
        mock_process.returncode = 1
        mock_subprocess.return_value = mock_process
        
        cmd = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        
        with pytest.raises(RetryableError):
            await run_ffmpeg_command(cmd, job_id=job_id, timeout=300)


class TestGetVideoDuration:
    """Tests for get_video_duration function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.subprocess.run')
    async def test_get_video_duration_success(self, mock_subprocess):
        """Test successful duration extraction."""
        mock_result = MagicMock()
        mock_result.stdout = "10.5\n"
        mock_result.check_returncode = MagicMock()
        mock_subprocess.return_value = mock_result
        
        video_path = Path("/tmp/test.mp4")
        duration = await get_video_duration(video_path)
        
        assert duration == 10.5
        mock_subprocess.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.subprocess.run')
    async def test_get_video_duration_fallback(self, mock_subprocess):
        """Test duration extraction fallback on failure."""
        mock_subprocess.side_effect = FileNotFoundError("ffprobe not found")
        
        video_path = Path("/tmp/test.mp4")
        duration = await get_video_duration(video_path)
        
        assert duration == 5.0  # Default fallback


class TestGetAudioDuration:
    """Tests for get_audio_duration function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.get_video_duration')
    async def test_get_audio_duration(self, mock_get_video_duration):
        """Test audio duration extraction (reuses get_video_duration)."""
        mock_get_video_duration.return_value = 15.0
        
        audio_path = Path("/tmp/test.mp3")
        duration = await get_audio_duration(audio_path)
        
        assert duration == 15.0
        mock_get_video_duration.assert_called_once_with(audio_path)

