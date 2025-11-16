"""
Unit tests for transition_applier module.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from pathlib import Path
from uuid import uuid4

from modules.composer.transition_applier import apply_transitions
from shared.models.scene import Transition
from shared.errors import CompositionError, RetryableError


class TestApplyTransitions:
    """Tests for apply_transitions function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.transition_applier.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_apply_transitions_success(self, mock_run_ffmpeg):
        """Test successful transition application (concatenation)."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_composer")
        temp_dir.mkdir(exist_ok=True)
        
        # Create mock clip paths
        clip_paths = [
            temp_dir / "clip_0_normalized.mp4",
            temp_dir / "clip_1_normalized.mp4",
            temp_dir / "clip_2_normalized.mp4"
        ]
        for clip_path in clip_paths:
            clip_path.touch()  # Create empty files
        
        transitions = [
            Transition(from_clip=0, to_clip=1, type="cut", duration=0.0, rationale="Cut"),
            Transition(from_clip=1, to_clip=2, type="cut", duration=0.0, rationale="Cut")
        ]
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "clips_concatenated.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        output_path = await apply_transitions(clip_paths, transitions, temp_dir, job_id)
        
        # Verify output path
        assert output_path == temp_dir / "clips_concatenated.mp4"
        
        # Verify FFmpeg was called
        mock_run_ffmpeg.assert_called_once()
        call_args = mock_run_ffmpeg.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-f" in call_args
        assert "concat" in call_args
        assert "-safe" in call_args
        assert "0" in call_args
        
        # Verify concat file was created
        concat_file = temp_dir / "clips_concat.txt"
        assert concat_file.exists()
        
        # Verify concat file format (absolute paths)
        with open(concat_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3
            for line in lines:
                assert line.startswith("file '")
                assert line.endswith("'\n")
                # Verify absolute path
                path_str = line[6:-2]  # Remove "file '" and "'\n"
                assert Path(path_str).is_absolute()
    
    @pytest.mark.asyncio
    @patch('modules.composer.transition_applier.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_apply_transitions_six_clips(self, mock_run_ffmpeg):
        """Test concatenation with 6 clips."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_composer_6")
        temp_dir.mkdir(exist_ok=True)
        
        # Create mock clip paths
        clip_paths = [temp_dir / f"clip_{i}_normalized.mp4" for i in range(6)]
        for clip_path in clip_paths:
            clip_path.touch()
        
        transitions = []  # Empty transitions list (ignored in MVP)
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "clips_concatenated.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        output_path = await apply_transitions(clip_paths, transitions, temp_dir, job_id)
        
        assert output_path == temp_dir / "clips_concatenated.mp4"
        mock_run_ffmpeg.assert_called_once()
        
        # Verify concat file has 6 entries
        concat_file = temp_dir / "clips_concat.txt"
        with open(concat_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 6
    
    @pytest.mark.asyncio
    @patch('modules.composer.transition_applier.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_apply_transitions_ffmpeg_failure(self, mock_run_ffmpeg):
        """Test error handling when FFmpeg fails."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_composer_error")
        temp_dir.mkdir(exist_ok=True)
        
        clip_paths = [temp_dir / f"clip_{i}_normalized.mp4" for i in range(3)]
        for clip_path in clip_paths:
            clip_path.touch()
        
        transitions = []
        
        # Mock FFmpeg failure
        from shared.errors import RetryableError
        mock_run_ffmpeg.side_effect = RetryableError("FFmpeg command failed")
        
        with pytest.raises(CompositionError):
            await apply_transitions(clip_paths, transitions, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.transition_applier.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_apply_transitions_output_not_created(self, mock_run_ffmpeg):
        """Test error when output file is not created."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_composer_no_output")
        temp_dir.mkdir(exist_ok=True)
        
        clip_paths = [temp_dir / f"clip_{i}_normalized.mp4" for i in range(3)]
        for clip_path in clip_paths:
            clip_path.touch()
        
        transitions = []
        
        # FFmpeg succeeds but output file doesn't exist
        mock_run_ffmpeg.return_value = None
        
        with pytest.raises(CompositionError, match="Concatenated video not created"):
            await apply_transitions(clip_paths, transitions, temp_dir, job_id)
    
    @pytest.mark.asyncio
    @patch('modules.composer.transition_applier.run_ffmpeg_command', new_callable=AsyncMock)
    async def test_apply_transitions_ignores_transitions_in_mvp(self, mock_run_ffmpeg):
        """Test that transitions list is ignored in MVP (cuts only)."""
        job_id = uuid4()
        temp_dir = Path("/tmp/test_composer_ignore_transitions")
        temp_dir.mkdir(exist_ok=True)
        
        clip_paths = [temp_dir / f"clip_{i}_normalized.mp4" for i in range(3)]
        for clip_path in clip_paths:
            clip_path.touch()
        
        # Pass non-cut transitions (should be ignored in MVP)
        transitions = [
            Transition(from_clip=0, to_clip=1, type="crossfade", duration=1.0, rationale="Crossfade"),
            Transition(from_clip=1, to_clip=2, type="fade", duration=0.5, rationale="Fade")
        ]
        
        # Create output file after FFmpeg runs
        output_path = temp_dir / "clips_concatenated.mp4"
        
        async def create_output_file(*args, **kwargs):
            output_path.touch()
        
        mock_run_ffmpeg.side_effect = create_output_file
        
        # Should still work (simple concatenation)
        output_path = await apply_transitions(clip_paths, transitions, temp_dir, job_id)
        
        assert output_path == temp_dir / "clips_concatenated.mp4"
        mock_run_ffmpeg.assert_called_once()

