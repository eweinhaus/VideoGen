"""
Tests for caching component.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis
from shared.models.audio import AudioAnalysis, Mood, EnergyLevel, SongStructure, SongStructureType, ClipBoundary


@pytest.fixture
def sample_audio_analysis(sample_job_id):
    """Sample AudioAnalysis object for testing."""
    return AudioAnalysis(
        job_id=sample_job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[0.5, 1.0, 1.5, 2.0],
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


@pytest.mark.asyncio
async def test_get_cached_analysis_cache_hit(sample_audio_analysis):
    """Test getting cached analysis when cache hit."""
    file_hash = "test_hash_12345678901234567890123456789012"
    
    # Mock Redis to return cached data
    with patch('modules.audio_parser.cache.redis_client') as mock_redis:
        cached_json = sample_audio_analysis.model_dump_json()
        mock_redis.get = AsyncMock(return_value=cached_json)
        
        result = await get_cached_analysis(file_hash)
        
        assert result is not None
        assert result.bpm == sample_audio_analysis.bpm
        assert result.job_id == sample_audio_analysis.job_id
        mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_cached_analysis_cache_miss():
    """Test getting cached analysis when cache miss."""
    file_hash = "test_hash_12345678901234567890123456789012"
    
    with patch('modules.audio_parser.cache.redis_client') as mock_redis:
        mock_redis.get = AsyncMock(return_value=None)
        
        result = await get_cached_analysis(file_hash)
        
        assert result is None
        mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_cached_analysis_cache_error():
    """Test that cache errors don't fail the request."""
    file_hash = "test_hash_12345678901234567890123456789012"
    
    with patch('modules.audio_parser.cache.redis_client') as mock_redis:
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        
        # Should return None, not raise exception
        result = await get_cached_analysis(file_hash)
        assert result is None


@pytest.mark.asyncio
async def test_store_cached_analysis(sample_audio_analysis):
    """Test storing analysis in cache."""
    file_hash = "test_hash_12345678901234567890123456789012"
    
    with patch('modules.audio_parser.cache.redis_client') as mock_redis:
        mock_redis.set = AsyncMock(return_value=True)
        
        await store_cached_analysis(file_hash, sample_audio_analysis, ttl=86400)
        
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "videogen:cache:audio_cache:" in call_args[0][0]
        assert call_args[1]['ttl'] == 86400


@pytest.mark.asyncio
async def test_store_cached_analysis_error_handling(sample_audio_analysis):
    """Test that cache write errors don't fail the request."""
    file_hash = "test_hash_12345678901234567890123456789012"
    
    with patch('modules.audio_parser.cache.redis_client') as mock_redis:
        mock_redis.set = AsyncMock(side_effect=Exception("Redis error"))
        
        # Should not raise exception
        await store_cached_analysis(file_hash, sample_audio_analysis, ttl=86400)
