"""
Tests for style applier module.
"""
import pytest
from modules.clip_regenerator.style_applier import apply_style_to_prompt, StyleTransferOptions
from modules.clip_regenerator.style_analyzer import StyleKeywords


def test_apply_style_color_palette():
    """Test applying color palette style."""
    target_prompt = "A cityscape at night"
    style_keywords = StyleKeywords(
        color=["warm", "vibrant"],
        lighting=[],
        mood=[]
    )
    transfer_options = StyleTransferOptions(
        color_palette=True,
        lighting=False,
        mood=False
    )
    
    result = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    assert "warm" in result
    assert "vibrant" in result
    assert "aesthetic" in result


def test_apply_style_lighting():
    """Test applying lighting style."""
    target_prompt = "A cityscape"
    style_keywords = StyleKeywords(
        color=[],
        lighting=["bright", "dramatic"],
        mood=[]
    )
    transfer_options = StyleTransferOptions(
        color_palette=False,
        lighting=True,
        mood=False
    )
    
    result = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    assert "bright" in result
    assert "dramatic" in result


def test_apply_style_all_options():
    """Test applying all style options."""
    target_prompt = "A cityscape"
    style_keywords = StyleKeywords(
        color=["warm"],
        lighting=["bright"],
        mood=["energetic"]
    )
    transfer_options = StyleTransferOptions(
        color_palette=True,
        lighting=True,
        mood=True
    )
    
    result = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    assert "warm" in result
    assert "bright" in result
    assert "energetic" in result


def test_apply_style_no_keywords():
    """Test applying style when no keywords available."""
    target_prompt = "A cityscape"
    style_keywords = StyleKeywords(
        color=[],
        lighting=[],
        mood=[]
    )
    transfer_options = StyleTransferOptions()
    
    result = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    # Should return original prompt unchanged
    assert result == target_prompt


def test_apply_style_preserves_original():
    """Test that original prompt is preserved."""
    target_prompt = "A cityscape at night with neon lights"
    style_keywords = StyleKeywords(
        color=["warm"],
        lighting=[],
        mood=[]
    )
    transfer_options = StyleTransferOptions(color_palette=True)
    
    result = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    assert target_prompt in result

