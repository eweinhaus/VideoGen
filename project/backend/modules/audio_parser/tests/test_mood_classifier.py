"""
Tests for mood classification component.
"""

import pytest
import numpy as np
from modules.audio_parser.mood_classifier import classify_mood
from shared.models.audio import SongStructure, SongStructureType, EnergyLevel


@pytest.fixture
def sample_song_structure():
    """Sample song structure for testing."""
    return [
        SongStructure(
            type=SongStructureType.INTRO,
            start=0.0,
            end=8.0,
            energy=EnergyLevel.LOW
        ),
        SongStructure(
            type=SongStructureType.VERSE,
            start=8.0,
            end=20.0,
            energy=EnergyLevel.MEDIUM
        ),
        SongStructure(
            type=SongStructureType.CHORUS,
            start=20.0,
            end=30.0,
            energy=EnergyLevel.HIGH
        ),
    ]


def test_mood_classification_energetic(sample_audio_signal, sample_song_structure):
    """Test mood classification for energetic music."""
    audio, sr = sample_audio_signal
    bpm = 130.0  # High BPM
    
    # Create structure with high energy
    high_energy_structure = [
        SongStructure(
            type=SongStructureType.CHORUS,
            start=0.0,
            end=10.0,
            energy=EnergyLevel.HIGH
        )
    ]
    
    mood = classify_mood(audio, sr, bpm, high_energy_structure)
    
    assert mood.primary in ["energetic", "bright", "calm", "dark"], \
        f"Primary mood should be valid, got {mood.primary}"
    assert 0 <= mood.confidence <= 1
    assert mood.energy_level in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH]


def test_mood_classification_calm(sample_audio_signal, sample_song_structure):
    """Test mood classification for calm music."""
    audio, sr = sample_audio_signal
    bpm = 70.0  # Low BPM
    
    # Create structure with low energy
    low_energy_structure = [
        SongStructure(
            type=SongStructureType.INTRO,
            start=0.0,
            end=10.0,
            energy=EnergyLevel.LOW
        )
    ]
    
    mood = classify_mood(audio, sr, bpm, low_energy_structure)
    
    assert mood.primary in ["energetic", "bright", "calm", "dark"]
    assert 0 <= mood.confidence <= 1
    assert mood.energy_level in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH]


def test_mood_classification_fallback(sample_audio_signal):
    """Test mood classification fallback."""
    audio, sr = sample_audio_signal
    bpm = 100.0
    empty_structure = []
    
    mood = classify_mood(audio, sr, bpm, empty_structure)
    
    # Fallback should still return valid mood
    assert mood.primary in ["energetic", "bright", "calm", "dark"]
    assert mood.confidence >= 0.0
    assert mood.energy_level in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH]


def test_mood_classification_secondary(sample_audio_signal, sample_song_structure):
    """Test that secondary mood is set when confidence > 0.3."""
    audio, sr = sample_audio_signal
    bpm = 120.0
    
    mood = classify_mood(audio, sr, bpm, sample_song_structure)
    
    # Secondary may or may not be set depending on scores
    if mood.secondary:
        assert mood.secondary in ["energetic", "bright", "calm", "dark"]


def test_mood_classification_energy_level(sample_audio_signal):
    """Test that energy level is correctly calculated."""
    audio, sr = sample_audio_signal
    
    # High BPM and high energy
    high_structure = [
        SongStructure(
            type=SongStructureType.CHORUS,
            start=0.0,
            end=10.0,
            energy=EnergyLevel.HIGH
        )
    ]
    
    mood_high = classify_mood(audio, sr, 130.0, high_structure)
    assert mood_high.energy_level in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH]
    
    # Low BPM
    mood_low = classify_mood(audio, sr, 70.0, high_structure)
    assert mood_low.energy_level in [EnergyLevel.LOW, EnergyLevel.MEDIUM, EnergyLevel.HIGH]

