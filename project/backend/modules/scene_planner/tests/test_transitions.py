"""
Unit tests for transition planner.
"""

import pytest
from shared.models.audio import SongStructure
from shared.models.scene import ClipScript
from modules.scene_planner.transition_planner import (
    plan_transitions,
    _get_beat_intensity_at_time,
    _get_structure_context,
    _determine_transition
)


@pytest.fixture
def sample_clip_scripts():
    """Sample clip scripts."""
    return [
        ClipScript(
            clip_index=0,
            start=0.0,
            end=5.0,
            visual_description="Scene 1",
            motion="Static",
            camera_angle="Medium",
            characters=["protagonist"],
            scenes=["scene1"],
            lyrics_context=None,
            beat_intensity="low"
        ),
        ClipScript(
            clip_index=1,
            start=5.0,
            end=10.0,
            visual_description="Scene 2",
            motion="Tracking",
            camera_angle="Wide",
            characters=["protagonist"],
            scenes=["scene2"],
            lyrics_context=None,
            beat_intensity="high"
        ),
        ClipScript(
            clip_index=2,
            start=10.0,
            end=15.0,
            visual_description="Scene 3",
            motion="Static",
            camera_angle="Close-up",
            characters=[],
            scenes=["scene1"],
            lyrics_context=None,
            beat_intensity="medium"
        ),
    ]


@pytest.fixture
def sample_beat_timestamps():
    """Sample beat timestamps."""
    return [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]


@pytest.fixture
def sample_song_structure():
    """Sample song structure."""
    return [
        SongStructure(type="intro", start=0.0, end=5.0, energy="low"),
        SongStructure(type="verse", start=5.0, end=10.0, energy="medium"),
        SongStructure(type="chorus", start=10.0, end=15.0, energy="high"),
    ]


def test_plan_transitions(sample_clip_scripts, sample_beat_timestamps, sample_song_structure):
    """Test planning transitions between clips."""
    transitions = plan_transitions(
        clip_scripts=sample_clip_scripts,
        beat_timestamps=sample_beat_timestamps,
        song_structure=sample_song_structure
    )
    
    # Should have N-1 transitions for N clips
    assert len(transitions) == len(sample_clip_scripts) - 1
    assert transitions[0].from_clip == 0
    assert transitions[0].to_clip == 1
    assert transitions[0].type in ["cut", "crossfade", "fade"]


def test_get_beat_intensity_at_time(sample_beat_timestamps):
    """Test getting beat intensity at a specific time."""
    # High intensity (many beats in window)
    intensity = _get_beat_intensity_at_time(2.0, sample_beat_timestamps, window=0.5)
    assert intensity in ["low", "medium", "high"]
    
    # Low intensity (few beats)
    intensity = _get_beat_intensity_at_time(20.0, sample_beat_timestamps, window=0.5)
    assert intensity == "low"


def test_get_structure_context(sample_song_structure):
    """Test getting song structure context."""
    context = _get_structure_context(7.0, sample_song_structure)
    
    assert "current_segment" in context
    assert "next_segment" in context
    assert context["current_segment"].type == "verse"


def test_determine_transition(sample_clip_scripts):
    """Test determining transition type."""
    structure_context = {
        "current_segment": SongStructure(type="verse", start=0.0, end=5.0, energy="medium"),
        "next_segment": SongStructure(type="chorus", start=5.0, end=10.0, energy="high"),
        "transition_type": "verse_to_chorus"
    }
    
    transition_type, duration, rationale = _determine_transition(
        beat_intensity="high",
        structure_context=structure_context,
        current_clip=sample_clip_scripts[0],
        next_clip=sample_clip_scripts[1]
    )
    
    assert transition_type in ["cut", "crossfade", "fade"]
    assert duration >= 0.0
    assert isinstance(rationale, str)

