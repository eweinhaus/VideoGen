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


def build_clip_prompt(context: ClipContext) -> Tuple[str, str]:
    """
    Build deterministic prompt/negative prompt pair for a clip.
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

    if context.lyrics_context:
        fragments.append(f"Lyrics reference: \"{context.lyrics_context.strip()}\"")

    if context.style_keywords:
        fragments.append(
            f"Style: {' ,'.join(context.style_keywords[:4])}"
        )

    color_phrase = summarize_color_palette(context.color_palette)
    if color_phrase:
        fragments.append(color_phrase)

    fragments.append(
        f"Mood: {context.mood}. Lighting: {context.lighting}. Cinematography: {context.cinematography}."
    )

    fragments.append("cinematic lighting, highly detailed, professional cinematography, 4K, 16:9 aspect ratio")

    reference_hint = _build_reference_hint(context)
    if reference_hint:
        fragments.append(reference_hint)
    
    # Add final reminder if using character reference
    if using_character_ref:
        fragments.append("REMINDER: Scene and background must come from the prompt description above, not from the character reference image")

    prompt = ", ".join(fragment for fragment in fragments if fragment)
    prompt = _enforce_word_limit(prompt, 200)

    return prompt, DEFAULT_NEGATIVE_PROMPT


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

