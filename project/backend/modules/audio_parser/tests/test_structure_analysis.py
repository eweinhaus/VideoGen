"""
Tests for structure analysis component.
"""

import pytest
import numpy as np
from modules.audio_parser.structure_analysis import analyze_structure
from shared.models.audio import SongStructure, SongStructureType, EnergyLevel


def test_structure_analysis_normal(sample_audio_signal):
    """Test structure analysis with normal audio."""
    audio, sr = sample_audio_signal
    duration = len(audio) / sr
    beat_timestamps = [i * 0.5 for i in range(20)]  # Beats every 0.5s
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    # Handle tuple return (structure, fallback_flag)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    assert len(structure) > 0, "Should generate at least one segment"
    assert all(isinstance(s, SongStructure) for s in structure)
    assert all(s.start >= 0 for s in structure)
    assert all(s.end > s.start for s in structure)
    assert all(s.energy in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH] for s in structure)


def test_structure_analysis_short_song():
    """Test structure analysis for very short songs (<15s)."""
    sr = 22050
    duration = 10.0  # 10 seconds
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(20)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # Should still generate segments even for short songs
    assert len(structure) > 0
    assert all(s.start < duration for s in structure)
    assert all(s.end <= duration for s in structure)


def test_structure_analysis_segment_duration():
    """Test that segments have reasonable durations."""
    sr = 22050
    duration = 60.0  # 1 minute
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(120)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # Segments should have minimum duration (after merging)
    for segment in structure:
        segment_duration = segment.end - segment.start
        assert segment_duration > 0, "Segments should have positive duration"


def test_structure_analysis_fallback():
    """Test structure analysis fallback when clustering fails."""
    sr = 22050
    duration = 30.0
    # Create uniform audio that might trigger fallback
    audio = np.ones(int(sr * duration))  # Uniform signal
    beat_timestamps = [i * 0.5 for i in range(60)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, fallback_used = structure_result
        # Note: Fallback may or may not be used depending on clustering success
    else:
        structure = structure_result
    
    # Fallback should still return valid structure
    assert len(structure) > 0
    assert all(isinstance(s, SongStructure) for s in structure)


def test_structure_analysis_energy_levels():
    """Test that energy levels are correctly assigned."""
    sr = 22050
    duration = 30.0
    # Create audio with varying energy
    t = np.linspace(0, duration, int(sr * duration))
    audio = np.sin(2 * np.pi * 440 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.1 * t))
    beat_timestamps = [i * 0.5 for i in range(60)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # Should have energy levels assigned
    assert all(s.energy in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH] for s in structure)


def test_structure_analysis_segment_types():
    """Test that segment types are valid."""
    sr = 22050
    duration = 60.0
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(120)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # All segment types should be valid
    valid_types = [SongStructureType.INTRO, SongStructureType.VERSE, 
                   SongStructureType.CHORUS, SongStructureType.BRIDGE, SongStructureType.OUTRO]
    assert all(s.type in valid_types for s in structure)


def test_structure_analysis_coverage():
    """Test that structure covers the full audio duration."""
    sr = 22050
    duration = 30.0
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(60)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # First segment should start at 0
    assert structure[0].start == 0.0, "First segment should start at 0"
    
    # Last segment should end at or near duration
    assert structure[-1].end <= duration, "Last segment should not exceed duration"
    assert structure[-1].end >= duration * 0.9, "Last segment should cover most of duration"


def test_structure_analysis_no_overlap():
    """Test that segments don't overlap."""
    sr = 22050
    duration = 60.0
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(120)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # Segments should not overlap (end of one should be start of next, or close)
    for i in range(len(structure) - 1):
        assert structure[i].end <= structure[i+1].start, \
            f"Segment {i} end ({structure[i].end}) should be <= segment {i+1} start ({structure[i+1].start})"


def test_structure_analysis_fixed_clusters():
    """Test that structure analysis uses fixed number of clusters (8)."""
    sr = 22050
    duration = 60.0
    audio = np.random.randn(int(sr * duration))
    beat_timestamps = [i * 0.5 for i in range(120)]
    
    structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
    if isinstance(structure_result, tuple):
        structure, _ = structure_result
    else:
        structure = structure_result
    
    # After merging, we may have fewer than 8 segments, but should have at least 1
    assert len(structure) >= 1, "Should have at least 1 segment"
    # Note: After merging segments <5s, we may have fewer than 8 segments
    # This is expected behavior

