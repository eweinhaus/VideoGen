"""
Unit tests for director knowledge loader.
"""

import pytest
from pathlib import Path

from modules.scene_planner.director_knowledge import (
    get_director_knowledge,
    extract_relevant_knowledge
)


def test_get_director_knowledge():
    """Test loading director knowledge base."""
    knowledge = get_director_knowledge()
    
    assert isinstance(knowledge, str)
    assert len(knowledge) > 1000  # Should be substantial
    assert "Visual Pacing" in knowledge or "Visual pacing" in knowledge
    assert "Color Palette" in knowledge or "Color palette" in knowledge


def test_extract_relevant_knowledge():
    """Test extracting relevant knowledge based on mood/energy."""
    # Test energetic mood
    knowledge = extract_relevant_knowledge(
        mood="energetic",
        energy_level="high",
        bpm=140.0
    )
    
    assert isinstance(knowledge, str)
    assert len(knowledge) > 0
    
    # Test calm mood
    knowledge = extract_relevant_knowledge(
        mood="calm",
        energy_level="low",
        bpm=80.0
    )
    
    assert isinstance(knowledge, str)
    assert len(knowledge) > 0

