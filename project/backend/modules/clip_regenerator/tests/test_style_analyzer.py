"""
Tests for style analyzer module.
"""
import pytest
from modules.clip_regenerator.style_analyzer import extract_style_keywords, StyleKeywords


def test_extract_style_keywords_warm_colors():
    """Test extracting warm color keywords."""
    prompt = "A warm sunset scene with golden light and orange hues"
    keywords = extract_style_keywords(prompt)
    
    assert "warm" in keywords.color
    assert len(keywords.color) > 0


def test_extract_style_keywords_cool_colors():
    """Test extracting cool color keywords."""
    prompt = "A cool blue ocean scene with cyan water and teal accents"
    keywords = extract_style_keywords(prompt)
    
    assert "cool" in keywords.color
    assert len(keywords.color) > 0


def test_extract_style_keywords_bright_lighting():
    """Test extracting bright lighting keywords."""
    prompt = "A bright, well-lit room with daylight streaming in"
    keywords = extract_style_keywords(prompt)
    
    assert "bright" in keywords.lighting
    assert len(keywords.lighting) > 0


def test_extract_style_keywords_dark_lighting():
    """Test extracting dark lighting keywords."""
    prompt = "A dark, shadowy alley with low light and dim atmosphere"
    keywords = extract_style_keywords(prompt)
    
    assert "dark" in keywords.lighting
    assert len(keywords.lighting) > 0


def test_extract_style_keywords_energetic_mood():
    """Test extracting energetic mood keywords."""
    prompt = "An energetic, dynamic scene with fast-paced action"
    keywords = extract_style_keywords(prompt)
    
    assert "energetic" in keywords.mood
    assert len(keywords.mood) > 0


def test_extract_style_keywords_calm_mood():
    """Test extracting calm mood keywords."""
    prompt = "A calm, peaceful scene with serene atmosphere"
    keywords = extract_style_keywords(prompt)
    
    assert "calm" in keywords.mood
    assert len(keywords.mood) > 0


def test_extract_style_keywords_multiple_categories():
    """Test extracting keywords from multiple categories."""
    prompt = "A warm, bright scene with energetic atmosphere"
    keywords = extract_style_keywords(prompt)
    
    assert len(keywords.color) > 0
    assert len(keywords.lighting) > 0
    assert len(keywords.mood) > 0


def test_extract_style_keywords_no_keywords():
    """Test extracting keywords when none are present."""
    prompt = "A scene with a person walking"
    keywords = extract_style_keywords(prompt)
    
    # Should return empty keywords (LLM fallback would be used)
    assert isinstance(keywords, StyleKeywords)
    assert len(keywords.color) == 0
    assert len(keywords.lighting) == 0
    assert len(keywords.mood) == 0

