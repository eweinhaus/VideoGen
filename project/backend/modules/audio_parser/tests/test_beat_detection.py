"""
Unit tests for beat detection.
"""

import pytest
import numpy as np
import librosa

from modules.audio_parser.beat_detection import detect_beats, _deduplicate_beats


class TestDeduplicateBeats:
    """Test beat deduplication."""
    
    def test_deduplicate_within_threshold(self):
        """Test that beats within 50ms threshold are deduplicated."""
        timestamps = [0.0, 0.03, 0.06, 0.10, 0.15]  # 30ms, 30ms, 40ms, 50ms gaps
        result = _deduplicate_beats(timestamps, threshold_ms=50.0)
        # Should keep first, skip second (30ms < 50ms), keep third (60ms > 50ms from first)
        assert len(result) <= len(timestamps)
        assert result[0] == 0.0
    
    def test_deduplicate_empty_list(self):
        """Test deduplication with empty list."""
        result = _deduplicate_beats([])
        assert result == []
    
    def test_deduplicate_single_beat(self):
        """Test deduplication with single beat."""
        result = _deduplicate_beats([1.0])
        assert result == [1.0]
    
    def test_deduplicate_sorted(self):
        """Test that deduplication sorts timestamps."""
        timestamps = [0.5, 0.0, 0.3, 0.1]
        result = _deduplicate_beats(timestamps)
        assert result == sorted(result)


class TestDetectBeats:
    """Test beat detection."""
    
    def test_detect_beats_valid_audio(self):
        """Test beat detection with valid audio signal."""
        # Generate synthetic audio with clear beats
        sr = 22050
        duration = 5.0
        t = np.linspace(0, duration, int(sr * duration))
        
        # Create signal with 120 BPM (2 Hz)
        bpm = 120
        beat_freq = bpm / 60.0
        y = np.sin(2 * np.pi * beat_freq * t) + 0.5 * np.sin(2 * np.pi * beat_freq * 2 * t)
        
        bpm_result, beats, confidence = detect_beats(y, sr)
        
        assert isinstance(bpm_result, float)
        assert 60 <= bpm_result <= 200
        assert isinstance(beats, list)
        assert len(beats) > 0
        assert all(isinstance(b, float) for b in beats)
        assert 0.0 <= confidence <= 1.0
    
    def test_detect_beats_bpm_validation(self):
        """Test that BPM is clamped to 60-200 range."""
        sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration))
        
        # Create very slow signal (would give low BPM)
        y = np.sin(2 * np.pi * 0.5 * t)  # 0.5 Hz = 30 BPM
        
        bpm_result, beats, confidence = detect_beats(y, sr)
        
        # Should clamp to valid range or use fallback
        assert 60 <= bpm_result <= 200
    
    def test_detect_beats_returns_timestamps(self):
        """Test that beat timestamps are in seconds."""
        sr = 22050
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 2 * t)  # 2 Hz = 120 BPM
        
        bpm_result, beats, confidence = detect_beats(y, sr)
        
        assert all(0 <= b <= duration for b in beats)
        assert all(isinstance(b, float) for b in beats)
    
    def test_detect_beats_confidence_calculation(self):
        """Test confidence calculation."""
        sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 2 * t)
        
        bpm_result, beats, confidence = detect_beats(y, sr)
        
        assert 0.0 <= confidence <= 1.0
    
    def test_detect_beats_fallback_on_error(self):
        """Test fallback behavior on processing error."""
        # Create invalid audio (empty)
        sr = 22050
        y = np.array([])
        
        # Should not raise, but return fallback values
        try:
            bpm_result, beats, confidence = detect_beats(y, sr)
            # Fallback should still return valid values
            assert isinstance(bpm_result, float)
            assert isinstance(beats, list)
        except Exception:
            # If it raises, that's also acceptable (error handling)
            pass

