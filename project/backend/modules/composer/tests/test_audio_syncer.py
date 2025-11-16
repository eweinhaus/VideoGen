"""
Unit tests for audio_syncer module.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
from uuid import uuid4

from modules.composer.audio_syncer import sync_audio
from shared.errors import CompositionError, RetryableError


class TestSyncAudio:
    """Tests for sync_audio function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.audio_syncer.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_video_duration', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_audio_duration', new_callable=AsyncMock)
    async def test_sync_audio_success(self, mock_get_audio_duration, mock_get_video_duration, mock_run_ffmpeg):
        """Test successful audio synchronization."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_audio_sync")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "concatenated_video.mp4"
        video_path.touch()
        
        audio_bytes = b"fake audio data"
        
        # Mock durations (matching)
        mock_get_video_duration.return_value = 15.0
        mock_get_audio_duration.return_value = 15.0
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "video_with_audio.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        output_path, sync_drift = await sync_audio(video_path, audio_bytes, temp_dir, job_id)
        
        # Verify output path
        assert output_path == temp_dir / "video_with_audio.mp4"
        
        # Verify audio file was created
        audio_path = temp_dir / "audio.mp3"
        assert audio_path.exists()
        assert audio_path.read_bytes() == audio_bytes
        
        # Verify FFmpeg was called with correct arguments
        mock_run_ffmpeg.assert_called_once()
        call_args = mock_run_ffmpeg.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-i" in call_args
        assert "-c:v" in call_args
        assert "copy" in call_args
        assert "-c:a" in call_args
        assert "aac" in call_args
        assert "-shortest" in call_args
        
        # Verify sync drift calculation
        assert sync_drift == 0.0  # Perfect sync
        
        # Verify duration functions were called
        mock_get_video_duration.assert_called_once()
        mock_get_audio_duration.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.composer.audio_syncer.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_video_duration', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_audio_duration', new_callable=AsyncMock)
    async def test_sync_audio_with_drift(self, mock_get_audio_duration, mock_get_video_duration, mock_run_ffmpeg):
        """Test audio sync with duration mismatch (drift)."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_audio_sync_drift")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "concatenated_video.mp4"
        video_path.touch()
        
        audio_bytes = b"fake audio data"
        
        # Mock durations (mismatch)
        mock_get_video_duration.return_value = 15.0
        mock_get_audio_duration.return_value = 15.1  # 0.1s longer
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "video_with_audio.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        output_path, sync_drift = await sync_audio(video_path, audio_bytes, temp_dir, job_id)
        
        # Verify sync drift is calculated correctly (use approximate comparison for floating point)
        assert abs(sync_drift - 0.1) < 0.001
        
        # Verify -shortest flag is used (handles mismatch)
        call_args = mock_run_ffmpeg.call_args[0][0]
        assert "-shortest" in call_args
    
    @pytest.mark.asyncio
    @patch('modules.composer.audio_syncer.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_sync_audio_ffmpeg_failure(self, mock_run_ffmpeg):
        """Test error handling when FFmpeg fails."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_audio_sync_error")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "concatenated_video.mp4"
        video_path.touch()
        
        audio_bytes = b"fake audio data"
        
        # Mock FFmpeg failure
        mock_run_ffmpeg.side_effect = RetryableError("FFmpeg command failed")
        
        with pytest.raises(CompositionError):
            await sync_audio(video_path, audio_bytes, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.audio_syncer.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_sync_audio_output_not_created(self, mock_run_ffmpeg):
        """Test error when output file is not created."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_audio_sync_no_output")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "concatenated_video.mp4"
        video_path.touch()
        
        audio_bytes = b"fake audio data"
        
        # FFmpeg succeeds but output file doesn't exist
        mock_run_ffmpeg.return_value = None
        
        with pytest.raises(CompositionError, match="Video with audio not created"):
            await sync_audio(video_path, audio_bytes, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.audio_syncer.run_ffmpeg_command', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_video_duration', new_callable=AsyncMock)
    @patch('modules.composer.audio_syncer.get_audio_duration', new_callable=AsyncMock)
    async def test_sync_audio_shortest_flag_handles_mismatch(self, mock_get_audio_duration, mock_get_video_duration, mock_run_ffmpeg):
        """Test that -shortest flag handles duration mismatches correctly."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_audio_sync_shortest")
        temp_dir.mkdir(exist_ok=True)
        
        video_path = temp_dir / "concatenated_video.mp4"
        video_path.touch()
        
        audio_bytes = b"fake audio data"
        
        # Video shorter than audio
        mock_get_video_duration.return_value = 10.0
        mock_get_audio_duration.return_value = 15.0
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "video_with_audio.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        output_path, sync_drift = await sync_audio(video_path, audio_bytes, temp_dir, job_id)
        
        # Verify -shortest flag is used
        call_args = mock_run_ffmpeg.call_args[0][0]
        assert "-shortest" in call_args
        
        # Sync drift should be 5.0s
        assert sync_drift == 5.0

