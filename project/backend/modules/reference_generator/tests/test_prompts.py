"""
Unit tests for prompt synthesis.
"""

import pytest
from shared.models.scene import Style
from shared.errors import ValidationError
from modules.reference_generator.prompts import synthesize_prompt


def test_synthesize_prompt_scene():
    """Test prompt synthesis for scene images."""
    style = Style(
        color_palette=["#00FFFF", "#FF00FF", "#0000FF"],
        visual_style="Neo-noir cyberpunk",
        mood="dark",
        lighting="High-contrast neon with deep shadows",
        cinematography="Handheld tracking shots"
    )
    
    description = "Rain-slicked cyberpunk street with neon signs"
    prompt = synthesize_prompt(description, style, "scene")
    
    assert "Rain-slicked cyberpunk street with neon signs" in prompt
    assert "Neo-noir cyberpunk" in prompt
    assert "#00FFFF #FF00FF #0000FF" in prompt
    assert "High-contrast neon with deep shadows" in prompt
    assert "Handheld tracking shots" in prompt
    assert "highly detailed" in prompt
    assert "professional quality" in prompt
    assert "4K" in prompt


def test_synthesize_prompt_character():
    """Test prompt synthesis for character images."""
    style = Style(
        color_palette=["#FF5733", "#33FF57"],
        visual_style="realistic",
        mood="energetic",
        lighting="bright",
        cinematography="dynamic"
    )

    description = "Young woman, 25-30, futuristic jacket"
    prompt = synthesize_prompt(description, style, "character")

    assert "Young woman, 25-30, futuristic jacket" in prompt
    # Character images force photorealistic style and use "natural lighting"
    assert "photorealistic" in prompt
    assert "#FF5733 #33FF57" in prompt
    assert "mood: energetic" in prompt
    # Character images use portrait photography keywords instead of style's lighting/cinematography
    assert "natural lighting" in prompt or "studio quality" in prompt


def test_synthesize_prompt_color_palette_formatting():
    """Test that color palette is formatted as space-separated hex codes."""
    style = Style(
        color_palette=["00FFFF", "FF00FF", "0000FF"],  # Without # prefix
        visual_style="test",
        mood="test",
        lighting="test",
        cinematography="test"
    )
    
    prompt = synthesize_prompt("Test description", style, "scene")
    
    # Should add # prefix and space-separate
    assert "#00FFFF #FF00FF #0000FF" in prompt


def test_synthesize_prompt_truncation():
    """Test that prompts are truncated if too long."""
    style = Style(
        color_palette=["#FF0000"],
        visual_style="test",
        mood="test",
        lighting="test",
        cinematography="test"
    )

    # Create a very long description
    # Scene prompts have a 1500 character limit, character prompts have 2000
    long_description = "A" * 1600
    prompt = synthesize_prompt(long_description, style, "scene")

    # Should be truncated to 1500 for scenes
    assert len(prompt) <= 1500


def test_synthesize_prompt_empty_description():
    """Test that empty description raises ValidationError."""
    style = Style(
        color_palette=["#FF0000"],
        visual_style="test",
        mood="test",
        lighting="test",
        cinematography="test"
    )
    
    with pytest.raises(ValidationError):
        synthesize_prompt("", style, "scene")


def test_synthesize_prompt_missing_style_fields():
    """Test that missing style fields use defaults."""
    style = Style(
        color_palette=[],
        visual_style="",
        mood="",
        lighting="",
        cinematography=""
    )
    
    prompt = synthesize_prompt("Test description", style, "scene")
    
    # Should still generate a valid prompt with defaults
    assert "Test description" in prompt
    assert len(prompt) > 0
