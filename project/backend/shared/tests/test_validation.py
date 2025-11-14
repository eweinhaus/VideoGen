"""
Tests for validation utilities.
"""

import pytest
import io
from shared.validation import (
    validate_audio_file,
    validate_prompt,
    validate_file_size
)
from shared.errors import ValidationError


def test_validate_audio_file_valid():
    """Test validation of valid audio file."""
    # Create a mock MP3 file (with MP3 signature)
    file_data = b"\xff\xfb\x90\x00" + b"\x00" * 1000  # MP3 frame sync + data
    file = io.BytesIO(file_data)
    file.name = "test.mp3"
    
    # Should not raise
    validate_audio_file(file, max_size_mb=10)


def test_validate_audio_file_too_large():
    """Test validation fails for file that's too large."""
    # Create a large file
    file_data = b"\xff\xfb\x90\x00" + b"\x00" * (11 * 1024 * 1024)  # > 10MB
    file = io.BytesIO(file_data)
    file.name = "test.mp3"
    
    with pytest.raises(ValidationError) as exc_info:
        validate_audio_file(file, max_size_mb=10)
    
    assert "exceeds maximum" in str(exc_info.value).lower()


def test_validate_audio_file_empty():
    """Test validation fails for empty file."""
    file = io.BytesIO(b"")
    
    with pytest.raises(ValidationError) as exc_info:
        validate_audio_file(file)
    
    assert "empty" in str(exc_info.value).lower()


def test_validate_prompt_valid():
    """Test validation of valid prompt."""
    prompt = "A" * 100  # 100 characters
    
    # Should not raise
    validate_prompt(prompt, min_length=50, max_length=500)


def test_validate_prompt_too_short():
    """Test validation fails for prompt that's too short."""
    prompt = "A" * 30  # 30 characters
    
    with pytest.raises(ValidationError) as exc_info:
        validate_prompt(prompt, min_length=50, max_length=500)
    
    assert "at least" in str(exc_info.value).lower()


def test_validate_prompt_too_long():
    """Test validation fails for prompt that's too long."""
    prompt = "A" * 600  # 600 characters
    
    with pytest.raises(ValidationError) as exc_info:
        validate_prompt(prompt, min_length=50, max_length=500)
    
    assert "at most" in str(exc_info.value).lower()


def test_validate_file_size_valid():
    """Test validation of valid file size."""
    file_size = 5 * 1024 * 1024  # 5MB
    max_size = 10 * 1024 * 1024  # 10MB
    
    # Should not raise
    validate_file_size(file_size, max_size)


def test_validate_file_size_too_large():
    """Test validation fails for file that's too large."""
    file_size = 15 * 1024 * 1024  # 15MB
    max_size = 10 * 1024 * 1024  # 10MB
    
    with pytest.raises(ValidationError) as exc_info:
        validate_file_size(file_size, max_size)
    
    assert "exceeds maximum" in str(exc_info.value).lower()


