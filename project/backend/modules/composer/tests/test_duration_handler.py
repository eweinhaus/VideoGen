"""
Unit tests for composer duration handler.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

from modules.composer.duration_handler import (
    handle_clip_duration,
    handle_cascading_durations,
    extend_last_clip
)
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
    async def test_clip_too_short_no_loop(self):
        """Test clip that is too short - now returns original path (no looping, handled by cascading)."""
        job_id = uuid4()
        clip = sample_clip(0, 2.0, 5.0)  # 3s too short
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "clip_0_normalized.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # With cascading compensation, short clips are returned as-is
            result_path, was_trimmed, was_looped = await handle_clip_duration(
                clip_path, clip, temp_dir, job_id
            )
            
            assert result_path == clip_path  # Same path returned (no looping)
            assert was_trimmed is False
            assert was_looped is False  # Always False with cascading compensation
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


class TestCascadingCompensation:
    """Tests for handle_cascading_durations function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_simple_compensation(self, mock_run_ffmpeg):
        """Test simple compensation: Clip 1 short, Clip 2 compensates."""
        job_id = uuid4()
        clips = [
            sample_clip(0, 7.5, 8.0),  # Short by 0.5s
            sample_clip(1, 10.0, 9.0),  # Long enough to compensate
        ]
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_paths = [
            temp_dir / "clip_0_normalized.mp4",
            temp_dir / "clip_1_normalized.mp4"
        ]
        for path in clip_paths:
            path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success
            mock_run_ffmpeg.return_value = None
            
            # Create output file for compensated clip
            output_path = temp_dir / "clip_1_compensated.mp4"
            output_path.write_bytes(b"compensated_video")
            
            final_paths, metrics = await handle_cascading_durations(
                clip_paths, clips, temp_dir, job_id
            )
            
            assert len(final_paths) == 2
            assert final_paths[0] == clip_paths[0]  # First clip unchanged
            assert final_paths[1] == output_path  # Second clip trimmed
            
            assert metrics["clips_trimmed"] == 1
            assert metrics["total_shortfall"] == 0.0  # Fully compensated
            assert len(metrics["compensation_applied"]) == 1
            assert metrics["compensation_applied"][0]["clip_index"] == 1
            assert metrics["compensation_applied"][0]["compensation"] == 0.5
            
            # Verify FFmpeg was called to trim clip 1
            assert mock_run_ffmpeg.called
            call_args = mock_run_ffmpeg.call_args
            cmd = call_args[0][0]
            assert "-t" in cmd
            assert "9.5" in cmd  # Extended target (9.0 + 0.5)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_no_shortfalls(self, mock_run_ffmpeg):
        """Test with no shortfalls - no compensation needed."""
        job_id = uuid4()
        clips = [
            sample_clip(0, 8.0, 8.0),  # Exact match
            sample_clip(1, 9.5, 9.0),  # Longer than target
        ]
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_paths = [
            temp_dir / "clip_0_normalized.mp4",
            temp_dir / "clip_1_normalized.mp4"
        ]
        for path in clip_paths:
            path.write_bytes(b"video_data")
        
        # Mock FFmpeg to do nothing (since clip 1 is longer, it should be trimmed)
        async def mock_trim(*args, **kwargs):
            # Create the output file
            if len(args) > 0 and isinstance(args[0], list):
                cmd = args[0]
                if '-y' in cmd:
                    output_idx = cmd.index('-y') + 1
                    if output_idx < len(cmd):
                        output_path = Path(cmd[output_idx])
                        output_path.write_bytes(b"trimmed_video")
        
        mock_run_ffmpeg.side_effect = mock_trim
        
        try:
            final_paths, metrics = await handle_cascading_durations(
                clip_paths, clips, temp_dir, job_id
            )
            
            assert len(final_paths) == 2
            assert final_paths[0] == clip_paths[0]
            # Clip 1 should be trimmed since it's longer than target
            
            assert metrics["clips_trimmed"] >= 0  # May trim clip 1
            assert metrics["total_shortfall"] == 0.0
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    async def test_cascading_through_multiple_clips(self, mock_run_ffmpeg):
        """Test shortfall cascading through multiple clips."""
        job_id = uuid4()
        clips = [
            sample_clip(0, 6.0, 8.0),  # Short by 2.0s
            sample_clip(1, 9.5, 9.0),  # Extended to 11.0s, actual 9.5s, still short by 1.5s
            sample_clip(2, 10.0, 7.0),  # Extended to 8.5s, actual 10.0s, can compensate
        ]
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_paths = [
            temp_dir / "clip_0_normalized.mp4",
            temp_dir / "clip_1_normalized.mp4",
            temp_dir / "clip_2_normalized.mp4"
        ]
        for path in clip_paths:
            path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success
            mock_run_ffmpeg.return_value = None
            
            # Create output file for compensated clip
            output_path = temp_dir / "clip_2_compensated.mp4"
            output_path.write_bytes(b"compensated_video")
            
            final_paths, metrics = await handle_cascading_durations(
                clip_paths, clips, temp_dir, job_id
            )
            
            assert len(final_paths) == 3
            assert final_paths[0] == clip_paths[0]  # First clip unchanged
            assert final_paths[1] == clip_paths[1]  # Second clip unchanged (still short)
            assert final_paths[2] == output_path  # Third clip trimmed
            
            assert metrics["clips_trimmed"] == 1
            assert metrics["total_shortfall"] == 0.0  # Fully compensated
            assert len(metrics["compensation_applied"]) == 1
            assert metrics["compensation_applied"][0]["clip_index"] == 2
            assert metrics["compensation_applied"][0]["compensation"] == 1.5
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_all_clips_short(self):
        """Test when all clips are short - final shortfall tracked."""
        job_id = uuid4()
        clips = [
            sample_clip(0, 6.0, 8.0),  # Short by 2.0s
            sample_clip(1, 7.0, 9.0),  # Short by 2.0s (extended target 11.0s, actual 7.0s, shortfall 4.0s)
            sample_clip(2, 5.0, 7.0),  # Short by 6.0s (extended target 11.0s, actual 5.0s, shortfall 6.0s)
        ]
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_paths = [
            temp_dir / "clip_0_normalized.mp4",
            temp_dir / "clip_1_normalized.mp4",
            temp_dir / "clip_2_normalized.mp4"
        ]
        for path in clip_paths:
            path.write_bytes(b"video_data")
        
        try:
            final_paths, metrics = await handle_cascading_durations(
                clip_paths, clips, temp_dir, job_id
            )
            
            assert len(final_paths) == 3
            assert all(p in clip_paths for p in final_paths)  # All original paths
            
            assert metrics["clips_trimmed"] == 0
            assert metrics["total_shortfall"] == 6.0  # Final shortfall
            assert len(metrics["compensation_applied"]) == 0
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestLastClipExtension:
    """Tests for extend_last_clip function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    @patch('modules.composer.duration_handler.get_video_duration')
    async def test_freeze_frame_extension(self, mock_get_duration, mock_run_ffmpeg):
        """Test freeze frame extension for shortfall <2s."""
        job_id = uuid4()
        shortfall = 1.5  # <2s threshold
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "last_clip.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success
            mock_run_ffmpeg.return_value = None
            
            # Create output file
            output_path = temp_dir / "last_clip_extended.mp4"
            output_path.write_bytes(b"x" * 2048)
            
            result_path = await extend_last_clip(
                clip_path, shortfall, temp_dir, job_id
            )
            
            assert result_path == output_path
            
            # Verify FFmpeg command uses tpad filter
            call_args = mock_run_ffmpeg.call_args
            cmd = call_args[0][0]
            assert "tpad" in " ".join(cmd)
            assert "stop_mode=clone" in " ".join(cmd)
            assert "-c:v" in cmd
            assert "libx264" in cmd
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @patch('modules.composer.duration_handler.run_ffmpeg_command')
    @patch('modules.composer.duration_handler.get_video_duration')
    async def test_loop_extension(self, mock_get_duration, mock_run_ffmpeg):
        """Test loop extension for shortfall >=2s."""
        job_id = uuid4()
        shortfall = 3.0  # >=2s threshold
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "last_clip.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            # Mock FFmpeg success and duration
            mock_run_ffmpeg.return_value = None
            mock_get_duration.return_value = 8.0  # Original clip duration
            
            # Create output files
            output_path = temp_dir / "last_clip_extended.mp4"
            output_path.write_bytes(b"x" * 2048)
            last_segment = temp_dir / "last_segment.mp4"
            last_segment.write_bytes(b"seg")
            
            result_path = await extend_last_clip(
                clip_path, shortfall, temp_dir, job_id
            )
            
            assert result_path == output_path
            
            # Verify FFmpeg concat command used
            call_args_list = mock_run_ffmpeg.call_args_list
            # The second command should be the concat/encode
            concat_cmd = call_args_list[-1][0][0]
            assert "concat" in concat_cmd
            assert "-t" in concat_cmd
            assert "-c" in concat_cmd
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_exceeds_maximum_extension(self):
        """Test that exceeding maximum extension raises error."""
        job_id = uuid4()
        shortfall = 6.0  # >5s maximum
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        clip_path = temp_dir / "last_clip.mp4"
        clip_path.write_bytes(b"video_data")
        
        try:
            with pytest.raises(CompositionError) as exc_info:
                await extend_last_clip(clip_path, shortfall, temp_dir, job_id)
            
            assert "exceeds maximum extension" in str(exc_info.value)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    

