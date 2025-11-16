"""
Tests for beat subdivision detection.
"""

import pytest
import numpy as np
from modules.audio_parser.beat_detection import detect_beat_subdivisions


def test_subdivisions_normal():
    """Test subdivisions with normal beat pattern."""
    beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]  # 120 BPM (0.5s intervals)
    bpm = 120.0
    duration = 2.5
    
    result = detect_beat_subdivisions(beat_timestamps, bpm, duration)
    
    assert "eighth_notes" in result
    assert "sixteenth_notes" in result
    assert len(result["eighth_notes"]) > 0
    assert len(result["sixteenth_notes"]) > 0
    assert all(0 <= t <= duration for t in result["eighth_notes"])
    assert all(0 <= t <= duration for t in result["sixteenth_notes"])


def test_subdivisions_empty_beats():
    """Test subdivisions with empty beat list."""
    result = detect_beat_subdivisions([], 120.0, 10.0)
    
    assert result["eighth_notes"] == []
    assert result["sixteenth_notes"] == []


def test_subdivisions_sorted():
    """Test that subdivisions are sorted."""
    beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]
    bpm = 120.0
    duration = 2.5
    
    result = detect_beat_subdivisions(beat_timestamps, bpm, duration)
    
    assert result["eighth_notes"] == sorted(result["eighth_notes"])
    assert result["sixteenth_notes"] == sorted(result["sixteenth_notes"])

