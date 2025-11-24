"""
Unit tests for composer normalizer.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from uuid import uuid4

from modules.composer.normalizer import normalize_clip
from shared.errors import CompositionError


class TestNormalizeClip:
    """Tests for normalize_clip function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.normalizer.run_ffmpeg_command')
    async def test_normalize_clip_success(self, mock_run_ffmpeg):
        """Test successful clip normalization."""
        job_id = uuid4()
        clip_bytes = b"fake_video_data" * 1000
        clip_index = 0
        
        # Create temp directory
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Mock FFmpeg command success
            mock_run_ffmpeg.return_value = None
            
            # Create output file to simulate FFmpeg success
            output_path = temp_dir / f"clip_{clip_index}_normalized.mp4"
            output_path.write_bytes(b"normalized_video")
            
            result = await normalize_clip(clip_bytes, clip_index, temp_dir, job_id, 1920, 1080)
            
            assert result == output_path
            assert result.exists()
            mock_run_ffmpeg.assert_called_once()
            
            # Verify FFmpeg command includes correct parameters
            call_args = mock_run_ffmpeg.call_args
            cmd = call_args[0][0]
            assert "ffmpeg" in cmd
            assert "-vf" in cmd
            assert "scale=1920:1080:flags=lanczos,fps=30" in cmd
            assert "-c:v" in cmd
            assert "libx264" in cmd
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.normalizer.run_ffmpeg_command')
    async def test_normalize_clip_output_not_created(self, mock_run_ffmpeg):
        """Test normalization fails when output file not created."""
        job_id = uuid4()
        clip_bytes = b"fake_video_data" * 1000
        clip_index = 0
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Mock FFmpeg command success but output file doesn't exist
            mock_run_ffmpeg.return_value = None
            
            with pytest.raises(CompositionError, match="Normalized clip not created"):
                await normalize_clip(clip_bytes, clip_index, temp_dir, job_id, 1920, 1080)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.normalizer.run_ffmpeg_command')
    async def test_normalize_clip_ffmpeg_failure(self, mock_run_ffmpeg):
        """Test normalization fails when FFmpeg fails."""
        job_id = uuid4()
        clip_bytes = b"fake_video_data" * 1000
        clip_index = 0
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Mock FFmpeg command failure
            from shared.errors import RetryableError
            mock_run_ffmpeg.side_effect = RetryableError("FFmpeg failed")
            
            with pytest.raises(CompositionError):
                await normalize_clip(clip_bytes, clip_index, temp_dir, job_id, 1920, 1080)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

