"""
Pytest fixtures for composer tests.
"""
import pytest
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

