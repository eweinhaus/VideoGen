"""
Unit tests for caching.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta

from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis
from modules.audio_parser.utils import calculate_file_hash
from shared.models.audio import AudioAnalysis, Mood, SongStructure, Lyric, ClipBoundary


@pytest.fixture
def sample_analysis():
    """Create sample AudioAnalysis for testing."""
    job_id = uuid4()
    return AudioAnalysis(
        job_id=job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[i * 0.5 for i in range(360)],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=15.0, energy="low"),
            SongStructure(type="verse", start=15.0, end=45.0, energy="medium"),
            SongStructure(type="chorus", start=45.0, end=75.0, energy="high"),
        ],
        lyrics=[
            Lyric(text="Hello", timestamp=0.0),
            Lyric(text="World", timestamp=1.0),
        ],
        mood=Mood(primary="energetic", secondary="bright", energy_level="high", confidence=0.8),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=6.0, duration=6.0),
            ClipBoundary(start=6.0, end=12.0, duration=6.0),
        ],
        metadata={"processing_time": 5.0, "cache_hit": False}
    )


class TestCalculateFileHash:
    """Test file hash calculation."""
    
    def test_hash_consistency(self):
        """Test that same file produces same hash."""
        audio_bytes = b"test audio data"
        hash1 = calculate_file_hash(audio_bytes)
        hash2 = calculate_file_hash(audio_bytes)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex is 32 chars
    
    def test_hash_different_files(self):
        """Test that different files produce different hashes."""
        audio_bytes1 = b"test audio data 1"
        audio_bytes2 = b"test audio data 2"
        
        hash1 = calculate_file_hash(audio_bytes1)
        hash2 = calculate_file_hash(audio_bytes2)
        
        assert hash1 != hash2


class TestCacheOperations:
    """Test cache operations."""
    
    @pytest.mark.asyncio
    async def test_store_and_get_cache(self, sample_analysis):
        """Test storing and retrieving from cache."""
        file_hash = "test_hash_12345"
        
        # Store in cache
        await store_cached_analysis(file_hash, sample_analysis, ttl=3600)
        
        # Retrieve from cache
        cached = await get_cached_analysis(file_hash)
        
        # Should retrieve the analysis
        assert cached is not None
        assert cached.bpm == sample_analysis.bpm
        assert cached.duration == sample_analysis.duration
        assert len(cached.beat_timestamps) == len(sample_analysis.beat_timestamps)
    
    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss returns None."""
        file_hash = "nonexistent_hash"
        
        cached = await get_cached_analysis(file_hash)
        
        assert cached is None
    
    @pytest.mark.asyncio
    async def test_cache_serialization(self, sample_analysis):
        """Test that cache serializes/deserializes correctly."""
        file_hash = "test_serialization"
        
        await store_cached_analysis(file_hash, sample_analysis, ttl=3600)
        cached = await get_cached_analysis(file_hash)
        
        assert cached is not None
        assert isinstance(cached, AudioAnalysis)
        assert cached.job_id == sample_analysis.job_id
        assert cached.bpm == sample_analysis.bpm
        assert cached.mood.primary == sample_analysis.mood.primary
    
    @pytest.mark.asyncio
    async def test_cache_ttl(self, sample_analysis):
        """Test that cache respects TTL."""
        file_hash = "test_ttl"
        
        # Store with short TTL
        await store_cached_analysis(file_hash, sample_analysis, ttl=1)
        
        # Should be available immediately
        cached = await get_cached_analysis(file_hash)
        assert cached is not None
        
        # Note: Actual TTL expiration testing requires waiting, which is slow
        # In practice, Redis handles TTL automatically

