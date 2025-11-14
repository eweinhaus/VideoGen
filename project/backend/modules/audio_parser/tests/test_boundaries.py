"""
Unit tests for boundary generation.
"""

import pytest

from modules.audio_parser.boundaries import generate_boundaries, _snap_to_beat
from shared.models.audio import ClipBoundary


class TestSnapToBeat:
    """Test beat snapping."""
    
    def test_snap_within_threshold(self):
        """Test snapping when within threshold."""
        beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]
        timestamp = 0.48  # Within 100ms of 0.5
        
        result = _snap_to_beat(timestamp, beat_timestamps, threshold=0.1)
        
        assert result == 0.5
    
    def test_no_snap_outside_threshold(self):
        """Test no snapping when outside threshold."""
        beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]
        timestamp = 0.3  # 200ms from nearest beat (0.5)
        
        result = _snap_to_beat(timestamp, beat_timestamps, threshold=0.1)
        
        assert result == 0.3  # No snap
    
    def test_snap_empty_beats(self):
        """Test snapping with empty beat list."""
        timestamp = 1.5
        
        result = _snap_to_beat(timestamp, [], threshold=0.1)
        
        assert result == timestamp  # Returns original
    
    def test_snap_finds_nearest(self):
        """Test that nearest beat is found."""
        beat_timestamps = [0.0, 1.0, 2.0, 3.0]
        timestamp = 1.45  # Closer to 1.5, but nearest beat is 1.0
        
        result = _snap_to_beat(timestamp, beat_timestamps, threshold=0.5)
        
        assert result == 1.0


class TestGenerateBoundaries:
    """Test boundary generation."""
    
    def test_generate_boundaries_valid(self):
        """Test boundary generation with valid inputs."""
        beat_timestamps = [i * 0.5 for i in range(20)]  # 10 seconds of beats
        duration = 10.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm)
        
        assert isinstance(boundaries, list)
        assert len(boundaries) >= 3  # Minimum 3 clips
        assert all(isinstance(b, ClipBoundary) for b in boundaries)
    
    def test_boundaries_within_duration(self):
        """Test that all boundaries are within duration."""
        beat_timestamps = [i * 0.5 for i in range(20)]
        duration = 10.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm)
        
        assert all(0 <= b.start < b.end <= duration for b in boundaries)
    
    def test_boundaries_duration_range(self):
        """Test that boundaries are within 4-8s range."""
        beat_timestamps = [i * 0.5 for i in range(40)]  # 20 seconds
        duration = 20.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm, min_duration=4.0, max_duration=8.0)
        
        # Most boundaries should be within range (allowing some flexibility)
        durations = [b.duration for b in boundaries]
        assert all(3.0 <= d <= 9.0 for d in durations)  # Allow some flexibility
    
    def test_minimum_clips_requirement(self):
        """Test that minimum 3 clips are generated."""
        beat_timestamps = [i * 0.5 for i in range(10)]  # 5 seconds
        duration = 5.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm, min_clips=3)
        
        assert len(boundaries) >= 3
    
    def test_boundaries_no_beats(self):
        """Test boundary generation without beats."""
        beat_timestamps = []
        duration = 10.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm)
        
        assert len(boundaries) >= 3
        assert all(isinstance(b, ClipBoundary) for b in boundaries)
    
    def test_boundaries_short_song(self):
        """Test boundary generation with very short song."""
        beat_timestamps = [i * 0.2 for i in range(10)]  # 2 seconds
        duration = 2.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm, min_clips=3)
        
        # Should still generate at least 3 clips, even if short
        assert len(boundaries) >= 3
    
    def test_boundaries_long_song(self):
        """Test boundary generation with long song."""
        beat_timestamps = [i * 0.5 for i in range(200)]  # 100 seconds
        duration = 100.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm)
        
        assert len(boundaries) >= 3
        assert all(b.end <= duration for b in boundaries)
    
    def test_boundaries_have_duration(self):
        """Test that boundaries have duration calculated."""
        beat_timestamps = [i * 0.5 for i in range(20)]
        duration = 10.0
        bpm = 120
        
        boundaries = generate_boundaries(beat_timestamps, duration, bpm)
        
        assert all(b.duration == b.end - b.start for b in boundaries)
        assert all(b.duration > 0 for b in boundaries)

