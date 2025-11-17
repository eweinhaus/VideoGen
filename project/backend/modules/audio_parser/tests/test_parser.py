"""
Integration tests for audio parser orchestration.
"""

import pytest
import numpy as np
import io
import soundfile as sf
from uuid import uuid4
from modules.audio_parser.parser import parse_audio
from shared.models.audio import AudioAnalysis


@pytest.fixture
def sample_audio_bytes_wav():
    """Generate a real WAV file in memory for testing."""
    # Create a simple audio signal
    sr = 22050
    duration = 5.0
    t = np.linspace(0, duration, int(sr * duration))
    audio = np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
    
    # Write to BytesIO as WAV
    buffer = io.BytesIO()
    sf.write(buffer, audio, sr, format='WAV')
    buffer.seek(0)
    return buffer.read()


@pytest.mark.asyncio
async def test_parse_audio_full_flow(sample_audio_bytes_wav, sample_job_id):
    """Test full parse_audio flow with real audio."""
    analysis = await parse_audio(sample_audio_bytes_wav, sample_job_id)
    
    assert isinstance(analysis, AudioAnalysis)
    assert analysis.job_id == sample_job_id
    assert analysis.bpm > 0
    assert 60 <= analysis.bpm <= 200
    assert analysis.duration > 0
    assert len(analysis.beat_timestamps) > 0
    assert len(analysis.song_structure) > 0
    # For short songs (<12s), we may have fewer than 3 clips
    assert len(analysis.clip_boundaries) >= 1
    assert analysis.mood is not None
    assert 0 <= analysis.mood.confidence <= 1


@pytest.mark.asyncio
async def test_parse_audio_metadata(sample_audio_bytes_wav, sample_job_id):
    """Test that metadata is populated correctly."""
    analysis = await parse_audio(sample_audio_bytes_wav, sample_job_id)
    
    assert "beat_detection_confidence" in analysis.metadata
    assert "structure_confidence" in analysis.metadata
    assert "mood_confidence" in analysis.metadata
    assert "lyrics_count" in analysis.metadata
    assert "fallbacks_used" in analysis.metadata
    assert isinstance(analysis.metadata["fallbacks_used"], list)


@pytest.mark.asyncio
async def test_parse_audio_clip_boundaries_valid(sample_audio_bytes_wav, sample_job_id):
    """Test that clip boundaries are valid."""
    analysis = await parse_audio(sample_audio_bytes_wav, sample_job_id)
    
    for boundary in analysis.clip_boundaries:
        assert boundary.start >= 0
        assert boundary.end > boundary.start
        assert 3.0 <= boundary.duration <= 7.0
        assert boundary.duration == boundary.end - boundary.start


@pytest.mark.asyncio
async def test_parse_audio_beat_timestamps_valid(sample_audio_bytes_wav, sample_job_id):
    """Test that beat timestamps are valid."""
    analysis = await parse_audio(sample_audio_bytes_wav, sample_job_id)
    
    assert len(analysis.beat_timestamps) > 0
    assert all(0 <= t <= analysis.duration for t in analysis.beat_timestamps)
    # Check timestamps are in ascending order
    if len(analysis.beat_timestamps) > 1:
        assert all(analysis.beat_timestamps[i] < analysis.beat_timestamps[i+1] 
                  for i in range(len(analysis.beat_timestamps) - 1))


@pytest.mark.asyncio
async def test_parse_audio_structure_valid(sample_audio_bytes_wav, sample_job_id):
    """Test that song structure is valid."""
    analysis = await parse_audio(sample_audio_bytes_wav, sample_job_id)
    
    assert len(analysis.song_structure) > 0
    for segment in analysis.song_structure:
        assert segment.start >= 0
        assert segment.end > segment.start
        assert segment.start < analysis.duration
        assert segment.end <= analysis.duration
