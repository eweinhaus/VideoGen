"""
Unit tests for script generator.
"""

import pytest
from uuid import uuid4

from shared.models.audio import ClipBoundary, Lyric
from modules.scene_planner.script_generator import (
    generate_clip_scripts,
    _align_lyrics_to_clip
)


@pytest.fixture
def sample_clip_boundaries():
    """Sample clip boundaries."""
    return [
        ClipBoundary(start=0.0, end=5.0, duration=5.0),
        ClipBoundary(start=5.0, end=10.0, duration=5.0),
        ClipBoundary(start=10.0, end=15.0, duration=5.0),
    ]


@pytest.fixture
def sample_lyrics():
    """Sample lyrics with formatted text."""
    return [
        Lyric(text="Hello", timestamp=1.0, confidence=0.9, formatted_text="Hello world"),
        Lyric(text="world", timestamp=2.0, confidence=0.9, formatted_text="Hello world"),
        Lyric(text="test", timestamp=6.0, confidence=0.85, formatted_text="test"),
    ]


@pytest.fixture
def sample_llm_output():
    """Sample LLM output."""
    return {
        "clip_scripts": [
            {
                "clip_index": 0,
                "start": 0.0,
                "end": 5.0,
                "visual_description": "Test scene 1",
                "motion": "Static shot",
                "camera_angle": "Medium shot",
                "characters": ["protagonist"],
                "scenes": ["scene1"],
                "lyrics_context": None,
                "beat_intensity": "medium"
            },
            {
                "clip_index": 1,
                "start": 5.0,
                "end": 10.0,
                "visual_description": "Test scene 2",
                "motion": "Tracking shot",
                "camera_angle": "Wide shot",
                "characters": ["protagonist"],
                "scenes": ["scene2"],
                "lyrics_context": None,
                "beat_intensity": "high"
            },
            {
                "clip_index": 2,
                "start": 10.0,
                "end": 15.0,
                "visual_description": "Test scene 3",
                "motion": "Static shot",
                "camera_angle": "Close-up",
                "characters": [],
                "scenes": ["scene1"],
                "lyrics_context": None,
                "beat_intensity": "low"
            }
        ]
    }


def test_generate_clip_scripts(sample_llm_output, sample_clip_boundaries, sample_lyrics):
    """Test generating clip scripts from LLM output."""
    clip_scripts = generate_clip_scripts(
        llm_output=sample_llm_output,
        clip_boundaries=sample_clip_boundaries,
        lyrics=sample_lyrics
    )
    
    assert len(clip_scripts) == len(sample_clip_boundaries)
    assert clip_scripts[0].clip_index == 0
    assert clip_scripts[0].start == 0.0
    assert clip_scripts[0].end == 5.0
    assert clip_scripts[0].visual_description == "Test scene 1"


def test_align_lyrics_to_clip(sample_lyrics):
    """Test aligning lyrics to clip time range - builds from individual words with mutually exclusive ranges."""
    # Lyrics within range - builds from individual words within clip time range
    # Words at 1.0s and 2.0s are within [0.5, 2.5), result: "Hello world"
    lyrics = _align_lyrics_to_clip(0.5, 2.5, sample_lyrics, is_last_clip=False)
    assert lyrics == "Hello world"  # Built from individual words, not formatted_text
    
    # Test half-open interval - word at exactly 2.5s should be excluded (not last clip)
    # Word at 2.0s is included (< 2.5), but if there was a word at 2.5s it would be excluded
    lyrics = _align_lyrics_to_clip(0.5, 2.5, sample_lyrics, is_last_clip=False)
    assert lyrics == "Hello world"  # Only includes words < 2.5
    
    # No lyrics in range
    lyrics = _align_lyrics_to_clip(20.0, 25.0, sample_lyrics, is_last_clip=False)
    assert lyrics is None
    
    # Single lyric in range - builds from individual word within clip time range
    # Word at 6.0s is within [5.5, 7.0), result: "test"
    lyrics = _align_lyrics_to_clip(5.5, 7.0, sample_lyrics, is_last_clip=False)
    assert lyrics == "test"  # Built from individual word within clip range
    
    # Test last clip uses inclusive end boundary
    # Word at 6.0s is within [5.5, 7.0] (inclusive), result: "test"
    lyrics = _align_lyrics_to_clip(5.5, 7.0, sample_lyrics, is_last_clip=True)
    assert lyrics == "test"  # Last clip includes boundary words

