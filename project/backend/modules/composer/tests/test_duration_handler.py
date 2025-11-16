"""
Unit tests for composer duration handler.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

from modules.composer.duration_handler import handle_clip_duration
from shared.models.video import Clip
from shared.errors import CompositionError


def sample_clip(clip_index: int, actual_duration: float, target_duration: float) -> Clip:
    """Create a sample clip for testing."""
    return Clip(
        clip_index=clip_index,
        video_url=f"https://project.supabase.co/storage/v1/object/public/video-clips/clip{clip_index}.mp4",
        actual_duration=actual_duration,
        target_duration=target_duration,
        duration_diff=actual_duration - target_duration,
        status="success",
        cost=Decimal("0.10"),
        generation_time=10.0
    )


class TestHandleClipDuration:
    """Tests for handle_clip_duration function."""
    
    @pytest.mark.asyncio
    async def test_duration_within_tolerance(self):
        """Test clip with duration within tolerance (no operation)."""
        job_id = uuid4()
        clip = sample_clip(0, 5.0, 5.2)  # 0.2s difference, within 0.5s tolerance
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            result_path, was_trimmed, was_looped = await handle_clip_duration(
                clip_path, clip, temp_dir, job_id
            )
            
            assert result_path == clip_path  # Same path returned
            assert was_trimmed is False
            assert was_looped is False
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_trim_clip_too_long(self, mock_run_ffmpeg):
        """Test trimming clip that is too long."""
        job_id = uuid4()
        clip = sample_clip(0, 10.0, 5.0)  # 5s too long
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success
            mock_run_ffmpeg.return_value = None
            
            # Create output file
            output_path = temp_dir / "clip_0_duration_fixed.mp4"
            output_path.write_bytes(b"trimmed_video")
            
            result_path, was_trimmed, was_looped = await handle_clip_duration(
                clip_path, clip, temp_dir, job_id
            )
            
            assert result_path == output_path
            assert was_trimmed is True
            assert was_looped is False
            
            # Verify FFmpeg command
            call_args = mock_run_ffmpeg.call_args
            cmd = call_args[0][0]
            assert "-t" in cmd
            assert "5.0" in cmd  # Target duration
            assert "-c" in cmd
            assert "copy" in cmd
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_loop_clip_too_short(self, mock_run_ffmpeg):
        """Test looping clip that is too short."""
        job_id = uuid4()
        clip = sample_clip(0, 2.0, 5.0)  # 3s too short
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success
            mock_run_ffmpeg.return_value = None
            
            # Create output file
            output_path = temp_dir / "clip_0_duration_fixed.mp4"
            output_path.write_bytes(b"looped_video")
            
            result_path, was_trimmed, was_looped = await handle_clip_duration(
                clip_path, clip, temp_dir, job_id
            )
            
            assert result_path == output_path
            assert was_trimmed is False
            assert was_looped is True
            
            # Verify concat file was created
            concat_file = temp_dir / "clip_0_concat.txt"
            assert concat_file.exists()
            
            # Verify concat file content (should have 3 loops: 2.0s * 3 = 6s, then trim to 5s)
            with open(concat_file, "r") as f:
                content = f.read()
                assert "file '" in content
                assert str(clip_path.absolute()) in content
                # Should have 3 entries (int(5.0/2.0) + 1 = 3)
                assert content.count("file '") == 3
            
            # Verify FFmpeg command
            call_args = mock_run_ffmpeg.call_args
            cmd = call_args[0][0]
            assert "-f" in cmd
            assert "concat" in cmd
            assert "-t" in cmd
            assert "5.0" in cmd  # Target duration
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_trim_failure(self, mock_run_ffmpeg):
        """Test trim operation failure."""
        job_id = uuid4()
        clip = sample_clip(0, 10.0, 5.0)  # Too long
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg failure
            from shared.errors import RetryableError
            mock_run_ffmpeg.side_effect = RetryableError("FFmpeg failed")
            
            with pytest.raises(CompositionError):
                await handle_clip_duration(clip_path, clip, temp_dir, job_id)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_loop_failure(self, mock_run_ffmpeg):
        """Test loop operation failure."""
        job_id = uuid4()
        clip = sample_clip(0, 2.0, 5.0)  # Too short
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg failure
            from shared.errors import RetryableError
            mock_run_ffmpeg.side_effect = RetryableError("FFmpeg failed")
            
            with pytest.raises(CompositionError):
                await handle_clip_duration(clip_path, clip, temp_dir, job_id)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

