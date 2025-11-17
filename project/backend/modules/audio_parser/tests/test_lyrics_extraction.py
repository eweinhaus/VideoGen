"""
Tests for lyrics extraction component.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from modules.audio_parser.lyrics_extraction import extract_lyrics
from shared.errors import BudgetExceededError


@pytest.fixture
def sample_audio_bytes():
    """Sample audio bytes for testing."""
    return b'\xff\xfb\x90\x00' + b'\x00' * 1000


@pytest.mark.asyncio
async def test_extract_lyrics_success(sample_audio_bytes, sample_job_id):
    """Test successful lyrics extraction."""
    # Mock OpenAI client
    mock_word = MagicMock()
    mock_word.word = "test"
    mock_word.start = 0.0
    
    mock_response = MagicMock()
    mock_response.words = [mock_word]
    mock_response.text = "test"
    
    # Create a mock file context manager
    mock_file_obj = MagicMock()
    mock_file_obj.__enter__ = MagicMock(return_value=mock_file_obj)
    mock_file_obj.__exit__ = MagicMock(return_value=None)
    mock_file_obj.read = MagicMock(return_value=sample_audio_bytes)
    
    with patch('modules.audio_parser.lyrics_extraction.AsyncOpenAI') as mock_openai_class, \
         patch('modules.audio_parser.lyrics_extraction.cost_tracker') as mock_cost_tracker, \
         patch('modules.audio_parser.lyrics_extraction.get_budget_limit', return_value=1000.0), \
         patch('tempfile.NamedTemporaryFile', return_value=mock_file_obj), \
         patch('builtins.open', create=True) as mock_open:
        
        mock_client = AsyncMock()
        mock_audio = MagicMock()
        mock_audio.transcriptions = MagicMock()
        mock_audio.transcriptions.create = AsyncMock(return_value=mock_response)
        mock_client.audio = mock_audio
        mock_openai_class.return_value = mock_client
        
        # Mock file operations
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=None)
        mock_open.return_value = mock_file
        
        mock_cost_tracker.check_budget = AsyncMock(return_value=True)
        mock_cost_tracker.track_cost = AsyncMock(return_value=None)
        
        lyrics = await extract_lyrics(sample_audio_bytes, sample_job_id, 60.0)
        
        assert len(lyrics) > 0
        assert lyrics[0].text == "test"
        assert lyrics[0].timestamp == 0.0
        # Verify new fields are present
        assert lyrics[0].confidence is not None
        assert 0.0 <= lyrics[0].confidence <= 1.0
        assert lyrics[0].formatted_text is not None
        assert isinstance(lyrics[0].formatted_text, str)
        mock_cost_tracker.check_budget.assert_called_once()
        mock_cost_tracker.track_cost.assert_called_once()


@pytest.mark.asyncio
async def test_extract_lyrics_budget_exceeded(sample_audio_bytes, sample_job_id):
    """Test lyrics extraction when budget is exceeded."""
    with patch('modules.audio_parser.lyrics_extraction.cost_tracker') as mock_cost_tracker, \
         patch('modules.audio_parser.lyrics_extraction.get_budget_limit', return_value=1000.0):
        
        mock_cost_tracker.check_budget = AsyncMock(return_value=False)
        
        with pytest.raises(BudgetExceededError):
            await extract_lyrics(sample_audio_bytes, sample_job_id, 60.0)


@pytest.mark.asyncio
async def test_extract_lyrics_fallback_on_error(sample_audio_bytes, sample_job_id):
    """Test that lyrics extraction falls back to empty array on error."""
    with patch('modules.audio_parser.lyrics_extraction.AsyncOpenAI') as mock_openai_class, \
         patch('modules.audio_parser.lyrics_extraction.cost_tracker') as mock_cost_tracker, \
         patch('modules.audio_parser.lyrics_extraction.get_budget_limit', return_value=1000.0), \
         patch('tempfile.NamedTemporaryFile') as mock_tempfile:
        
        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(side_effect=Exception("API error"))
        mock_openai_class.return_value = mock_client
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.mp3"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=None)
        mock_tempfile.return_value = mock_file
        
        mock_cost_tracker.check_budget = AsyncMock(return_value=True)
        
        # Should return empty lyrics array, not raise exception
        lyrics = await extract_lyrics(sample_audio_bytes, sample_job_id, 60.0)
        
        assert lyrics == []


@pytest.mark.asyncio
async def test_extract_lyrics_instrumental(sample_audio_bytes, sample_job_id):
    """Test lyrics extraction for instrumental tracks (empty response)."""
    mock_response = MagicMock()
    mock_response.words = []
    mock_response.text = ""
    
    with patch('modules.audio_parser.lyrics_extraction.AsyncOpenAI') as mock_openai_class, \
         patch('modules.audio_parser.lyrics_extraction.cost_tracker') as mock_cost_tracker, \
         patch('modules.audio_parser.lyrics_extraction.get_budget_limit', return_value=1000.0), \
         patch('tempfile.NamedTemporaryFile') as mock_tempfile:
        
        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
        mock_openai_class.return_value = mock_client
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.mp3"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=None)
        mock_tempfile.return_value = mock_file
        
        mock_cost_tracker.check_budget = AsyncMock(return_value=True)
        mock_cost_tracker.track_cost = AsyncMock(return_value=None)
        
        lyrics = await extract_lyrics(sample_audio_bytes, sample_job_id, 60.0)
        
        # Instrumental tracks should return empty lyrics (valid)
        assert lyrics == []

