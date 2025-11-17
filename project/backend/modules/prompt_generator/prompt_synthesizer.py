"""
Prompt synthesis helpers for Module 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Literal, Dict, Any

from shared.logging import get_logger

logger = get_logger("prompt_generator")

# Enhanced negative prompt to prevent anatomy errors and quality issues
# Added specific anatomy constraints to prevent common issues like extra limbs, missing body parts
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low resolution, distorted faces, "
    "extra limbs, missing limbs, extra fingers, missing fingers, deformed hands, "
    "extra legs, extra arms, three legs, three arms, four legs, four arms, "
    "deformed anatomy, mutated body parts, asymmetric body, distorted proportions, "
    "malformed limbs, incorrect anatomy, unnatural body structure, "
    "text, watermark, logo, oversaturated, flickering, low quality, "
    "cartoon, illustration, duplicate subject"
)

HEX_NAME_LOOKUP = {
    "000000": "deep black",
    "FFFFFF": "pure white",
    "FF0000": "crimson red",
    "00FF00": "vivid green",
    "0000FF": "electric blue",
    "00FFFF": "neon cyan",
    "FF00FF": "neon magenta",
    "FFFF00": "vibrant yellow",
    "FFA500": "sunset orange",
    "800080": "royal purple",
    "4B0082": "indigo",
    "FFC0CB": "soft pink",
    "1ABC9C": "teal",
    "C0C0C0": "silver",
}


@dataclass
class ClipContext:
    """Normalized context for synthesizing a clip prompt."""

    clip_index: int
    visual_description: str
    motion: Optional[str]
    camera_angle: Optional[str]
    style_keywords: List[str]
    color_palette: List[str]
    mood: str
    lighting: str
    cinematography: str
    scene_reference_url: Optional[str]
    character_reference_urls: List[str]
    beat_intensity: Literal["low", "medium", "high"]
    duration: float
    scene_ids: List[str]
    character_ids: List[str]
    scene_descriptions: List[str]
    character_descriptions: List[str]
    primary_scene_id: Optional[str]
    lyrics_context: Optional[str] = None
    beat_metadata: Dict[str, Any] = field(default_factory=dict)

    # PHASE 2: Full style information from scene planner (not just keywords)
    visual_style_full: str = ""
    mood_full: str = ""
    lighting_full: str = ""
    cinematography_full: str = ""
    color_palette_full: List[str] = field(default_factory=list)

    # CHARACTER CONSISTENCY FIX: Character objects (not just descriptions)
    # This allows access to structured features for proper formatting
    characters: List[Any] = field(default_factory=list)  # List[Character] from shared.models.scene


def build_clip_prompt(context: ClipContext, include_comprehensive_style: bool = True) -> Tuple[str, str]:
    """
    Build deterministic prompt/negative prompt pair for a clip.

    Args:
        context: ClipContext with all prompt data
        include_comprehensive_style: If True, include comprehensive style block.
                                     If False, only include condensed style (for LLM optimization).
    """
    fragments: List[str] = []
    
    # When using character reference images, we need to strongly emphasize the scene from the prompt
    # and explicitly ignore the background from the character reference image
    using_character_ref = bool(context.character_reference_urls)
    
    # If using character reference, start with explicit scene instruction
    if using_character_ref:
        # Put scene description FIRST and make it very explicit
        if context.scene_descriptions:
            scene_desc = ', '.join(context.scene_descriptions)
            fragments.append(f"SCENE SETTING (ignore background from reference image): {scene_desc}")
        elif context.visual_description:
            fragments.append(f"SCENE SETTING (ignore background from reference image): {context.visual_description.strip()}")
        else:
            fragments.append("SCENE SETTING (ignore background from reference image): Wide shot of the main scene consistent with the overall style")
        
        # Add explicit instruction to ignore image background
        fragments.append("IMPORTANT: Use the scene description above, completely ignore any background or scene elements from the character reference image")
    
    # Core visual description
    description = context.visual_description.strip()
    if not description:
        description = "Wide shot of the main scene consistent with the overall style"
    if not using_character_ref:  # Only add if we didn't already add it above
        fragments.append(description)

    motion = context.motion.strip() if context.motion else ""
    if not motion:
        motion = _default_motion(context.beat_intensity)
    fragments.append(motion)

    camera = context.camera_angle.strip() if context.camera_angle else ""
    if not camera:
        camera = _default_camera(context.beat_intensity)
    fragments.append(f"Camera: {camera}")

    # Add character descriptions with anatomy constraints for human characters
    if context.character_descriptions:
        # Check if any human characters are present (basic heuristic: look for human-related terms)
        has_humans = any(
            word in ' '.join(context.character_descriptions).lower()
            for word in ['person', 'man', 'woman', 'human', 'boy', 'girl', 'child', 'adult', 'people']
        )

        char_desc = f"Characters: {', '.join(context.character_descriptions)}"

        # Add anatomy keywords if human characters are present
        if has_humans:
            char_desc += ", anatomically correct human, proper human anatomy, two arms, two legs"

        fragments.append(char_desc)

    if context.scene_descriptions and not using_character_ref:
        # Only add scene descriptions here if we didn't already add them at the start
        fragments.append(
            f"Scene context: {', '.join(context.scene_descriptions)}"
        )

    # NOTE: Lyrics are now appended AFTER LLM optimization (similar to character identity blocks)
    # to ensure they are not modified by the LLM and remain exactly as extracted from audio parser

    # PHASE 2: Conditionally include comprehensive style block
    # When include_comprehensive_style=False (for LLM optimization), use condensed style
    # When include_comprehensive_style=True (final prompts), use full structured style block
    if include_comprehensive_style:
        style_block = build_comprehensive_style_block(context)
        if style_block:
            # Insert comprehensive style block AFTER core description but BEFORE quality boosters
            # This gives it prominence without overwhelming the core visual description
            fragments.append(style_block)
        else:
            # Fallback to condensed style for backward compatibility (if no full style available)
            _add_condensed_style(fragments, context)
    else:
        # For LLM optimization: use condensed style (LLM will rewrite this naturally)
        _add_condensed_style(fragments, context)

    fragments.append("cinematic lighting, highly detailed, professional cinematography, 4K, 16:9 aspect ratio")

    reference_hint = _build_reference_hint(context)
    if reference_hint:
        fragments.append(reference_hint)
    
    # Add final reminder if using character reference
    if using_character_ref:
        fragments.append("REMINDER: Scene and background must come from the prompt description above, not from the character reference image")

    prompt = ", ".join(fragment for fragment in fragments if fragment)
    # Note: Removed word limit enforcement - more context is better for video generation
    # Character identity blocks and style blocks will be appended later
    # Final prompt can be up to 1000 words (validated in validator.py)

    return prompt, DEFAULT_NEGATIVE_PROMPT


def _add_condensed_style(fragments: List[str], context: ClipContext) -> None:
    """
    Add condensed style information to fragments (for LLM optimization input).

    This is used when we want the LLM to optimize the prompt naturally,
    but will append the comprehensive style block afterward.
    """
    if context.style_keywords:
        fragments.append(
            f"Style: {', '.join(context.style_keywords[:4])}"
        )

    color_phrase = summarize_color_palette(context.color_palette)
    if color_phrase:
        fragments.append(color_phrase)

    fragments.append(
        f"Mood: {context.mood}. Lighting: {context.lighting}. Cinematography: {context.cinematography}."
    )


def build_comprehensive_style_block(context: ClipContext) -> str:
    """
    Build comprehensive style block with full scene planner style information.

    PHASE 2: This provides the video generation model with complete artistic direction,
    including visual style, mood, lighting, cinematography, and color palette with hex codes.

    Args:
        context: ClipContext with full style fields

    Returns:
        Formatted multi-line style block
    """
    lines: List[str] = []

    # Visual Style
    if context.visual_style_full:
        lines.append(f"VISUAL STYLE: {context.visual_style_full}")

    # Mood (prefer full version, fallback to keyword version)
    if context.mood_full:
        lines.append(f"MOOD: {context.mood_full}")
    elif context.mood:
        lines.append(f"MOOD: {context.mood}")

    # Lighting (prefer full version, fallback to keyword version)
    if context.lighting_full:
        lines.append(f"LIGHTING: {context.lighting_full}")
    elif context.lighting:
        lines.append(f"LIGHTING: {context.lighting}")

    # Cinematography (prefer full version, fallback to keyword version)
    if context.cinematography_full:
        lines.append(f"CINEMATOGRAPHY: {context.cinematography_full}")
    elif context.cinematography:
        lines.append(f"CINEMATOGRAPHY: {context.cinematography}")

    # Color Palette with hex codes
    if context.color_palette_full:
        color_entries: List[str] = []
        for hex_code in context.color_palette_full:
            # Strip # if present
            hex_clean = hex_code.replace("#", "").upper()

            # Get color name from lookup or generate descriptive name
            color_name = HEX_NAME_LOOKUP.get(hex_clean, f"color_{hex_clean[:6]}")

            color_entries.append(f"#{hex_clean} ({color_name})")

        colors_str = ", ".join(color_entries)
        lines.append(f"COLOR PALETTE: {colors_str}")

    # Join with comma + space for prompt-friendly format (models handle this well)
    return ", ".join(lines)


def build_character_identity_block(context: ClipContext) -> str:
    """
    Build character identity block with immutable character descriptions.

    PHASE 1: Now formats from structured CharacterFeatures instead of pre-formatted text.
    PHASE 3: Properly separates multiple characters with clear labels and roles.

    This ensures identical character descriptions across all clips, preventing
    the LLM from modifying or paraphrasing character features.

    This is appended AFTER LLM optimization to ensure the model cannot rewrite
    or deviate from the precise character specifications.

    Args:
        context: ClipContext with Character objects (with structured features)

    Returns:
        Formatted character identity block with proper multi-character separation
    """
    # Try to use structured Character objects first
    if context.characters:
        return _build_identity_from_characters(context.characters)

    # Fallback: Use legacy character_descriptions if available
    if context.character_descriptions:
        return _build_identity_from_descriptions(context.character_descriptions)

    return ""


def _build_identity_from_characters(characters: List[Any]) -> str:
    """
    Build character identity block from structured Character objects.

    PHASE 1: Formats from CharacterFeatures (no pre-formatted text).
    PHASE 3: Proper multi-character formatting with labels and roles.

    Args:
        characters: List of Character objects with structured features

    Returns:
        Formatted character identity block
    """
    if not characters:
        return ""

    # Build individual character blocks
    character_blocks = []
    for char in characters:
        # Skip if no features available (fallback to description if needed)
        if not hasattr(char, 'features') or char.features is None:
            # Fallback to description field if features not available
            if hasattr(char, 'description') and char.description:
                character_blocks.append(char.description)
            continue

        # Get character name and role
        char_name = getattr(char, 'name', None) or getattr(char, 'id', 'Character')
        char_role = getattr(char, 'role', '')

        # Build character label with role
        if char_role and char_role != 'character':
            char_label = f"{char_name} ({char_role})"
        else:
            char_label = char_name

        # Format features (NO "FIXED CHARACTER IDENTITY:" header - that caused nesting)
        features = char.features
        char_block = f"""{char_label}:
Hair: {features.hair}
Face: {features.face}
Eyes: {features.eyes}
Clothing: {features.clothing}
Accessories: {features.accessories}
Build: {features.build}
Age: {features.age}"""

        character_blocks.append(char_block)

    if not character_blocks:
        return ""

    # PHASE 3: Proper multi-character formatting
    if len(character_blocks) == 1:
        # Single character
        identity_block = f"""CHARACTER IDENTITIES:

{character_blocks[0]}

CRITICAL: These are EXACT, IMMUTABLE features for ALL characters. Each character must maintain these precise features in every clip."""
    else:
        # Multiple characters - separate with double newlines
        characters_text = "\n\n".join(character_blocks)
        character_count = len(character_blocks)
        identity_block = f"""CHARACTER IDENTITIES:

{characters_text}

CRITICAL: These are EXACT, IMMUTABLE features for ALL {character_count} characters. Each character must maintain these precise features in every clip."""

    return identity_block


def _build_identity_from_descriptions(character_descriptions: List[str]) -> str:
    """
    DEPRECATED: Build character identity block from pre-formatted descriptions.

    This is a fallback for backward compatibility when Character objects
    don't have structured features yet.

    Args:
        character_descriptions: List of pre-formatted character description strings

    Returns:
        Formatted character identity block
    """
    if not character_descriptions:
        return ""

    # Join all character descriptions
    char_desc = ', '.join(character_descriptions)

    # Check if character description already has CRITICAL statement
    has_critical_statement = "CRITICAL:" in char_desc and "IMMUTABLE features" in char_desc

    if has_critical_statement:
        # Character description already includes CRITICAL statement, don't duplicate
        identity_block = f"CHARACTER IDENTITY: {char_desc}"
    else:
        # Add CRITICAL statement if not present in character description
        identity_block = (
            f"CHARACTER IDENTITY: {char_desc}. "
            "CRITICAL: These are EXACT, FIXED features - do not modify, reinterpret, "
            "or deviate from these specific details. This is the same character "
            "appearing in all video clips - maintain precise consistency with these "
            "physical descriptions."
        )

    return identity_block


def build_lyrics_block(context: ClipContext) -> str:
    """
    Build lyrics block with exact lyrics for this clip's time range.

    This ensures lyrics are appended AFTER LLM optimization, preserving the exact
    words spoken during this clip's time range as extracted by the audio parser.
    
    Similar to build_character_identity_block(), lyrics are appended after optimization
    to prevent the LLM from modifying or paraphrasing them.

    Args:
        context: ClipContext with lyrics_context

    Returns:
        Formatted lyrics block with exact lyrics for this clip, or empty string if none
    """
    if not context.lyrics_context:
        return ""

    # Lyrics are already filtered to clip's exact time range by scene planner
    # Format as a clear reference block
    lyrics_block = f"LYRICS REFERENCE: \"{context.lyrics_context.strip()}\""

    return lyrics_block


def summarize_color_palette(color_palette: List[str]) -> str:
    """Convert hex color palette into descriptive sentence."""
    if not color_palette:
        return ""

    names: List[str] = []
    for hex_code in color_palette[:3]:
        normalized = hex_code.replace("#", "").upper()
        names.append(HEX_NAME_LOOKUP.get(normalized, f"#{normalized}".lower()))

    if len(names) == 1:
        return f"Color palette features {names[0]}"
    if len(names) == 2:
        return f"Color palette blends {names[0]} and {names[1]}"
    return f"Color palette mixes {', '.join(names[:-1])}, and {names[-1]}"


def compute_word_count(prompt: str) -> int:
    """Return simple whitespace-based word count."""
    if not prompt:
        return 0
    return len(prompt.strip().split())


def _default_motion(beat_intensity: Literal["low", "medium", "high"]) -> str:
    mapping = {
        "high": "Dynamic tracking shot with energetic subject movement",
        "medium": "Smooth tracking shot maintaining steady pacing",
        "low": "Static camera with subtle, slow movement",
    }
    return mapping.get(beat_intensity, mapping["medium"])


def _default_camera(beat_intensity: Literal["low", "medium", "high"]) -> str:
    if beat_intensity == "high":
        return "Handheld medium shot with slight shake"
    if beat_intensity == "low":
        return "Wide static shot with gentle dolly"
    return "Medium wide shot with controlled motion"


def _build_reference_hint(context: ClipContext) -> str:
    hints: List[str] = []
    if context.scene_reference_url:
        hints.append("Match the look and composition of the established scene reference image")
    if context.character_reference_urls:
        # When using character reference images, focus on character/object appearance only
        # Ignore any scene/background in the character reference image - use the prompt's scene description instead
        # Make this very explicit since the model tends to use the image as first frame
        hints.append("CRITICAL: Character reference image is ONLY for character appearance - completely ignore all background, scene, setting, or environment from the character reference image. The scene must come entirely from the prompt description above.")
    return ", ".join(hints)


def _enforce_word_limit(prompt: str, limit: int) -> str:
    words = prompt.split()
    if len(words) <= limit:
        return prompt
    truncated = " ".join(words[:limit]) + "..."
    logger.debug(
        "Prompt truncated to enforce word limit",
        extra={"original_words": len(words), "limit": limit},
    )
    return truncated

