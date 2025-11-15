"""
Pytest configuration and fixtures for audio parser tests.
"""

import pytest
import numpy as np
import io
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

@pytest.fixture
def test_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test_service_key_1234567890123456789012345678901234567890")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678901234567890")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def sample_audio_signal():
    """Generate a sample audio signal for testing."""
    sr = 22050
    duration = 10.0  # 10 seconds
    t = np.linspace(0, duration, int(sr * duration))
    # Generate a simple tone with some variation
    audio = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 880 * t)
    return audio, sr


@pytest.fixture
def sample_audio_bytes():
    """Generate sample audio file bytes (simulated MP3)."""
    # Create a minimal valid MP3 header
    # This is a simplified version - real tests should use actual audio files
    mp3_header = b'\xff\xfb\x90\x00'  # MP3 frame sync
    # Add some dummy data
    audio_data = mp3_header + b'\x00' * 1000
    return audio_data


@pytest.fixture
def sample_job_id():
    """Sample job ID for testing."""
    return uuid4()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture
def mock_storage_client():
    """Mock storage client for testing."""
    mock_client = AsyncMock()
    mock_client.download_file = AsyncMock(return_value=b"fake_audio_data")
    return mock_client


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = AsyncMock()
    
    # Mock transcription response
    mock_word = MagicMock()
    mock_word.word = "test"
    mock_word.start = 0.0
    
    mock_response = MagicMock()
    mock_response.words = [mock_word]
    mock_response.text = "test"
    
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_cost_tracker():
    """Mock cost tracker for testing."""
    mock_tracker = AsyncMock()
    mock_tracker.check_budget = AsyncMock(return_value=True)
    mock_tracker.track_cost = AsyncMock(return_value=None)
    mock_tracker.get_total_cost = AsyncMock(return_value=0.0)
    return mock_tracker

