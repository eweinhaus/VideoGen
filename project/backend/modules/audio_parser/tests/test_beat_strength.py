"""
Tests for beat strength classification.
"""

import pytest
import numpy as np
from modules.audio_parser.beat_detection import classify_beat_strength


def test_beat_strength_normal():
    """Test beat strength with normal beat pattern."""
    beat_timestamps = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]  # 8 beats
    audio = np.random.randn(22050 * 4)  # 4 seconds
    sr = 22050
    bpm = 120.0
    
    result = classify_beat_strength(beat_timestamps, audio, sr, bpm)
    
    assert len(result) == len(beat_timestamps)
    assert all(s in ["downbeat", "upbeat"] for s in result)
    assert result[0] == "downbeat"
    assert result[2] == "downbeat"
    assert result[1] == "upbeat"
    assert result[3] == "upbeat"


def test_beat_strength_empty():
    """Test beat strength with empty beat list."""
    result = classify_beat_strength([], np.array([]), 22050, 120.0)
    
    assert result == []


def test_beat_strength_pattern():
    """Test that pattern repeats correctly (4/4 time)."""
    beat_timestamps = [i * 0.5 for i in range(16)]  # 16 beats
    audio = np.random.randn(22050 * 8)
    sr = 22050
    bpm = 120.0
    
    result = classify_beat_strength(beat_timestamps, audio, sr, bpm)
    
    # Pattern should repeat: downbeat, upbeat, downbeat, upbeat
    expected = ["downbeat", "upbeat", "downbeat", "upbeat"] * 4
    
    assert result == expected

