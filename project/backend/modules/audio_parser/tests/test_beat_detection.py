"""
Tests for beat detection component.
"""

import pytest
import numpy as np
from modules.audio_parser.beat_detection import detect_beats


def test_beat_detection_normal(sample_audio_signal):
    """Test beat detection with normal audio."""
    audio, sr = sample_audio_signal
    
    bpm, beat_timestamps, confidence = detect_beats(audio, sr)
    
    assert 60 <= bpm <= 200, f"BPM {bpm} outside valid range"
    assert len(beat_timestamps) > 0, "No beats detected"
    assert 0 <= confidence <= 1, f"Confidence {confidence} outside valid range"
    assert all(0 <= t <= len(audio) / sr for t in beat_timestamps), "Beat timestamps out of range"


def test_beat_detection_fallback():
    """Test beat detection fallback with empty/invalid audio."""
    # Create very short audio that might trigger fallback
    sr = 22050
    audio = np.zeros(int(sr * 0.1))  # 0.1 seconds of silence
    
    bpm, beat_timestamps, confidence = detect_beats(audio, sr)
    
    # Fallback should still return valid results
    assert 60 <= bpm <= 200
    assert len(beat_timestamps) > 0
    assert 0 <= confidence <= 1


def test_beat_detection_bpm_clamping():
    """Test that BPM is clamped to valid range."""
    sr = 22050
    # Create audio that might produce extreme BPM values
    duration = 5.0
    audio = np.random.randn(int(sr * duration))
    
    bpm, beat_timestamps, confidence = detect_beats(audio, sr)
    
    assert 60 <= bpm <= 200, f"BPM {bpm} should be clamped to 60-200 range"


def test_beat_detection_timestamps_ordered(sample_audio_signal):
    """Test that beat timestamps are in ascending order."""
    audio, sr = sample_audio_signal
    
    bpm, beat_timestamps, confidence = detect_beats(audio, sr)
    
    if len(beat_timestamps) > 1:
        assert all(beat_timestamps[i] < beat_timestamps[i+1] 
                  for i in range(len(beat_timestamps) - 1)), \
            "Beat timestamps should be in ascending order"


def test_beat_detection_duration_match(sample_audio_signal):
    """Test that beat timestamps don't exceed audio duration."""
    audio, sr = sample_audio_signal
    duration = len(audio) / sr
    
    bpm, beat_timestamps, confidence = detect_beats(audio, sr)
    
    assert all(t <= duration for t in beat_timestamps), \
        "Beat timestamps should not exceed audio duration"
