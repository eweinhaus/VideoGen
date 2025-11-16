"""
Unit tests for encoder module.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
from uuid import uuid4

from modules.composer.encoder import encode_final_video
from shared.errors import CompositionError, RetryableError


class TestEncodeFinalVideo:
    """Tests for encode_final_video function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.encoder.get_video_duration', new_callable=AsyncMock)
    async def test_encode_final_video_success(self, mock_get_duration, mock_run_ffmpeg):
        """Test successful final video encoding."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        # Create output file with reasonable size (simulate encoding)
        output_path = temp_dir / "final_video.mp4"
        output_path.write_bytes(b"x" * 1024 * 1024)  # 1MB
        
        mock_get_duration.return_value = 15.0
        
        result_path = await encode_final_video(video_path, temp_dir, job_id)
        
        # Verify output path
        assert result_path == temp_dir / "final_video.mp4"
        
        # Verify FFmpeg was called with correct arguments
        mock_run_ffmpeg.assert_called_once()
        call_args = mock_run_ffmpeg.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-threads" in call_args
        assert "-c:v" in call_args
        assert "libx264" in call_args
        assert "-c:a" in call_args
        assert "aac" in call_args
        assert "-b:v" in call_args
        assert "5000k" in call_args
        assert "-b:a" in call_args
        assert "192k" in call_args
        assert "-preset" in call_args
        assert "medium" in call_args
        assert "-movflags" in call_args
        assert "+faststart" in call_args
        
        # Verify duration validation was called
        mock_get_duration.assert_called_once_with(result_path)
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_encode_final_video_ffmpeg_failure(self, mock_run_ffmpeg):
        """Test error handling when FFmpeg fails."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder_error")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        # Mock FFmpeg failure
        mock_run_ffmpeg.side_effect = RetryableError("FFmpeg command failed")
        
        with pytest.raises(CompositionError):
            await encode_final_video(video_path, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_encode_final_video_output_not_created(self, mock_run_ffmpeg):
        """Test error when output file is not created."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder_no_output")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        # FFmpeg succeeds but output file doesn't exist
        mock_run_ffmpeg.return_value = None
        
        with pytest.raises(CompositionError, match="Final video not created"):
            await encode_final_video(video_path, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.encoder.get_video_duration', new_callable=AsyncMock)
    async def test_encode_final_video_too_small(self, mock_get_duration, mock_run_ffmpeg):
        """Test error when output file is too small (suspicious)."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder_small")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        # Create output file that's too small (<1KB)
        output_path = temp_dir / "final_video.mp4"
        output_path.write_bytes(b"x" * 500)  # 500 bytes
        
        with pytest.raises(CompositionError, match="Final video too small"):
            await encode_final_video(video_path, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.encoder.get_video_duration', new_callable=AsyncMock)
    async def test_encode_final_video_invalid_duration(self, mock_get_duration, mock_run_ffmpeg):
        """Test error when output video has invalid duration."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder_invalid_duration")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        # Create output file
        output_path = temp_dir / "final_video.mp4"
        output_path.write_bytes(b"x" * 1024 * 1024)  # 1MB
        
        # Mock invalid duration (0 or negative)
        mock_get_duration.return_value = 0.0
        
        with pytest.raises(CompositionError, match="Invalid video duration"):
            await encode_final_video(video_path, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.encoder.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.encoder.get_video_duration', new_callable=AsyncMock)
    async def test_encode_final_video_uses_config_constants(self, mock_get_duration, mock_run_ffmpeg):
        """Test that encoding uses constants from config module."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_encoder_config")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "video_with_audio.mp4"
        video_path.touch()
        
        output_path = temp_dir / "final_video.mp4"
        output_path.write_bytes(b"x" * 1024 * 1024)  # 1MB
        
        mock_get_duration.return_value = 15.0
        
        await encode_final_video(video_path, temp_dir, job_id)
        
        # Verify FFmpeg command uses config values
        call_args = mock_run_ffmpeg.call_args[0][0]
        
        # Check that config constants are used (via string matching)
        cmd_str = " ".join(call_args)
        assert "libx264" in cmd_str  # OUTPUT_VIDEO_CODEC
        assert "aac" in cmd_str  # OUTPUT_AUDIO_CODEC
        assert "5000k" in cmd_str  # OUTPUT_VIDEO_BITRATE
        assert "192k" in cmd_str  # OUTPUT_AUDIO_BITRATE
        assert "medium" in cmd_str  # FFMPEG_PRESET
        assert "+faststart" in cmd_str  # Web optimization

