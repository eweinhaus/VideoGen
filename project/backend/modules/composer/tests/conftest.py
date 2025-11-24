"""
Pytest fixtures for composer tests.
"""
import pytest
import subprocess
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

from shared.models.video import Clips, Clip
from shared.models.scene import Transition


@pytest.fixture
def sample_job_id():
    """Create a sample job ID."""
    return uuid4()


@pytest.fixture
def sample_clip():
    """Create a sample clip for testing."""
    def _create_clip(clip_index: int, video_url: str = None, actual_duration: float = 5.0, target_duration: float = 5.0):
        return Clip(
            clip_index=clip_index,
            video_url=video_url or f"https://project.supabase.co/storage/v1/object/public/video-clips/clip{clip_index}.mp4",
            actual_duration=actual_duration,
            target_duration=target_duration,
            duration_diff=actual_duration - target_duration,
            status="success",
            cost=Decimal("0.10"),
            generation_time=10.0
        )
    return _create_clip


@pytest.fixture
def sample_clips(sample_clip):
    """Create sample clips collection."""
    def _create_clips(count: int = 3):
        return Clips(
            job_id=uuid4(),
            clips=[sample_clip(i) for i in range(count)],
            total_clips=count,
            successful_clips=count,
            failed_clips=0,
            total_cost=Decimal("0.30"),
            total_generation_time=30.0
        )
    return _create_clips


@pytest.fixture
def sample_transitions():
    """Create sample transitions."""
    return [
        Transition(
            from_clip=0,
            to_clip=1,
            type="cut",
            duration=0.0,
            rationale="Simple cut"
        ),
        Transition(
            from_clip=1,
            to_clip=2,
            type="cut",
            duration=0.0,
            rationale="Simple cut"
        )
    ]


def create_test_video(output_path: Path, duration: float = 1.0, width: int = 640, height: int = 480):
    """
    Create a minimal valid video file for testing.
    
    Args:
        output_path: Path to output video file
        duration: Duration in seconds (default: 1.0)
        width: Video width (default: 640)
        height: Video height (default: 480)
    """
    # Create a minimal valid video using FFmpeg
    # This generates a solid color video with no audio
    cmd = [
        'ffmpeg',
        '-f', 'lavfi',
        '-i', f'color=c=black:s={width}x{height}:d={duration}',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p',
        '-y',  # Overwrite if exists
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            # If FFmpeg fails, just create an empty file as fallback
            output_path.touch()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # FFmpeg not available or timeout - create empty file
        output_path.touch()


@pytest.fixture
def create_test_video_file():
    """Fixture that returns the create_test_video function."""
    return create_test_video

