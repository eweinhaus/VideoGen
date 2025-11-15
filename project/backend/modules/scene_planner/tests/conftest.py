"""
Shared test fixtures for scene planner tests.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from shared.models.audio import AudioAnalysis, Mood, SongStructure, Lyric, ClipBoundary


@pytest.fixture
def job_id():
    """Generate test job ID."""
    return uuid4()


@pytest.fixture
def sample_user_prompt():
    """Sample user prompt matching PRD requirements (50-500 chars)."""
    return "cyberpunk city at night with neon lights, rain-slicked streets, lone figure walking"


@pytest.fixture
def sample_audio_analysis(job_id):
    """Create sample AudioAnalysis matching PRD format."""
    return AudioAnalysis(
        job_id=job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[i * 0.5 for i in range(360)],  # 180 seconds at 120 BPM
        song_structure=[
            SongStructure(type="intro", start=0.0, end=15.0, energy="low"),
            SongStructure(type="verse", start=15.0, end=45.0, energy="medium"),
            SongStructure(type="chorus", start=45.0, end=75.0, energy="high"),
            SongStructure(type="verse", start=75.0, end=105.0, energy="medium"),
            SongStructure(type="chorus", start=105.0, end=135.0, energy="high"),
            SongStructure(type="bridge", start=135.0, end=150.0, energy="medium"),
            SongStructure(type="outro", start=150.0, end=180.0, energy="low"),
        ],
        lyrics=[
            Lyric(text="I see the lights", timestamp=15.0),
            Lyric(text="shining bright", timestamp=16.0),
            Lyric(text="in the city", timestamp=17.0),
            Lyric(text="at night", timestamp=18.0),
        ],
        mood=Mood(
            primary="energetic",
            secondary="bright",
            energy_level="high",
            confidence=0.85
        ),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=6.0, duration=6.0),
            ClipBoundary(start=6.0, end=12.0, duration=6.0),
            ClipBoundary(start=12.0, end=18.0, duration=6.0),
            ClipBoundary(start=18.0, end=24.0, duration=6.0),
            ClipBoundary(start=24.0, end=30.0, duration=6.0),
        ],
        metadata={
            "processing_time": 45.2,
            "cache_hit": False
        }
    )


@pytest.fixture
def calm_audio_analysis(job_id):
    """Create calm mood AudioAnalysis for testing different moods."""
    return AudioAnalysis(
        job_id=job_id,
        bpm=75.0,  # Low BPM
        duration=120.0,
        beat_timestamps=[i * 0.8 for i in range(150)],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=20.0, energy="low"),
            SongStructure(type="verse", start=20.0, end=60.0, energy="low"),
            SongStructure(type="chorus", start=60.0, end=100.0, energy="medium"),
            SongStructure(type="outro", start=100.0, end=120.0, energy="low"),
        ],
        lyrics=[
            Lyric(text="Lonely walk", timestamp=20.0),
            Lyric(text="through empty streets", timestamp=21.0),
        ],
        mood=Mood(
            primary="calm",
            secondary=None,
            energy_level="low",
            confidence=0.9
        ),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=5.0, duration=5.0),
            ClipBoundary(start=5.0, end=10.0, duration=5.0),
            ClipBoundary(start=10.0, end=15.0, duration=5.0),
        ],
        metadata={"processing_time": 30.0, "cache_hit": False}
    )


@pytest.fixture
def sample_scene_plan_dict(job_id):
    """Sample ScenePlan dict matching PRD output format."""
    return {
        "job_id": str(job_id),
        "video_summary": "A lone figure walks through neon-lit streets at night, rain reflecting neon signs. The video captures the energy and mood of a cyberpunk cityscape.",
        "characters": [
            {
                "id": "protagonist",
                "description": "Young woman, 25-30, futuristic jacket, signature red jacket",
                "role": "main character"
            }
        ],
        "scenes": [
            {
                "id": "city_street",
                "description": "Rain-slicked cyberpunk street with neon signs, distant city lights",
                "time_of_day": "night"
            }
        ],
        "style": {
            "color_palette": ["#00FFFF", "#FF00FF", "#0000FF"],
            "visual_style": "Neo-noir cyberpunk with rain and neon",
            "mood": "Melancholic yet hopeful",
            "lighting": "High-contrast neon with deep shadows",
            "cinematography": "Handheld, slight shake, tracking shots"
        },
        "clip_scripts": [
            {
                "clip_index": 0,
                "start": 0.0,
                "end": 6.0,
                "visual_description": "Protagonist walks toward camera through rain-slicked cyberpunk street, neon signs reflecting in puddles",
                "motion": "Slow tracking shot following character",
                "camera_angle": "Medium wide shot, slightly low angle, eye level height",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": None,
                "beat_intensity": "medium"
            },
            {
                "clip_index": 1,
                "start": 6.0,
                "end": 12.0,
                "visual_description": "Character continues walking, camera tracks alongside",
                "motion": "Tracking shot, camera moves parallel to character",
                "camera_angle": "Medium shot, eye level",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": None,
                "beat_intensity": "high"
            },
            {
                "clip_index": 2,
                "start": 12.0,
                "end": 18.0,
                "visual_description": "Close-up of character's face, neon lights reflecting",
                "motion": "Static shot with slight push-in",
                "camera_angle": "Close-up, eye level",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": "I see the lights shining bright",
                "beat_intensity": "medium"
            },
            {
                "clip_index": 3,
                "start": 18.0,
                "end": 24.0,
                "visual_description": "Wide shot of street, character small in frame",
                "motion": "Slow pull-out",
                "camera_angle": "Wide shot, high angle",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": None,
                "beat_intensity": "low"
            },
            {
                "clip_index": 4,
                "start": 24.0,
                "end": 30.0,
                "visual_description": "Character walks away from camera into neon-lit distance",
                "motion": "Static shot, character moves away",
                "camera_angle": "Medium wide shot, eye level",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": None,
                "beat_intensity": "medium"
            }
        ],
        "transitions": [
            {
                "from_clip": 0,
                "to_clip": 1,
                "type": "crossfade",
                "duration": 0.5,
                "rationale": "Smooth transition for continuous motion"
            },
            {
                "from_clip": 1,
                "to_clip": 2,
                "type": "cut",
                "duration": 0.0,
                "rationale": "Hard cut on strong beat for high energy"
            },
            {
                "from_clip": 2,
                "to_clip": 3,
                "type": "crossfade",
                "duration": 0.5,
                "rationale": "Smooth transition for medium energy"
            },
            {
                "from_clip": 3,
                "to_clip": 4,
                "type": "fade",
                "duration": 0.5,
                "rationale": "Fade for low energy section"
            }
        ]
    }

