"""
Prompt synthesis for reference image generation.

Combines scene/character descriptions with style information to create SDXL prompts.
"""

from typing import Literal
from shared.models.scene import Style
from shared.errors import ValidationError
from shared.logging import get_logger

logger = get_logger("reference_generator.prompts")


def validate_prompt(prompt: str, max_length: int = 500) -> str:
    """
    Validate and truncate prompt if too long.
    
    Args:
        prompt: Prompt to validate
        max_length: Maximum prompt length (default: 500)
        
    Returns:
        Validated and potentially truncated prompt
        
    Raises:
        ValidationError: If prompt is invalid
    """
    if not prompt or not prompt.strip():
        raise ValidationError("Prompt cannot be empty")
    
    if len(prompt) > max_length:
        logger.warning(
            f"Prompt truncated from {len(prompt)} to {max_length} characters",
            extra={"original_length": len(prompt)}
        )
        # Truncate intelligently (try to avoid cutting mid-word)
        # Find last space before max_length to avoid cutting mid-word
        truncated = prompt[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:  # Only if we're not losing too much
            truncated = truncated[:last_space] + "..."
        else:
            # Ensure we don't exceed max_length
            truncated = prompt[:max_length-3] + "..."
        # Final check to ensure we don't exceed max_length
        if len(truncated) > max_length:
            truncated = truncated[:max_length]
        return truncated
    
    return prompt


def synthesize_prompt(
    description: str,
    style: Style,
    image_type: Literal["scene", "character"]
) -> str:
    """
    Synthesize prompt from description and style.
    
    Args:
        description: Scene or character description
        style: Style object from ScenePlan
        image_type: "scene" or "character"
        
    Returns:
        Synthesized prompt string
        
    Raises:
        ValidationError: If style is missing required fields or prompt is invalid
    """
    if not description or not description.strip():
        raise ValidationError("Description cannot be empty")
    
    if not style:
        raise ValidationError("Style object is required")
    
    # Extract style components
    visual_style = style.visual_style or "realistic"
    lighting = style.lighting or "natural"
    cinematography = style.cinematography or "standard"
    
    # Format color palette as space-separated hex codes
    if style.color_palette and len(style.color_palette) > 0:
        # Ensure all colors are valid hex codes
        color_palette_str = " ".join(
            color if color.startswith("#") else f"#{color}"
            for color in style.color_palette
        )
    else:
        color_palette_str = "#FFFFFF"  # Default white
    
    # Build prompt template
    prompt = (
        f"{description}, {visual_style} aesthetic, {color_palette_str} color scheme, "
        f"{lighting}, {cinematography}, highly detailed, professional quality, 4K"
    )
    
    # Validate and truncate if too long (>500 characters)
    try:
        prompt = validate_prompt(prompt, max_length=500)
    except ValidationError as e:
        logger.error(
            f"Prompt validation failed for {image_type}: {str(e)}",
            extra={"image_type": image_type, "error": str(e)}
        )
        raise
    
    return prompt
