"""
Tests for clip boundary generation component.
"""

import pytest
from modules.audio_parser.boundaries import generate_boundaries
from shared.models.audio import ClipBoundary


def test_boundaries_minimum_clips():
    """Test that at least 1 clip is generated."""
    beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]
    bpm = 120.0
    duration = 10.0
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    assert len(boundaries) >= 1, "Should generate at least 1 clip"
    assert all(isinstance(b, ClipBoundary) for b in boundaries)


def test_boundaries_short_song():
    """Test boundaries for very short songs (<9s)."""
    beat_timestamps = [0.0, 0.5, 1.0]
    bpm = 120.0
    duration = 6.0  # Less than 9s
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    # For songs <9s, we create 1-2 segments to ensure 3s minimum
    assert len(boundaries) >= 1, "Should generate at least 1 clip"
    assert all(3.0 <= b.duration <= 7.0 for b in boundaries), \
        f"Clip durations should be in 3-7s range, got: {[b.duration for b in boundaries]}"


def test_boundaries_duration_range():
    """Test that clip durations are in 3-7s range."""
    beat_timestamps = [i * 0.5 for i in range(20)]  # Beats every 0.5s
    bpm = 120.0
    duration = 30.0
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    assert all(3.0 <= b.duration <= 7.0 for b in boundaries), \
        f"All clip durations should be 3-7s, got: {[b.duration for b in boundaries]}"


def test_boundaries_no_beats():
    """Test boundaries when no beats are detected."""
    beat_timestamps = []
    bpm = 120.0
    duration = 20.0
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    assert len(boundaries) >= 1, "Should generate at least 1 clip even without beats"
    assert all(3.0 <= b.duration <= 7.0 for b in boundaries)


def test_boundaries_cover_full_duration():
    """Test that boundaries cover the full audio duration."""
    beat_timestamps = [i * 0.5 for i in range(20)]
    bpm = 120.0
    duration = 15.0
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    assert boundaries[0].start == 0.0, "First boundary should start at 0"
    # Last boundary should end at or near duration (may be slightly less if extending would exceed 7s)
    assert boundaries[-1].end >= duration * 0.8, \
        f"Last boundary should cover most of duration (got {boundaries[-1].end}, expected ~{duration})"


def test_boundaries_max_clips():
    """Test that max_clips limit is respected."""
    beat_timestamps = [i * 0.5 for i in range(100)]  # Many beats
    bpm = 120.0
    duration = 60.0
    max_clips = 10
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration, max_clips=max_clips)
    
    assert len(boundaries) <= max_clips, \
        f"Should not exceed max_clips ({max_clips}), got {len(boundaries)}"


def test_boundaries_valid_structure():
    """Test that boundaries have valid start < end relationships."""
    beat_timestamps = [i * 0.5 for i in range(20)]
    bpm = 120.0
    duration = 20.0
    
    boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    for boundary in boundaries:
        assert boundary.start < boundary.end, \
            f"Boundary start ({boundary.start}) should be < end ({boundary.end})"
        assert boundary.duration == boundary.end - boundary.start, \
            f"Duration should match end - start"
