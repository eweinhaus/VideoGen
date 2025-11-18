"""
Prompt synthesis for reference image generation.

Combines scene/character descriptions with style information to create SDXL prompts.
Enhanced with detailed character features similar to video generator prompts.
"""

from typing import Literal, Optional
from shared.models.scene import Style, Character, CharacterFeatures
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


def get_scene_variation_suffix(variation_index: int) -> str:
    """
    Get variation suffix to append to scene prompts for different camera angles.

    Args:
        variation_index: Index of the variation (0, 1, 2, etc.)

    Returns:
        Suffix string describing camera angle for this variation
    """
    variations = [
        "wide establishing shot, showing full environment, environmental view",
        "medium shot from different angle, alternative perspective",
        "close-up detail shot, focus on key elements, detailed view",
        "overhead view, bird's eye perspective, top-down angle",
        "low angle view, dramatic upward perspective, ground level shot",
    ]

    if variation_index < len(variations):
        return variations[variation_index]
    else:
        # Cycle through variations if we have more than 5
        return variations[variation_index % len(variations)]


def get_character_variation_suffix(variation_index: int) -> str:
    """
    Get variation suffix for character prompts with identity preservation.

    CRITICAL: All variations must show the SAME PERSON from different angles/poses.
    Each variation includes "SAME PERSON" emphasis to prevent identity drift.

    Args:
        variation_index: Index of the variation (0, 1, 2, 3, etc.)

    Returns:
        Suffix string describing camera angle/pose for this variation
    """
    if variation_index == 0:
        # Base variation: frontal portrait
        return "frontal portrait view, neutral expression, direct gaze, centered composition"
    elif variation_index == 1:
        # Variation 1: profile view
        return "SAME PERSON, profile view from left side, slight smile, side angle, EXACT SAME FEATURES"
    elif variation_index == 2:
        # Variation 2: three-quarter view
        return "SAME PERSON, three-quarter view, confident pose, slight angle, EXACT SAME FEATURES"
    elif variation_index == 3:
        # Variation 3: full body
        return "SAME PERSON, full body shot, natural standing pose, full figure visible, EXACT SAME FEATURES"
    elif variation_index == 4:
        # Variation 4: action pose
        return "SAME PERSON, dynamic action shot, in motion, natural movement, EXACT SAME FEATURES"
    else:
        # Cycle through variations if we have more than 5
        cycle_idx = (variation_index % 5)
        return get_character_variation_suffix(cycle_idx)


def get_variation_suffix(variation_index: int) -> str:
    """
    DEPRECATED: Use get_character_variation_suffix() instead for identity preservation.
    Kept for backward compatibility.
    """
    return get_character_variation_suffix(variation_index)


def build_character_features_block(character: Optional[Character]) -> str:
    """
    Build detailed character features block from structured CharacterFeatures.
    
    Similar to video generator's character identity block, but formatted for reference images.
    
    Args:
        character: Character object with structured features
        
    Returns:
        Formatted character features block, or empty string if no features available
    """
    if not character:
        return ""
    
    # Try structured features first
    if character.features:
        features = character.features
        char_name = character.name or character.id
        char_role = character.role or ""
        
        # Build character label
        if char_role and char_role != "character":
            char_label = f"{char_name} ({char_role})"
        else:
            char_label = char_name
        
        # Format features for reference image (more concise than video prompts)
        # Emphasize realism and photography for lifelike results
        # Note: Realism keywords are added at prompt start, not here to avoid redundancy
        features_block = (
            f"{char_label}: "
            f"Hair: {features.hair}. "
            f"Face: {features.face}. "
            f"Eyes: {features.eyes}. "
            f"Clothing: {features.clothing}. "
            f"Accessories: {features.accessories}. "
            f"Build: {features.build}. "
            f"Age: {features.age}. "
            f"Anatomically correct human, proper human anatomy, two arms, two legs, natural proportions"
        )
        return features_block
    
    # Fallback to description if available
    if character.description:
        # Check if description mentions human characters
        desc_lower = character.description.lower()
        has_humans = any(
            word in desc_lower
            for word in ['person', 'man', 'woman', 'human', 'boy', 'girl', 'child', 'adult', 'people']
        )
        
        if has_humans:
            return f"{character.description}, anatomically correct human, proper human anatomy, two arms, two legs"
        return character.description
    
    return ""


def synthesize_prompt(
    description: str,
    style: Style,
    image_type: Literal["scene", "character"],
    variation_index: int = 0,
    character: Optional[Character] = None
) -> str:
    """
    Synthesize prompt from description and style.
    Supports character variations for diversity.
    Enhanced with detailed character features similar to video generator prompts.

    Args:
        description: Scene or character description
        style: Style object from ScenePlan
        image_type: "scene" or "character"
        variation_index: Index of variation for character references (0 = base, 1+ = variations)
        character: Optional Character object with structured features (for enhanced character prompts)

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
    # FORCE photorealistic for character images (override scene plan style)
    if image_type == "character":
        visual_style = "photorealistic"  # Force realistic, ignore scene plan style
    else:
        visual_style = style.visual_style or "realistic"
    
    lighting = style.lighting or "natural"
    cinematography = style.cinematography or "standard"
    mood = getattr(style, 'mood', None) or "neutral"
    
    # Format color palette as space-separated hex codes
    if style.color_palette and len(style.color_palette) > 0:
        # Ensure all colors are valid hex codes
        color_palette_str = " ".join(
            color if color.startswith("#") else f"#{color}"
            for color in style.color_palette
        )
    else:
        color_palette_str = "#FFFFFF"  # Default white
    
    # Build prompt fragments
    fragments = []
    
    # For character images: START with strong realism keywords (order matters in SDXL)
    if image_type == "character":
        # Put realism FIRST to override any style tendencies
        fragments.append("photorealistic portrait photograph of a real person, hyperrealistic, lifelike human")
    
    # For character images, use enhanced character features if available
    if image_type == "character" and character:
        features_block = build_character_features_block(character)
        if features_block:
            # Use detailed features instead of simple description
            fragments.append(features_block)
        else:
            # Fallback to description
            fragments.append(description)
    else:
        # Scene images or characters without structured features
        fragments.append(description)

    # Add variation suffix for scene variations (different camera angles)
    if image_type == "scene" and variation_index >= 0:
        scene_variation_suffix = get_scene_variation_suffix(variation_index)
        fragments.append(scene_variation_suffix)

    # Add variation suffix for character variations (identity-preserving)
    if image_type == "character":
        variation_suffix = get_character_variation_suffix(variation_index)
        fragments.append(variation_suffix)
    
    # Add style information (for characters, this reinforces realism)
    if image_type == "character":
        # For characters: emphasize photography and realism
        style_fragments = [
            "professional portrait photography",
            "natural lighting, studio quality",
            f"mood: {mood}",
            f"{color_palette_str} color tones",
            "DSLR camera, 85mm lens, f/2.8 aperture, shallow depth of field",
            "natural skin texture, realistic skin pores, natural colors",
            "highly detailed, professional quality, 4K, sharp focus, crisp details"
        ]
    else:
        # For scenes: use scene plan style
        style_fragments = [
            f"in {visual_style} style",
            f"{visual_style} aesthetic",
            f"{color_palette_str} color scheme",
            f"mood: {mood}",
            f"lighting: {lighting}",
            f"cinematography: {cinematography}",
            "highly detailed, professional quality, 4K, sharp focus, crisp details"
        ]
    fragments.extend(style_fragments)
    
    # Join all fragments
    prompt = ", ".join(fragments)
    
    # Validate and truncate if too long (increased max_length for detailed prompts)
    try:
        prompt = validate_prompt(prompt, max_length=800)  # Increased from 500 to accommodate detailed features
    except ValidationError as e:
        logger.error(
            f"Prompt validation failed for {image_type}: {str(e)}",
            extra={"image_type": image_type, "error": str(e)}
        )
        raise

    return prompt


def get_object_variation_suffix(variation_index: int) -> str:
    """
    Get variation suffix for object prompts with different angles.

    Args:
        variation_index: Index of the variation (0, 1, 2, etc.)

    Returns:
        Suffix string describing camera angle/view for this variation
    """
    variations = [
        "primary view, front angle, centered composition",
        "alternate angle, side view, different perspective",
        "close-up detail shot, macro photography, focus on distinctive features",
        "overhead view, top-down angle, bird's eye perspective",
        "low angle view, dramatic upward perspective, ground level shot",
    ]

    if variation_index < len(variations):
        return variations[variation_index]
    else:
        # Cycle through variations if we have more than 5
        return variations[variation_index % len(variations)]


def synthesize_object_prompt(
    obj: 'Object',
    style: Style,
    variation_index: int = 0
) -> str:
    """
    Synthesize prompt for object reference images from ObjectFeatures.

    Args:
        obj: Object with structured ObjectFeatures
        style: Style object from ScenePlan
        variation_index: Index of variation (0 = base, 1+ = variations)

    Returns:
        Synthesized prompt string for product photography

    Raises:
        ValidationError: If object or style is invalid
    """
    if not obj or not obj.features:
        raise ValidationError("Object must have features")

    if not style:
        raise ValidationError("Style object is required")

    features = obj.features

    # Build prompt fragments for product photography
    fragments = []

    # Start with product photography keywords
    fragments.append("professional product photography")

    # Add object description with all features
    object_desc = (
        f"{obj.name}, "
        f"{features.object_type}, "
        f"color: {features.color}, "
        f"material: {features.material}, "
        f"distinctive features: {features.distinctive_features}, "
        f"size: {features.size}, "
        f"condition: {features.condition}"
    )
    fragments.append(object_desc)

    # Add variation suffix for different angles
    variation_suffix = get_object_variation_suffix(variation_index)
    fragments.append(variation_suffix)

    # Add style information (simplified for product photography)
    # Use color palette from style but adapt for product shots
    if style.color_palette and len(style.color_palette) > 0:
        color_palette_str = " ".join(
            color if color.startswith("#") else f"#{color}"
            for color in style.color_palette
        )
    else:
        color_palette_str = "#FFFFFF"

    style_fragments = [
        "neutral background, studio lighting",
        f"color tones: {color_palette_str}",
        "sharp focus on object, clean composition",
        "highly detailed, professional quality, 4K, crisp details"
    ]
    fragments.extend(style_fragments)

    # Join all fragments
    prompt = ", ".join(fragments)

    # Validate and truncate if too long
    try:
        prompt = validate_prompt(prompt, max_length=800)
    except ValidationError as e:
        logger.error(
            f"Object prompt validation failed for {obj.id}: {str(e)}",
            extra={"object_id": obj.id, "error": str(e)}
        )
        raise

    return prompt
