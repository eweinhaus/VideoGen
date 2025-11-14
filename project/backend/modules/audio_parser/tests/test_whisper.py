"""
Unit tests for Whisper API integration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4
from decimal import Decimal

from modules.audio_parser.whisper_client import extract_lyrics, _calculate_whisper_cost
from shared.models.audio import Lyric


class TestCalculateWhisperCost:
    """Test Whisper cost calculation."""
    
    def test_cost_calculation(self):
        """Test cost calculation for different durations."""
        # 1 minute = $0.006
        cost_1min = _calculate_whisper_cost(60.0)
        assert cost_1min == Decimal("0.006")
        
        # 2 minutes = $0.012
        cost_2min = _calculate_whisper_cost(120.0)
        assert cost_2min == Decimal("0.012")
        
        # 30 seconds = $0.003
        cost_30sec = _calculate_whisper_cost(30.0)
        assert cost_30sec == Decimal("0.003")
    
    def test_cost_zero_duration(self):
        """Test cost calculation for zero duration."""
        cost = _calculate_whisper_cost(0.0)
        assert cost == Decimal("0")


class TestExtractLyrics:
    """Test lyrics extraction."""
    
    @pytest.mark.asyncio
    @patch('modules.audio_parser.whisper_client._extract_lyrics_internal')
    @patch('modules.audio_parser.whisper_client.cost_tracker')
    async def test_extract_lyrics_success(self, mock_cost_tracker, mock_internal):
        """Test successful lyrics extraction."""
        from shared.models.audio import Lyric
        
        # Mock the internal function to return lyrics directly
        mock_internal.return_value = [
            Lyric(text="Hello", timestamp=0.0),
            Lyric(text="World", timestamp=1.0),
            Lyric(text="Test", timestamp=2.0),
        ]
        
        # Mock async cost tracker
        async def mock_track_cost(*args, **kwargs):
            return None
        mock_cost_tracker.track_cost = mock_track_cost
        
        audio_bytes = b"fake audio data"
        job_id = uuid4()
        duration = 60.0
        
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        
        assert len(lyrics) == 3
        assert all(isinstance(l, Lyric) for l in lyrics)
        assert lyrics[0].text == "Hello"
        assert lyrics[0].timestamp == 0.0
        assert lyrics[1].text == "World"
        assert lyrics[1].timestamp == 1.0
        
        # Verify internal function was called
        mock_internal.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.audio_parser.whisper_client.openai_client')
    async def test_extract_lyrics_empty_response(self, mock_openai_client):
        """Test handling of empty lyrics response."""
        # Mock empty response
        mock_response = Mock()
        mock_response.words = []
        mock_openai_client.audio.transcriptions.create.return_value = mock_response
        
        audio_bytes = b"fake audio data"
        job_id = uuid4()
        duration = 60.0
        
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        
        assert lyrics == []
    
    @pytest.mark.asyncio
    @patch('modules.audio_parser.whisper_client.openai_client')
    @patch('modules.audio_parser.whisper_client.cost_tracker')
    async def test_extract_lyrics_filters_empty_words(self, mock_cost_tracker, mock_openai_client):
        """Test that empty words are filtered out."""
        mock_response = Mock()
        mock_response.words = [
            {"word": "Hello", "start": 0.0},
            {"word": "", "start": 1.0},  # Empty word
            {"word": "   ", "start": 2.0},  # Whitespace only
            {"word": "World", "start": 3.0},
        ]
        mock_openai_client.audio.transcriptions.create.return_value = mock_response
        
        # Mock async cost tracker
        async def mock_track_cost(*args, **kwargs):
            return None
        mock_cost_tracker.track_cost = mock_track_cost
        
        audio_bytes = b"fake audio data"
        job_id = uuid4()
        duration = 60.0
        
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        
        # Should filter out empty words
        assert len(lyrics) == 2
        assert lyrics[0].text == "Hello"
        assert lyrics[1].text == "World"
    
    @pytest.mark.asyncio
    @patch('modules.audio_parser.whisper_client.openai_client')
    async def test_extract_lyrics_api_error(self, mock_openai_client):
        """Test handling of API errors."""
        # Mock API error
        mock_openai_client.audio.transcriptions.create.side_effect = Exception("API Error")
        
        audio_bytes = b"fake audio data"
        job_id = uuid4()
        duration = 60.0
        
        # Should return empty lyrics on error (after retries)
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        
        assert lyrics == []
    
    @pytest.mark.asyncio
    @patch('modules.audio_parser.whisper_client.openai_client')
    @patch('modules.audio_parser.whisper_client.cost_tracker')
    async def test_extract_lyrics_cost_tracking(self, mock_cost_tracker, mock_openai_client):
        """Test that cost is tracked correctly."""
        mock_response = Mock()
        mock_response.words = [{"word": "Test", "start": 0.0}]
        mock_openai_client.audio.transcriptions.create.return_value = mock_response
        
        audio_bytes = b"fake audio data"
        job_id = uuid4()
        duration = 60.0  # 1 minute
        
        await extract_lyrics(audio_bytes, job_id, duration)
        
        # Verify cost tracking
        mock_cost_tracker.track_cost.assert_called_once()
        call_args = mock_cost_tracker.track_cost.call_args
        assert call_args[1]["job_id"] == job_id
        assert call_args[1]["stage_name"] == "audio_analysis"
        assert call_args[1]["api_name"] == "whisper"
        assert call_args[1]["cost"] == Decimal("0.006")  # $0.006 per minute

