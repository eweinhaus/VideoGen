"""
Tests for main entry point.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from modules.audio_parser.main import process_audio_analysis
from shared.models.audio import AudioAnalysis
from shared.errors import ValidationError, AudioAnalysisError


@pytest.mark.asyncio
async def test_process_audio_analysis_validation_error(sample_job_id):
    """Test that validation errors are raised correctly."""
    # Empty audio_url should raise ValidationError
    with pytest.raises(ValidationError):
        await process_audio_analysis(sample_job_id, "")


@pytest.mark.asyncio
async def test_process_audio_analysis_cache_hit(sample_job_id):
    """Test that cache hit returns cached analysis."""
    audio_url = "https://test.supabase.co/storage/v1/object/public/audio-uploads/test.mp3"
    
    # Create mock cached analysis
    from shared.models.audio import Mood, EnergyLevel, SongStructure, SongStructureType, ClipBoundary
    cached_analysis = AudioAnalysis(
        job_id=sample_job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[0.5, 1.0, 1.5],
        song_structure=[
            SongStructure(
                type=SongStructureType.INTRO,
                start=0.0,
                end=8.0,
                energy=EnergyLevel.LOW
            )
        ],
        lyrics=[],
        mood=Mood(
            primary="energetic",
            secondary=None,
            energy_level=EnergyLevel.HIGH,
            confidence=0.8
        ),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=5.0, duration=5.0),
            ClipBoundary(start=5.0, end=10.0, duration=5.0),
            ClipBoundary(start=10.0, end=15.0, duration=5.0)
        ]
    )
    
    with patch('modules.audio_parser.main.extract_hash_from_url', return_value="test_hash"), \
         patch('modules.audio_parser.main.get_cached_analysis', return_value=cached_analysis):
        
        result = await process_audio_analysis(sample_job_id, audio_url)
        
        assert result is not None
        assert result.job_id == sample_job_id
        assert result.metadata.get("cache_hit") is True


@pytest.mark.asyncio
async def test_process_audio_analysis_full_processing(sample_job_id):
    """Test full processing flow (cache miss)."""
    audio_url = "https://test.supabase.co/storage/v1/object/public/audio-uploads/test.mp3"
    audio_bytes = b'\xff\xfb\x90\x00' + b'\x00' * 1000
    
    with patch('modules.audio_parser.main.extract_hash_from_url', return_value=None), \
         patch('modules.audio_parser.main.get_cached_analysis', return_value=None), \
         patch('modules.audio_parser.main.download_audio_file', return_value=audio_bytes), \
         patch('modules.audio_parser.main.calculate_file_hash', return_value="test_hash"), \
         patch('modules.audio_parser.main.parse_audio') as mock_parse, \
         patch('modules.audio_parser.main.store_cached_analysis') as mock_store:
        
        # Create mock analysis result
        from shared.models.audio import Mood, EnergyLevel, SongStructure, SongStructureType, ClipBoundary
        mock_analysis = AudioAnalysis(
            job_id=sample_job_id,
            bpm=120.0,
            duration=5.0,
            beat_timestamps=[0.5, 1.0, 1.5],
            song_structure=[
                SongStructure(
                    type=SongStructureType.INTRO,
                    start=0.0,
                    end=5.0,
                    energy=EnergyLevel.LOW
                )
            ],
            lyrics=[],
            mood=Mood(
                primary="energetic",
                secondary=None,
                energy_level=EnergyLevel.HIGH,
                confidence=0.8
            ),
            clip_boundaries=[
                ClipBoundary(start=0.0, end=5.0, duration=5.0),
                ClipBoundary(start=5.0, end=10.0, duration=5.0),
                ClipBoundary(start=10.0, end=15.0, duration=5.0)
            ]
        )
        mock_parse.return_value = mock_analysis
        
        result = await process_audio_analysis(sample_job_id, audio_url)
        
        assert result is not None
        assert result.job_id == sample_job_id
        assert result.metadata.get("cache_hit") is False
        mock_parse.assert_called_once()
        mock_store.assert_called_once()

