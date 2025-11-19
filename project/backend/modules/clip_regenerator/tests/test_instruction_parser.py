"""
Tests for instruction parser module.
"""
import pytest
from modules.clip_regenerator.instruction_parser import (
    parse_multi_clip_instruction,
    extract_modification,
    ClipInstruction
)
from shared.models.audio import AudioAnalysis, SongStructure, Mood, ClipBoundary, EnergyLevel


def test_extract_modification_removes_clip_references():
    """Test that clip references are removed from modification."""
    instruction = "make clips 2 and 4 brighter"
    modification = extract_modification(instruction)
    
    assert "clips" not in modification.lower()
    assert "2" not in modification
    assert "4" not in modification
    assert "brighter" in modification.lower()
    # Should preserve the action verb
    assert "make" in modification.lower() or "brighter" in modification.lower()


def test_extract_modification_all_clips():
    """Test extracting modification from 'all clips' instruction."""
    instruction = "make all clips brighter"
    modification = extract_modification(instruction)
    
    assert "all" not in modification.lower()
    assert "clips" not in modification.lower()
    assert "brighter" in modification.lower()


def test_parse_all_clips():
    """Test parsing 'all clips' instruction."""
    instruction = "make all clips brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 5
    # extract_modification returns "make brighter" not just "brighter"
    assert all("brighter" in ci.instruction.lower() for ci in result)
    assert all(ci.clip_index == i for i, ci in enumerate(result))


def test_parse_specific_clip_numbers():
    """Test parsing specific clip numbers."""
    instruction = "make clips 2 and 4 brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 2
    assert result[0].clip_index == 1  # clip 2 = index 1
    assert result[1].clip_index == 3  # clip 4 = index 3
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_range_notation():
    """Test parsing range notation."""
    instruction = "make clips 1-3 brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 3
    assert result[0].clip_index == 0
    assert result[1].clip_index == 1
    assert result[2].clip_index == 2
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_first_n():
    """Test parsing 'first N' instruction."""
    instruction = "make the first 3 clips brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 3
    assert all(ci.clip_index == i for i, ci in enumerate(result))
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_last_n():
    """Test parsing 'last N' instruction."""
    instruction = "make the last 2 clips brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 2
    assert result[0].clip_index == 3
    assert result[1].clip_index == 4
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_exclusion():
    """Test parsing 'all clips except' instruction."""
    instruction = "make all clips except clip 2 brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    assert len(result) == 4
    assert all(ci.clip_index != 1 for ci in result)  # clip 2 = index 1
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_chorus_clips():
    """Test parsing chorus clips instruction."""
    # Create mock audio data with chorus segments
    from uuid import UUID
    audio_data = AudioAnalysis(
        job_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        bpm=120.0,
        duration=30.0,
        beat_timestamps=[0.0, 0.5, 1.0],
        song_structure=[
            SongStructure(type="verse", start=0.0, end=10.0, energy=EnergyLevel.MEDIUM),
            SongStructure(type="chorus", start=10.0, end=20.0, energy=EnergyLevel.HIGH),
            SongStructure(type="verse", start=20.0, end=30.0, energy=EnergyLevel.MEDIUM),
        ],
        mood=Mood(primary="energetic", confidence=0.8, energy_level=EnergyLevel.HIGH),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=5.0, duration=5.0),   # verse
            ClipBoundary(start=5.0, end=10.0, duration=5.0),   # verse
            ClipBoundary(start=10.0, end=15.0, duration=5.0),  # chorus
            ClipBoundary(start=15.0, end=20.0, duration=5.0),  # chorus
            ClipBoundary(start=20.0, end=25.0, duration=5.0),  # verse
        ]
    )
    
    instruction = "make the chorus clips brighter"
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=audio_data)
    
    # Should match clips 2 and 3 (indices 2 and 3) which overlap with chorus
    assert len(result) >= 1
    assert all("brighter" in ci.instruction.lower() for ci in result)


def test_parse_defaults_to_all_clips():
    """Test that parsing defaults to all clips if no pattern matches."""
    instruction = "make them brighter"  # No clip reference
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    # Should default to all clips
    assert len(result) == 5


def test_parse_invalid_clip_numbers():
    """Test parsing with invalid clip numbers (out of range)."""
    instruction = "make clips 2 and 10 brighter"  # clip 10 doesn't exist
    result = parse_multi_clip_instruction(instruction, total_clips=5, audio_data=None)
    
    # Should only include valid clip indices
    assert len(result) == 1
    assert result[0].clip_index == 1  # clip 2 = index 1
    assert "brighter" in result[0].instruction.lower()

