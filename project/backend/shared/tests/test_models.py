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


def test_job_stage_model():
    """Test JobStage model validation."""
    job_id = uuid4()
    stage_id = uuid4()
    
    stage = JobStage(
        id=stage_id,
        job_id=job_id,
        stage_name="audio_parser",
        status="completed",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        duration_seconds=45,
        cost=Decimal("0.10"),
        metadata={"cache_hit": True}
    )
    
    assert stage.id == stage_id
    assert stage.job_id == job_id
    assert stage.stage_name == "audio_parser"
    assert stage.status == "completed"
    assert stage.cost == Decimal("0.10")


def test_job_cost_model():
    """Test JobCost model validation."""
    job_id = uuid4()
    cost_id = uuid4()
    
    cost = JobCost(
        id=cost_id,
        job_id=job_id,
        stage_name="video_generation",
        api_name="svd",
        cost=Decimal("0.06"),
        timestamp=datetime.utcnow()
    )
    
    assert cost.id == cost_id
    assert cost.job_id == job_id
    assert cost.api_name == "svd"
    assert cost.cost == Decimal("0.06")


def test_scene_plan_model():
    """Test ScenePlan model validation."""
    job_id = uuid4()
    
    plan = ScenePlan(
        job_id=job_id,
        video_summary="A cyberpunk music video",
        characters=[
            Character(id="protagonist", description="Young woman", role="main character")
        ],
        scenes=[
            Scene(id="city_street", description="Rain-slicked street", time_of_day="night")
        ],
        style=Style(
            color_palette=["#00FFFF", "#FF00FF"],
            visual_style="Cyberpunk",
            mood="Energetic",
            lighting="Neon",
            cinematography="Handheld"
        ),
        clip_scripts=[
            ClipScript(
                clip_index=0,
                start=0.0,
                end=5.0,
                visual_description="Character walks",
                motion="Tracking shot",
                camera_angle="Medium wide",
                characters=["protagonist"],
                scenes=["city_street"],
                beat_intensity="high"
            )
        ],
        transitions=[
            Transition(
                from_clip=0,
                to_clip=1,
                type="crossfade",
                duration=0.5,
                rationale="Smooth transition"
            )
        ]
    )
    
    assert plan.job_id == job_id
    assert len(plan.characters) == 1
    assert len(plan.scenes) == 1
    assert len(plan.clip_scripts) == 1
    assert plan.style.color_palette == ["#00FFFF", "#FF00FF"]


def test_reference_images_model():
    """Test ReferenceImages model validation."""
    job_id = uuid4()
    
    references = ReferenceImages(
        job_id=job_id,
        scene_references=[
            ReferenceImage(
                scene_id="city_street",
                character_id=None,
                image_url="https://storage.supabase.co/scene.png",
                prompt_used="Cyberpunk street",
                generation_time=8.5,
                cost=Decimal("0.005")
            )
        ],
        character_references=[
            ReferenceImage(
                scene_id=None,
                character_id="protagonist",
                image_url="https://storage.supabase.co/char.png",
                prompt_used="Young woman",
                generation_time=8.2,
                cost=Decimal("0.005")
            )
        ],
        total_references=2,
        total_generation_time=16.7,
        total_cost=Decimal("0.010"),
        status="success",
        metadata={"format": "PNG"}
    )
    
    assert references.job_id == job_id
    assert len(references.scene_references) == 1
    assert len(references.character_references) == 1
    assert references.total_references == 2
    assert references.status == "success"


def test_clip_prompts_model():
    """Test ClipPrompts model validation."""
    job_id = uuid4()
    
    prompts = ClipPrompts(
        job_id=job_id,
        clip_prompts=[
            ClipPrompt(
                clip_index=0,
                prompt="A cyberpunk scene",
                negative_prompt="blurry, low quality",
                duration=5.0,
                scene_reference_url="https://storage.supabase.co/scene.png",
                character_reference_urls=["https://storage.supabase.co/char.png"],
                metadata={"word_count": 45, "style_keywords": ["cyberpunk"]}
            )
        ],
        total_clips=1,
        generation_time=2.1
    )
    
    assert prompts.job_id == job_id
    assert len(prompts.clip_prompts) == 1
    assert prompts.total_clips == 1
    assert prompts.clip_prompts[0].clip_index == 0


def test_clips_model():
    """Test Clips model validation."""
    job_id = uuid4()
    
    clips = Clips(
        job_id=job_id,
        clips=[
            Clip(
                clip_index=0,
                video_url="https://storage.supabase.co/clip_0.mp4",
                actual_duration=5.4,
                target_duration=5.0,
                duration_diff=0.4,
                status="success",
                cost=Decimal("0.06"),
                retry_count=0,
                generation_time=45.2
            )
        ],
        total_clips=1,
        successful_clips=1,
        failed_clips=0,
        total_cost=Decimal("0.06"),
        total_generation_time=45.2
    )
    
    assert clips.job_id == job_id
    assert len(clips.clips) == 1
    assert clips.successful_clips == 1
    assert clips.failed_clips == 0
    assert clips.total_cost == Decimal("0.06")


def test_video_output_model():
    """Test VideoOutput model validation."""
    job_id = uuid4()
    
    output = VideoOutput(
        job_id=job_id,
        video_url="https://storage.supabase.co/final_video.mp4",
        duration=185.3,
        audio_duration=185.3,
        sync_drift=0.05,
        clips_used=6,
        clips_trimmed=4,
        clips_looped=2,
        transitions_applied=5,
        file_size_mb=45.2,
        composition_time=60.5,
        cost=Decimal("0.00"),
        status="success"
    )
    
    assert output.job_id == job_id
    assert output.duration == 185.3
    assert output.clips_used == 6
    assert output.status == "success"


def test_mood_confidence_validation():
    """Test that Mood confidence is between 0.0 and 1.0."""
    # Valid confidence
    mood = Mood(
        primary="energetic",
        energy_level="high",
        confidence=0.9
    )
    assert mood.confidence == 0.9
    
    # Invalid confidence > 1.0
    with pytest.raises(Exception):  # Pydantic validation error
        Mood(
            primary="energetic",
            energy_level="high",
            confidence=1.5
        )
    
    # Invalid confidence < 0.0
    with pytest.raises(Exception):  # Pydantic validation error
        Mood(
            primary="energetic",
            energy_level="high",
            confidence=-0.1
        )


def test_clip_retry_count_validation():
    """Test that Clip retry_count is non-negative."""
    job_id = uuid4()
    
    # Valid retry_count
    clip = Clip(
        clip_index=0,
        video_url="https://storage.supabase.co/clip_0.mp4",
        actual_duration=5.0,
        target_duration=5.0,
        duration_diff=0.0,
        status="success",
        cost=Decimal("0.06"),
        retry_count=2,
        generation_time=45.2
    )
    assert clip.retry_count == 2
    
    # Invalid retry_count < 0
    with pytest.raises(Exception):  # Pydantic validation error
        Clip(
            clip_index=0,
            video_url="https://storage.supabase.co/clip_0.mp4",
            actual_duration=5.0,
            target_duration=5.0,
            duration_diff=0.0,
            status="success",
            cost=Decimal("0.06"),
            retry_count=-1,
            generation_time=45.2
        )

