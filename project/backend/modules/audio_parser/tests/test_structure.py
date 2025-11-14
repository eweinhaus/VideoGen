"""
Unit tests for structure analysis.
"""

import pytest
import numpy as np
import librosa

from modules.audio_parser.structure_analysis import analyze_structure, _calculate_segment_energy
from shared.models.audio import SongStructure


class TestCalculateSegmentEnergy:
    """Test segment energy calculation."""
    
    def test_calculate_energy_valid_segment(self):
        """Test energy calculation for valid segment."""
        sr = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        y_segment = np.sin(2 * np.pi * 440 * t)  # A4 note
        
        energy = _calculate_segment_energy(y_segment, sr)
        
        assert 0.0 <= energy <= 1.0
        assert isinstance(energy, float)
    
    def test_calculate_energy_normalization(self):
        """Test that energy is normalized."""
        sr = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        
        # High energy segment
        y_high = np.sin(2 * np.pi * 440 * t) * 2.0
        energy_high = _calculate_segment_energy(y_high, sr)
        
        # Low energy segment
        y_low = np.sin(2 * np.pi * 440 * t) * 0.1
        energy_low = _calculate_segment_energy(y_low, sr)
        
        assert energy_high > energy_low
    
    def test_calculate_energy_with_max_values(self):
        """Test energy calculation with provided max values."""
        sr = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        y_segment = np.sin(2 * np.pi * 440 * t)
        
        energy = _calculate_segment_energy(y_segment, sr, max_rms=1.0, max_centroid=5000.0)
        
        assert 0.0 <= energy <= 1.0


class TestAnalyzeStructure:
    """Test structure analysis."""
    
    def test_analyze_structure_valid_audio(self):
        """Test structure analysis with valid audio."""
        sr = 22050
        duration = 30.0
        t = np.linspace(0, duration, int(sr * duration))
        
        # Create audio with varying energy (simulating structure)
        y = np.sin(2 * np.pi * 440 * t)
        # Add energy variation
        y[:int(sr * 10)] *= 0.5  # Lower energy intro
        y[int(sr * 10):int(sr * 20)] *= 1.5  # Higher energy chorus
        
        beat_timestamps = [i * 0.5 for i in range(int(duration / 0.5))]
        
        structure = analyze_structure(y, sr, beat_timestamps, duration)
        
        assert isinstance(structure, list)
        assert len(structure) > 0
        assert all(isinstance(s, SongStructure) for s in structure)
        assert all(0 <= s.start < s.end <= duration for s in structure)
    
    def test_analyze_structure_segment_types(self):
        """Test that segments have valid types."""
        sr = 22050
        duration = 20.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t)
        beat_timestamps = [i * 0.5 for i in range(int(duration / 0.5))]
        
        structure = analyze_structure(y, sr, beat_timestamps, duration)
        
        valid_types = {"intro", "verse", "chorus", "bridge", "outro"}
        assert all(s.type in valid_types for s in structure)
    
    def test_analyze_structure_energy_levels(self):
        """Test that segments have valid energy levels."""
        sr = 22050
        duration = 15.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t)
        beat_timestamps = [i * 0.5 for i in range(int(duration / 0.5))]
        
        structure = analyze_structure(y, sr, beat_timestamps, duration)
        
        valid_energies = {"low", "medium", "high"}
        assert all(s.energy in valid_energies for s in structure)
    
    def test_analyze_structure_fallback(self):
        """Test fallback behavior on error."""
        sr = 22050
        duration = 5.0
        y = np.array([])  # Empty audio
        beat_timestamps = []
        
        # Should return fallback single segment
        structure = analyze_structure(y, sr, beat_timestamps, duration)
        
        assert isinstance(structure, list)
        assert len(structure) >= 1
        assert structure[0].type == "verse"
        assert structure[0].energy == "medium"
    
    def test_analyze_structure_short_song(self):
        """Test structure analysis with very short song."""
        sr = 22050
        duration = 10.0  # Very short
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t)
        beat_timestamps = [i * 0.5 for i in range(int(duration / 0.5))]
        
        structure = analyze_structure(y, sr, beat_timestamps, duration)
        
        assert len(structure) > 0
        assert all(s.start < s.end for s in structure)

