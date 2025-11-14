"""
Tests for data models.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from uuid import UUID, uuid4
from shared.models import (
    Job,
    JobStage,
    JobCost,
    AudioAnalysis,
    SongStructure,
    Lyric,
    Mood,
    ClipBoundary,
    ScenePlan,
    Character,
    Scene,
    Style,
    ClipScript,
    Transition,
    ReferenceImage,
    ReferenceImages,
    ClipPrompt,
    ClipPrompts,
    Clip,
    Clips,
    VideoOutput
)


def test_job_model():
    """Test Job model validation."""
    job_id = uuid4()
    user_id = uuid4()
    
    job = Job(
        id=job_id,
        user_id=user_id,
        status="queued",
        audio_url="https://example.com/audio.mp3",
        user_prompt="Test prompt",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    assert job.id == job_id
    assert job.status == "queued"
    assert job.progress == 0
    assert job.total_cost == Decimal("0.00")


def test_job_model_progress_validation():
    """Test Job model progress validation."""
    job_id = uuid4()
    user_id = uuid4()
    
    # Valid progress
    job = Job(
        id=job_id,
        user_id=user_id,
        status="processing",
        audio_url="https://example.com/audio.mp3",
        user_prompt="Test",
        progress=50,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    assert job.progress == 50
    
    # Invalid progress (should be clamped or raise error)
    with pytest.raises(Exception):  # Pydantic validation error
        Job(
            id=job_id,
            user_id=user_id,
            status="processing",
            audio_url="https://example.com/audio.mp3",
            user_prompt="Test",
            progress=150,  # Invalid: > 100
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )


def test_audio_analysis_model():
    """Test AudioAnalysis model."""
    job_id = uuid4()
    
    analysis = AudioAnalysis(
        job_id=job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[0.0, 0.5, 1.0, 1.5],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=30.0, energy="low")
        ],
        lyrics=[
            Lyric(text="Test lyric", timestamp=10.0)
        ],
        mood=Mood(
            primary="energetic",
            energy_level="high",
            confidence=0.9
        ),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=4.0, duration=4.0)
        ]
    )
    
    assert analysis.job_id == job_id
    assert analysis.bpm == 120.0
    assert len(analysis.beat_timestamps) == 4


def test_models_serialize_to_json():
    """Test that models can serialize to JSON."""
    job_id = uuid4()
    user_id = uuid4()
    
    job = Job(
        id=job_id,
        user_id=user_id,
        status="completed",
        audio_url="https://example.com/audio.mp3",
        user_prompt="Test",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    json_data = job.model_dump_json()
    assert isinstance(json_data, str)
    assert str(job_id) in json_data


def test_models_deserialize_from_json():
    """Test that models can deserialize from JSON."""
    job_id = uuid4()
    user_id = uuid4()
    
    job_data = {
        "id": str(job_id),
        "user_id": str(user_id),
        "status": "queued",
        "audio_url": "https://example.com/audio.mp3",
        "user_prompt": "Test",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    job = Job.model_validate(job_data)
    assert job.id == job_id
    assert job.status == "queued"

