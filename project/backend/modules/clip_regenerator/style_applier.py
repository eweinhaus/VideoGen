"""
Style application for clip style transfer.

Applies style keywords to target prompts while preserving original composition.
"""
from typing import List
from pydantic import BaseModel, Field

from modules.clip_regenerator.style_analyzer import StyleKeywords

logger = None  # Will be initialized if needed


class StyleTransferOptions(BaseModel):
    """Options for style transfer."""
    
    color_palette: bool = Field(default=True, description="Transfer color palette")
    lighting: bool = Field(default=True, description="Transfer lighting style")
    mood: bool = Field(default=True, description="Transfer mood/atmosphere")
    camera_angle: bool = Field(default=False, description="Transfer camera angle (future)")
    motion: bool = Field(default=False, description="Transfer motion style (future)")
    preserve_characters: bool = Field(default=True, description="Preserve target clip's character references")


def apply_style_to_prompt(
    target_prompt: str,
    style_keywords: StyleKeywords,
    transfer_options: StyleTransferOptions
) -> str:
    """
    Apply style keywords to target prompt.
    
    Preserves original composition and subject.
    Only applies style elements specified in transfer_options.
    
    Args:
        target_prompt: Original target prompt to modify
        style_keywords: Style keywords extracted from source clip
        transfer_options: Options controlling which style elements to transfer
        
    Returns:
        Modified prompt with style keywords applied
    """
    style_additions = []
    
    if transfer_options.color_palette and style_keywords.color:
        style_additions.extend(style_keywords.color)
    
    if transfer_options.lighting and style_keywords.lighting:
        style_additions.extend(style_keywords.lighting)
    
    if transfer_options.mood and style_keywords.mood:
        style_additions.extend(style_keywords.mood)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_additions = []
    for item in style_additions:
        if item not in seen:
            seen.add(item)
            unique_additions.append(item)
    
    if unique_additions:
        style_text = ", ".join(unique_additions)
        return f"{target_prompt}, {style_text} aesthetic"
    
    # No style additions, return original prompt
    return target_prompt

