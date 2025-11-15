"""
Integration tests for Audio Parser.

Tests component interactions and full parse_audio() flow.
Uses real audio file: Test_audio_file.mp3
"""
import pytest
import numpy as np
import librosa
import os
from pathlib import Path
from uuid import uuid4
from modules.audio_parser.parser import parse_audio
from modules.audio_parser.main import process_audio_analysis
from shared.models.audio import AudioAnalysis


@pytest.fixture
def test_audio_file_path():
    """Path to test audio file."""
    # Audio file is in the same directory as tests
    test_dir = Path(__file__).parent
    audio_file = test_dir / "Test_audio_file.mp3"
    if not audio_file.exists():
        pytest.skip(f"Test audio file not found: {audio_file}")
    return str(audio_file)


@pytest.fixture
def test_audio_bytes(test_audio_file_path):
    """Load test audio file as bytes."""
    with open(test_audio_file_path, 'rb') as f:
        return f.read()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_audio_full_flow_real_file(test_audio_bytes, sample_job_id):
    """Test full parse_audio flow with real audio file."""
    analysis = await parse_audio(test_audio_bytes, sample_job_id)
    
    # Verify AudioAnalysis object structure
    assert isinstance(analysis, AudioAnalysis)
    assert analysis.job_id == sample_job_id
    assert analysis.bpm >= 60 and analysis.bpm <= 200
    assert analysis.duration > 0
    assert len(analysis.beat_timestamps) > 0
    assert len(analysis.song_structure) > 0
    assert len(analysis.clip_boundaries) >= 1  # Minimum 1 clip
    assert analysis.mood.primary in ['energetic', 'calm', 'dark', 'bright']
    
    # Verify metadata
    assert 'beat_detection_confidence' in analysis.metadata
    assert 'fallbacks_used' in analysis.metadata
    assert 'structure_confidence' in analysis.metadata
    assert 'mood_confidence' in analysis.metadata
    
    # Verify processing completed successfully
    # processing_time may or may not be in metadata (optional)
    if 'processing_time' in analysis.metadata:
        assert analysis.metadata['processing_time'] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_audio_component_interaction(test_audio_bytes, sample_job_id):
    """Test that components interact correctly."""
    analysis = await parse_audio(test_audio_bytes, sample_job_id)
    
    # Verify beat detection feeds into boundaries
    assert len(analysis.beat_timestamps) > 0
    assert len(analysis.clip_boundaries) > 0
    
    # Verify structure feeds into mood
    assert len(analysis.song_structure) > 0
    assert analysis.mood.primary is not None
    
    # Verify boundaries use beat timestamps (aligned to beats)
    first_boundary = analysis.clip_boundaries[0]
    # First boundary should start near a beat timestamp (within 2 seconds tolerance)
    if len(analysis.beat_timestamps) > 0:
        nearest_beat = min(analysis.beat_timestamps, key=lambda x: abs(x - first_boundary.start))
        assert abs(nearest_beat - first_boundary.start) < 2.0  # Within 2 seconds


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_audio_metadata_collection(test_audio_bytes, sample_job_id):
    """Test that metadata is collected correctly."""
    analysis = await parse_audio(test_audio_bytes, sample_job_id)
    
    # Verify all metadata fields present
    assert 'beat_detection_confidence' in analysis.metadata
    assert isinstance(analysis.metadata['beat_detection_confidence'], (int, float))
    assert 0 <= analysis.metadata['beat_detection_confidence'] <= 1
    
    assert 'fallbacks_used' in analysis.metadata
    assert isinstance(analysis.metadata['fallbacks_used'], list)
    
    assert 'structure_confidence' in analysis.metadata
    assert 'mood_confidence' in analysis.metadata
    assert 'lyrics_count' in analysis.metadata


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_audio_performance(test_audio_bytes, sample_job_id):
    """Test that processing meets performance targets."""
    import time
    
    start_time = time.time()
    analysis = await parse_audio(test_audio_bytes, sample_job_id)
    elapsed = time.time() - start_time
    
    # Verify processing time is reasonable (target: <60s for 3min song)
    # Allow some buffer for test environment
    assert elapsed < 120, f"Processing took {elapsed:.2f}s, expected <120s"
    
    # Verify duration is reasonable
    assert analysis.duration > 0
    assert analysis.duration < 600  # Less than 10 minutes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_audio_fallback_scenarios(test_audio_bytes, sample_job_id):
    """Test that fallbacks work in full flow."""
    analysis = await parse_audio(test_audio_bytes, sample_job_id)
    
    # Verify fallbacks_used is a list
    fallbacks = analysis.metadata.get('fallbacks_used', [])
    assert isinstance(fallbacks, list)
    
    # Even with fallbacks, analysis should complete
    assert analysis.bpm > 0
    assert len(analysis.beat_timestamps) > 0
    assert len(analysis.song_structure) > 0
    assert len(analysis.clip_boundaries) >= 1
    
    # Verify all required fields are present regardless of fallbacks
    assert analysis.mood is not None
    assert analysis.mood.primary is not None
    assert isinstance(analysis.lyrics, list)  # May be empty (instrumental)

