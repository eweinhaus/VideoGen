"""
Tests for beat intensity calculation per segment.
"""

import pytest
import numpy as np
from modules.audio_parser.structure_analysis import calculate_segment_beat_intensity
from shared.models.audio import SongStructure, SongStructureType, EnergyLevel


def test_intensity_high():
    """Test high intensity segment (high BPM + high energy)."""
    segment = SongStructure(
        type=SongStructureType.CHORUS,
        start=0.0,
        end=10.0,
        energy=EnergyLevel.HIGH
    )
    # High BPM: 2 beats per second = 120 BPM
    beat_timestamps = [i * 0.5 for i in range(20)]  # 20 beats in 10s = 120 BPM
    # High energy audio (loud)
    audio = np.random.randn(22050 * 10) * 0.8  # High amplitude
    sr = 22050
    
    result = calculate_segment_beat_intensity(segment, beat_timestamps, audio, sr)
    
    assert result in ["high", "medium"]  # Should be high or medium


def test_intensity_low():
    """Test low intensity segment (low BPM + low energy)."""
    segment = SongStructure(
        type=SongStructureType.INTRO,
        start=0.0,
        end=10.0,
        energy=EnergyLevel.LOW
    )
    # Low BPM: 1 beat per second = 60 BPM
    beat_timestamps = [i * 1.0 for i in range(10)]  # 10 beats in 10s = 60 BPM
    # Low energy audio (quiet)
    audio = np.random.randn(22050 * 10) * 0.1  # Low amplitude
    sr = 22050
    
    result = calculate_segment_beat_intensity(segment, beat_timestamps, audio, sr)
    
    assert result in ["low", "medium"]  # Should be low or medium


def test_intensity_no_beats():
    """Test intensity with no beats in segment."""
    segment = SongStructure(
        type=SongStructureType.VERSE,
        start=5.0,
        end=10.0,
        energy=EnergyLevel.MEDIUM
    )
    # Beats are outside segment
    beat_timestamps = [0.0, 0.5, 1.0, 11.0, 12.0]
    audio = np.random.randn(22050 * 15)
    sr = 22050
    
    result = calculate_segment_beat_intensity(segment, beat_timestamps, audio, sr)
    
    assert result == "low"  # No beats = low intensity

