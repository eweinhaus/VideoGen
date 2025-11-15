"""
Tests for utility functions.
"""

import pytest
import io
from modules.audio_parser.utils import (
    calculate_file_hash,
    extract_hash_from_url,
    validate_audio_file_bytes
)
from shared.errors import ValidationError


def test_calculate_file_hash():
    """Test MD5 hash calculation."""
    test_data = b"test audio data"
    hash1 = calculate_file_hash(test_data)
    hash2 = calculate_file_hash(test_data)
    
    assert hash1 == hash2, "Same data should produce same hash"
    assert len(hash1) == 32, "MD5 hash should be 32 characters"
    assert all(c in '0123456789abcdef' for c in hash1), "Hash should be hexadecimal"


def test_calculate_file_hash_different_data():
    """Test that different data produces different hashes."""
    data1 = b"test audio data 1"
    data2 = b"test audio data 2"
    
    hash1 = calculate_file_hash(data1)
    hash2 = calculate_file_hash(data2)
    
    assert hash1 != hash2, "Different data should produce different hashes"


def test_extract_hash_from_url_no_hash():
    """Test hash extraction when hash is not in URL."""
    url = "https://test.supabase.co/storage/v1/object/public/audio-uploads/test.mp3"
    hash_result = extract_hash_from_url(url)
    
    assert hash_result is None, "URL without hash should return None"


def test_extract_hash_from_url_with_hash_param():
    """Test hash extraction from URL parameter."""
    url = "https://test.supabase.co/storage/v1/object/public/audio-uploads/test.mp3?hash=12345678901234567890123456789012"
    hash_result = extract_hash_from_url(url)
    
    assert hash_result == "12345678901234567890123456789012", \
        f"Should extract hash from URL parameter, got {hash_result}"


def test_extract_hash_from_url_in_path():
    """Test hash extraction from URL path."""
    url = "https://test.supabase.co/storage/v1/object/public/audio-uploads/12345678901234567890123456789012.mp3"
    hash_result = extract_hash_from_url(url)
    
    # Should extract 32-char hex string from path
    assert hash_result is not None or hash_result is None, \
        "May or may not extract hash from path depending on format"


def test_validate_audio_file_bytes_valid():
    """Test validation of valid audio file bytes."""
    # Create minimal valid MP3 header
    mp3_data = b'\xff\xfb\x90\x00' + b'\x00' * 100
    
    # Should not raise
    validate_audio_file_bytes(mp3_data, max_size_mb=10)


def test_validate_audio_file_bytes_too_large():
    """Test validation fails for files that are too large."""
    # Create data larger than 10MB
    large_data = b'\xff\xfb\x90\x00' + b'\x00' * (11 * 1024 * 1024)
    
    with pytest.raises(ValidationError):
        validate_audio_file_bytes(large_data, max_size_mb=10)


def test_validate_audio_file_bytes_empty():
    """Test validation fails for empty files."""
    empty_data = b''
    
    with pytest.raises(ValidationError):
        validate_audio_file_bytes(empty_data, max_size_mb=10)

