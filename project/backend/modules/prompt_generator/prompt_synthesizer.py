"""
Prompt synthesis helpers for Module 6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Literal, Dict, Any

from shared.logging import get_logger

logger = get_logger("prompt_generator")

# Enhanced negative prompt to prevent anatomy errors and quality issues
# Added specific anatomy constraints to prevent common issues like extra limbs, missing body parts
# Enhanced with face-specific constraints to prevent face warping and distortion
# Phase 1.4: Added video-specific negative terms for temporal stability
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low resolution, distorted faces, "
    "warped face, distorted face, blurred face, fuzzy facial features, "
    "face morphing, inconsistent face, face changing, different face, "
    "deformed facial features, asymmetric face, face distortion, "
    "face blur, low detail face, unclear face, hazy face, soft focus face, "
    "extra limbs, missing limbs, extra fingers, missing fingers, deformed hands, "
    "extra legs, extra arms, three legs, three arms, four legs, four arms, "
    "deformed anatomy, mutated body parts, asymmetric body, distorted proportions, "
    "malformed limbs, incorrect anatomy, unnatural body structure, "
    "text, watermark, logo, oversaturated, low quality, "
    "cartoon, illustration, duplicate subject, "
    "flickering, jittering, unstable camera, shaky footage, frame drops, "
    "morphing background, changing scenery mid-clip, inconsistent lighting, "
    "teleporting characters, position jumps, continuity errors, "
    "temporal artifacts, stuttering motion, warping objects"
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

    # PHASE 3: Object support for consistent prop tracking
    object_ids: List[str] = field(default_factory=list)
    object_descriptions: List[str] = field(default_factory=list)
    objects: List[Any] = field(default_factory=list)  # List[Object] from shared.models.scene
    object_reference_urls: List[str] = field(default_factory=list)

    # PHASE 2.1: Scene transition context
    transition_from_previous: Optional[str] = None
    is_first_clip: bool = False

    # PHASE 2.2: Time of day for lighting consistency
    time_of_day: Optional[str] = None

    # PHASE 2.3: Scene persistence notes
    scene_persistence_note: str = ""


def _build_transition_block(context: ClipContext) -> str:
    """
    Build transition instruction block based on clip position and transition type.

    PHASE 2.1: Provides transition context to help video generation model
    understand scene transitions and maintain consistency.

    Args:
        context: ClipContext with transition information

    Returns:
        Formatted transition instruction string
    """
    if context.is_first_clip:
        return "SCENE INTRODUCTION: Establish opening scene"

    if not context.transition_from_previous:
        return ""

    transition_type = context.transition_from_previous.lower()

    # Map transition types to instructions
    transition_instructions = {
        "cut": "TRANSITION: Direct cut, immediate scene change",
        "crossfade": "TRANSITION: Smooth crossfade from previous scene",
        "fade": "TRANSITION: Fade transition from previous scene",
        "match_action": "TRANSITION: Match action from previous clip, maintain motion continuity",
        "dissolve": "TRANSITION: Dissolve from previous scene",
        "wipe": "TRANSITION: Wipe transition from previous scene",
    }

    return transition_instructions.get(transition_type, f"TRANSITION: {transition_type} from previous scene")


def _is_face_heavy_shot(context: ClipContext) -> bool:
    """
    Detect if this is a face-heavy shot (close-up, portrait, etc.).

    Face-heavy shots benefit from face-first prompt ordering to ensure
    facial features are prioritized by the video generation model.

    Args:
        context: ClipContext with camera_angle information

    Returns:
        True if this is a face-heavy shot (close-up, extreme close-up, portrait)
    """
    if not context.camera_angle:
        return False

    camera = context.camera_angle.lower()

    # Keywords indicating face-heavy shots
    face_heavy_keywords = [
        'close-up',
        'close up',
        'closeup',
        'extreme close-up',
        'extreme close up',
        'extreme closeup',
        'ecu',
        'cu',
        'portrait',
        'head shot',
        'headshot',
        'face shot',
        'tight shot',
        'tight close-up'
    ]

    return any(keyword in camera for keyword in face_heavy_keywords)


def _enhance_camera_description(metadata: dict) -> str:
    """
    Enhance camera movement description with detailed specifications.

    PHASE 2.9: Maps camera movement keywords to detailed descriptions
    that help the video generation model understand desired camera motion.

    Args:
        metadata: Beat metadata dictionary that may contain camera_angle

    Returns:
        Enhanced camera description string, or empty string if no camera info
    """
    if not metadata or 'camera_angle' not in metadata:
        return ""

    camera_angle = str(metadata['camera_angle']).lower()

    # Map movement keywords to detailed descriptions
    movement_descriptions = {
        'tracking': "smooth tracking shot following subject movement, maintaining consistent framing",
        'pan': "smooth horizontal pan across scene, steady camera movement",
        'static': "static camera position, locked frame with no camera movement",
        'orbit': "orbital camera movement around subject, circular motion maintaining center focus",
        'push-in': "slow push-in/dolly forward towards subject, gradual approach",
        'pull-out': "slow pull-out/dolly back from subject, gradual retreat",
        'tilt': "smooth vertical tilt movement, camera angling up or down",
        'crane': "crane shot with vertical camera movement, elevated perspective change",
        'handheld': "handheld camera with natural subtle movement, organic camera shake",
    }

    # Check for movement keywords in camera_angle
    for keyword, description in movement_descriptions.items():
        if keyword in camera_angle:
            return f"CAMERA MOVEMENT: {description}"

    return ""


def build_clip_prompt(context: ClipContext, include_comprehensive_style: bool = True) -> Tuple[str, str]:
    """
    Build deterministic prompt/negative prompt pair for a clip.

    PHASE 2.8: Completely rewritten with conditional prompt ordering for lyrics prominence.
    # PHASE 2.6: Adds explicit singing/lip sync instructions when lyrics are present. (COMMENTED OUT)

    The ordering now adapts based on shot type and presence of lyrics:
    # - Face-heavy shots with lyrics: character_identity, lyrics_block first (for lip sync) (COMMENTED OUT)
    - Face-heavy shots without lyrics: character_identity first
    - Non-face-heavy with lyrics: lyrics after action
    - Standard: normal ordering

    Args:
        context: ClipContext with all prompt data
        include_comprehensive_style: If True, include comprehensive style block.
                                     If False, only include condensed style (for LLM optimization).
    """
    # Detect key conditions for conditional ordering
    is_face_heavy = _is_face_heavy_shot(context)
    has_lyrics = bool(context.lyrics_context and context.lyrics_context.strip())
    using_character_ref = bool(context.character_reference_urls)

    # Build all prompt components separately, then assemble based on conditions
    components = {}

    # 1. TRANSITION BLOCK (always first if present)
    transition_block = _build_transition_block(context)
    components['transition'] = transition_block if transition_block else None

    # 2. CHARACTER IDENTITY (for face-heavy shots with character refs)
    character_identity = None
    if is_face_heavy and using_character_ref:
        character_identity = "PRIORITY: Character facial features from reference image (face shape, skin tone, facial structure)"
    components['character_identity'] = character_identity

    # 3. SCENE SETTING (for character refs)
    scene_setting = None
    scene_instruction = None
    if using_character_ref:
        if context.scene_descriptions:
            scene_desc = ', '.join(context.scene_descriptions)
            scene_setting = f"SCENE SETTING (ignore background from reference image): {scene_desc}"
        elif context.visual_description:
            scene_setting = f"SCENE SETTING (ignore background from reference image): {context.visual_description.strip()}"
        else:
            scene_setting = "SCENE SETTING (ignore background from reference image): Wide shot of the main scene consistent with the overall style"
        scene_instruction = "IMPORTANT: Use the scene description above, completely ignore any background or scene elements from the character reference image"
    components['scene_setting'] = scene_setting
    components['scene_instruction'] = scene_instruction

    # 4. VISUAL DESCRIPTION (core action/scene)
    description = context.visual_description.strip()
    if not description:
        description = "Wide shot of the main scene consistent with the overall style"

    # PHASE 2.6: Add explicit singing instructions if lyrics are present
    # COMMENTED OUT: Lip sync instructions removed per user request
    # if has_lyrics:
    #     # Extract first 4 words from lyrics for mouth sync hint
    #     lyrics_words = context.lyrics_context.strip().split()[:4]
    #     lyrics_preview = " ".join(lyrics_words) if lyrics_words else context.lyrics_context.strip()[:30]
    #
    #     singing_instruction = f"Character singing lyrics with mouth movements matching words. Lips moving in sync with: {lyrics_preview}... Visible mouth articulation during singing."
    #     # Append singing instruction to visual description
    #     description = f"{description}. {singing_instruction}"

    # Only add visual description if we didn't already add it as scene_setting
    components['visual_description'] = description if not using_character_ref else None

    # 5. MOTION
    motion = context.motion.strip() if context.motion else ""
    if not motion:
        motion = _default_motion(context.beat_intensity)
    components['motion'] = motion

    # 6. CAMERA
    camera = context.camera_angle.strip() if context.camera_angle else ""
    if not camera:
        camera = _default_camera(context.beat_intensity)
    components['camera'] = f"Camera: {camera}"

    # 7. SCENE CONTEXT (only if not using character ref)
    scene_context = None
    if context.scene_descriptions and not using_character_ref:
        scene_context = f"Scene context: {', '.join(context.scene_descriptions)}"
    components['scene_context'] = scene_context

    # 8. LYRICS BLOCK (for inline lyrics in certain orderings)
    # PHASE 2.6: Inline lyrics with singing context
    # COMMENTED OUT: Removed "SINGING:" label per user request (lip sync removal)
    lyrics_inline = None
    if has_lyrics:
        lyrics_inline = f"\"{context.lyrics_context.strip()}\""
    components['lyrics_inline'] = lyrics_inline

    # 9. SCENE PERSISTENCE NOTE
    components['persistence_note'] = context.scene_persistence_note if context.scene_persistence_note else None

    # 10. STYLE BLOCK
    if include_comprehensive_style:
        style_block = build_comprehensive_style_block(context)
        if not style_block:
            # Fallback to condensed style
            style_fragments = []
            _add_condensed_style(style_fragments, context)
            style_block = ", ".join(style_fragments)
    else:
        # For LLM optimization: use condensed style
        style_fragments = []
        _add_condensed_style(style_fragments, context)
        style_block = ", ".join(style_fragments)
    components['style'] = style_block

    # 11. QUALITY KEYWORDS
    components['quality'] = "professional cinematography, natural motion, temporal consistency, smooth camera movement, stable composition, coherent scene, high fidelity rendering, photorealistic quality, 4K resolution, 16:9 widescreen"

    # 12. REFERENCE HINTS
    # Pass is_face_heavy to build_reference_hint for face feature control
    reference_hint = _build_reference_hint(context, is_face_heavy)
    components['reference_hint'] = reference_hint if reference_hint else None

    # 13. FINAL REMINDER (for character refs)
    final_reminder = None
    if using_character_ref:
        final_reminder = "REMINDER: Scene and background must come from the prompt description above, not from the character reference image"
    components['final_reminder'] = final_reminder

    # PHASE 2.8: CONDITIONAL PROMPT ORDERING
    # Assemble fragments based on shot type and lyrics presence
    fragments: List[str] = []

    # Always start with transition if present
    if components['transition']:
        fragments.append(components['transition'])

    # ORDERING LOGIC:
    if is_face_heavy and has_lyrics:
        # Face-heavy shot with singing: prioritize character face + lyrics
        # (Lip sync instructions removed per user request)
        if components['character_identity']:
            fragments.append(components['character_identity'])
        if components['scene_setting']:
            fragments.append(components['scene_setting'])
        if components['scene_instruction']:
            fragments.append(components['scene_instruction'])
        if components['lyrics_inline']:
            fragments.append(components['lyrics_inline'])
        if components['visual_description']:
            fragments.append(components['visual_description'])
        if components['motion']:
            fragments.append(components['motion'])
        if components['camera']:
            fragments.append(components['camera'])
        if components['scene_context']:
            fragments.append(components['scene_context'])
    elif is_face_heavy:
        # Face-heavy shot without lyrics: prioritize character face
        if components['character_identity']:
            fragments.append(components['character_identity'])
        if components['scene_setting']:
            fragments.append(components['scene_setting'])
        if components['scene_instruction']:
            fragments.append(components['scene_instruction'])
        if components['visual_description']:
            fragments.append(components['visual_description'])
        if components['motion']:
            fragments.append(components['motion'])
        if components['camera']:
            fragments.append(components['camera'])
        if components['scene_context']:
            fragments.append(components['scene_context'])
    elif has_lyrics:
        # Non-face-heavy with lyrics: lyrics after action
        if components['scene_setting']:
            fragments.append(components['scene_setting'])
        if components['scene_instruction']:
            fragments.append(components['scene_instruction'])
        if components['visual_description']:
            fragments.append(components['visual_description'])
        if components['motion']:
            fragments.append(components['motion'])
        if components['lyrics_inline']:
            fragments.append(components['lyrics_inline'])
        if components['camera']:
            fragments.append(components['camera'])
        if components['scene_context']:
            fragments.append(components['scene_context'])
    else:
        # Standard ordering (no special conditions)
        if components['character_identity']:
            fragments.append(components['character_identity'])
        if components['scene_setting']:
            fragments.append(components['scene_setting'])
        if components['scene_instruction']:
            fragments.append(components['scene_instruction'])
        if components['visual_description']:
            fragments.append(components['visual_description'])
        if components['motion']:
            fragments.append(components['motion'])
        if components['camera']:
            fragments.append(components['camera'])
        if components['scene_context']:
            fragments.append(components['scene_context'])

    # Add remaining components (same for all orderings)
    if components['persistence_note']:
        fragments.append(components['persistence_note'])
    if components['style']:
        fragments.append(components['style'])
    if components['quality']:
        fragments.append(components['quality'])
    if components['reference_hint']:
        fragments.append(components['reference_hint'])
    if components['final_reminder']:
        fragments.append(components['final_reminder'])

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

    PHASE 2.2: Now includes time of day with lighting guidance for consistency.

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

    # PHASE 2.2: Time of Day with lighting guidance
    if context.time_of_day:
        time_of_day_lower = context.time_of_day.lower()
        # Map time of day to lighting guidance
        lighting_guidance = {
            "dawn": "soft golden hour light, warm rising sun, long shadows",
            "morning": "bright natural daylight, fresh clear lighting, moderate shadows",
            "midday": "bright overhead sunlight, harsh lighting, short shadows",
            "afternoon": "warm afternoon light, golden tones, lengthening shadows",
            "dusk": "golden hour light, warm sunset glow, long dramatic shadows",
            "evening": "fading natural light, blue hour tones, soft ambient lighting",
            "night": "artificial lighting, moonlight, deep shadows, dramatic contrast",
            "midnight": "dark ambient lighting, deep shadows, minimal light sources",
        }
        guidance = lighting_guidance.get(time_of_day_lower, f"{context.time_of_day} lighting")
        lines.append(f"TIME OF DAY: {context.time_of_day} ({guidance})")

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

    # PHASE 2.9: Enhanced camera movement description
    camera_enhancement = _enhance_camera_description(context.beat_metadata)
    if camera_enhancement:
        lines.append(camera_enhancement)

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


def build_character_identity_block(context: ClipContext, is_face_heavy: bool = False) -> str:
    """
    Build character identity block with immutable character descriptions.

    PHASE 1: Now formats from structured CharacterFeatures instead of pre-formatted text.
    PHASE 3: Properly separates multiple characters with clear labels and roles.
    # PHASE 2.7: Pass has_lyrics flag to add mouth emphasis for singing clips. (COMMENTED OUT - lip sync removed)

    This ensures identical character descriptions across all clips, preventing
    the LLM from modifying or paraphrasing character features.

    This is appended AFTER LLM optimization to ensure the model cannot rewrite
    or deviate from the precise character specifications.

    Args:
        context: ClipContext with Character objects (with structured features)
        is_face_heavy: If True, this is a close-up shot that needs detailed face features

    Returns:
        Formatted character identity block with proper multi-character separation
    """
    # Detect if this clip has lyrics for mouth emphasis
    has_lyrics = bool(context.lyrics_context and context.lyrics_context.strip())

    # Try to use structured Character objects first
    if context.characters:
        # Pass character_reference_urls to conditionally add face reference note
        # Pass has_lyrics for mouth emphasis in singing clips
        # Pass is_face_heavy to control face feature detail level
        return _build_identity_from_characters(context.characters, context.character_reference_urls, has_lyrics, is_face_heavy)

    # Fallback: Use legacy character_descriptions if available
    if context.character_descriptions:
        return _build_identity_from_descriptions(context.character_descriptions, context.character_reference_urls)

    return ""


def _build_identity_from_characters(characters: List[Any], character_reference_urls: List[str] = None, has_lyrics: bool = False, is_face_heavy: bool = False) -> str:
    """
    Build character identity block from structured Character objects.

    PHASE 1: Formats from CharacterFeatures (no pre-formatted text).
    PHASE 3: Proper multi-character formatting with labels and roles.
    # PHASE 2.7: Add mouth emphasis for singing clips when has_lyrics=True. (COMMENTED OUT - lip sync removed)

    Args:
        characters: List of Character objects with structured features
        character_reference_urls: Optional list of character reference image URLs
        has_lyrics: If True, add critical mouth emphasis for lip sync (COMMENTED OUT - not used anymore)
        is_face_heavy: If True (close-up), include detailed face features. If False (mid-shot), rely on reference image.

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

        # Format face_features if it's a FaceFeatures object, otherwise fallback to face string
        # CRITICAL FIX: Only include detailed face features in close-ups
        # Mid-shots should rely on reference image to prevent face warping
        if hasattr(features, 'face_features') and features.face_features:
            face_features = features.face_features

            if is_face_heavy:
                # CLOSE-UP: Check if reference images exist
                # UPDATED 2025-11-18: When reference images exist, use minimal face features
                # to avoid text/image conflicts. When no reference images, use detailed features.
                using_character_refs = bool(character_reference_urls and len(character_reference_urls) > 0)

                if using_character_refs:
                    # CLOSE-UP WITH REFERENCE IMAGE: Minimal face features
                    # Only include face shape and skin tone - let reference image handle details
                    # PHASE 2.7: Add mouth emphasis for singing clips (COMMENTED OUT - lip sync removed)
                    # if has_lyrics:
                    #     face_block = f"""Face Shape: {face_features.shape}
                    # Skin Tone: {face_features.skin_tone}
                    # CRITICAL FOR LIP SYNC: Mouth movements matching sung lyrics."""
                    # else:
                    face_block = f"""Face Shape: {face_features.shape}
Skin Tone: {face_features.skin_tone}"""

                    # COMMENTED OUT 2025-11-18: Detailed face features commented out when reference
                    # images exist to avoid text/image conflicts. Reference image should drive the
                    # specific facial details (nose shape, mouth shape, cheek definition, jawline).
                    # If testing shows we need these details, they can be uncommented.
                    #
                    # Full detailed face block (COMMENTED OUT):
                    # mouth_line = f"Mouth: {face_features.mouth}"
                    # if has_lyrics:
                    #     mouth_line += f"\nCRITICAL FOR LIP SYNC: Character's mouth is {face_features.mouth}. Maintain consistent mouth shape during singing."
                    #
                    # face_block = f"""Face Shape: {face_features.shape}
                    # Skin Tone: {face_features.skin_tone}
                    # Nose: {face_features.nose}
                    # {mouth_line}
                    # Cheeks: {face_features.cheeks}
                    # Jawline: {face_features.jawline}
                    # Distinctive Marks: {face_features.distinctive_marks}"""
                else:
                    # CLOSE-UP WITHOUT REFERENCE IMAGE: Keep detailed face features as fallback
                    # This ensures we still get good results when no reference image is available
                    # PHASE 2.7: Add mouth emphasis for singing clips (COMMENTED OUT - lip sync removed)
                    mouth_line = f"Mouth: {face_features.mouth}"
                    # if has_lyrics:
                    #     mouth_line += f"\nCRITICAL FOR LIP SYNC: Character's mouth is {face_features.mouth}. Maintain consistent mouth shape during singing."

                    face_block = f"""Face Shape: {face_features.shape}
Skin Tone: {face_features.skin_tone}
Nose: {face_features.nose}
{mouth_line}
Cheeks: {face_features.cheeks}
Jawline: {face_features.jawline}
Distinctive Marks: {face_features.distinctive_marks}"""
            else:
                # MID-SHOT: Minimal face description - let reference image handle details
                # (This code path is UNCHANGED - already minimal)
                # COMMENTED OUT: Lip sync instructions removed per user request
                # if has_lyrics:
                #     face_block = f"Face: Match reference image exactly. CRITICAL FOR LIP SYNC: Mouth movements matching sung lyrics."
                # else:
                face_block = "Face: Match reference image exactly (face shape, skin tone, facial features)"
        elif hasattr(features, 'face'):
            # Backward compatibility: use old face string format
            face_block = f"Face: {features.face}"
        else:
            face_block = ""

        char_block = f"""{char_label}:
Hair: {features.hair}
{face_block}
Eyes: {features.eyes}
Clothing: {features.clothing}
Accessories: {features.accessories}
Build: {features.build}
Age: {features.age}"""

        character_blocks.append(char_block)

    if not character_blocks:
        return ""

    # PHASE 3: Proper multi-character formatting
    # Instruction to use faces from reference images (only if reference images are available)
    #
    # COMMENTED OUT 2025-11-18: This line is redundant with Layer 2 (reference hint at line 938-940)
    # which already instructs the model to match the reference image. Having this additional
    # CRITICAL statement creates over-prescription and may conflict with the "naturally" guidance
    # in mid-shots. Reference images are already passed as a separate API parameter to Veo 3.1
    # with high priority. If testing shows this is needed, we can uncomment it selectively for
    # close-ups only.
    #
    # face_reference_note = ""
    # if character_reference_urls and len(character_reference_urls) > 0:
    #     face_reference_note = "\n\nCRITICAL: Use the face from the character reference image for each character. Match the exact facial features, structure, and appearance from the reference image."

    # Set to empty string since we're not using it
    face_reference_note = ""
    
    if len(character_blocks) == 1:
        # Single character
        identity_block = f"""CHARACTER IDENTITIES:

{character_blocks[0]}

CRITICAL: These are EXACT, IMMUTABLE features for ALL characters. Each character must maintain these precise features in every clip.{face_reference_note}"""
    else:
        # Multiple characters - separate with double newlines
        characters_text = "\n\n".join(character_blocks)
        character_count = len(character_blocks)
        identity_block = f"""CHARACTER IDENTITIES:

{characters_text}

CRITICAL: These are EXACT, IMMUTABLE features for ALL {character_count} characters. Each character must maintain these precise features in every clip.{face_reference_note}"""

    return identity_block


def _build_identity_from_descriptions(character_descriptions: List[str], character_reference_urls: List[str] = None) -> str:
    """
    DEPRECATED: Build character identity block from pre-formatted descriptions.

    This is a fallback for backward compatibility when Character objects
    don't have structured features yet.
    
    Args:
        character_descriptions: List of pre-formatted character description strings
        character_reference_urls: Optional list of character reference image URLs

    Returns:
        Formatted character identity block
    """
    if not character_descriptions:
        return ""

    # Join all character descriptions
    char_desc = ', '.join(character_descriptions)

    # Check if character description already has CRITICAL statement
    has_critical_statement = "CRITICAL:" in char_desc and "IMMUTABLE features" in char_desc

    # Instruction to use faces from reference images (only if reference images are available)
    face_reference_note = ""
    if character_reference_urls and len(character_reference_urls) > 0:
        face_reference_note = " CRITICAL: Use the face from the character reference image for each character. Match the exact facial features, structure, and appearance from the reference image."

    if has_critical_statement:
        # Character description already includes CRITICAL statement, don't duplicate
        identity_block = f"CHARACTER IDENTITY: {char_desc}{face_reference_note}"
    else:
        # Add CRITICAL statement if not present in character description
        identity_block = (
            f"CHARACTER IDENTITY: {char_desc}. "
            "CRITICAL: These are EXACT, FIXED features - do not modify, reinterpret, "
            "or deviate from these specific details. This is the same character "
            "appearing in all video clips - maintain precise consistency with these "
            f"physical descriptions.{face_reference_note}"
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

    # Apply word replacements before formatting
    lyrics_text = context.lyrics_context.strip()
    # Replace "ass" with "ash" (case-insensitive, whole word only)
    lyrics_text = re.sub(r'\bass\b', 'ash', lyrics_text, flags=re.IGNORECASE)
    # Replace "pussy" with "pushy" (case-insensitive, whole word only)
    lyrics_text = re.sub(r'\bpussy\b', 'pushy', lyrics_text, flags=re.IGNORECASE)
    # Replace "kiss" with "kish" (case-insensitive, whole word only)
    lyrics_text = re.sub(r'\bkiss\b', 'kish', lyrics_text, flags=re.IGNORECASE)
    # Remove n-word (hard r version, case-insensitive, whole word only)
    lyrics_text = re.sub(r'\bn[1i]gg[ae]r\b', '', lyrics_text, flags=re.IGNORECASE)
    # Remove n-word (soft a version, case-insensitive, whole word only)
    lyrics_text = re.sub(r'\bn[1i]gg[ae]\b', '', lyrics_text, flags=re.IGNORECASE)
    # Clean up any extra spaces that may result from word removal
    lyrics_text = re.sub(r'\s+', ' ', lyrics_text).strip()

    # Lyrics are already filtered to clip's exact time range by scene planner
    # Format as a clear reference block
    lyrics_block = f"LYRICS REFERENCE: \"{lyrics_text}\""

    return lyrics_block


def build_object_identity_block(context: ClipContext) -> str:
    """
    Build object identity block with immutable object descriptions.

    PHASE 3: Formats from structured ObjectFeatures for consistent prop tracking.

    This ensures identical object descriptions across all clips where the object appears,
    preventing the LLM from modifying or paraphrasing object features.

    This is appended AFTER LLM optimization to ensure the model cannot rewrite
    or deviate from the precise object specifications.

    Args:
        context: ClipContext with Object objects (with structured features)

    Returns:
        Formatted object identity block with proper multi-object separation
    """
    # Try to use structured Object objects first
    if context.objects:
        return _build_identity_from_objects(context.objects)

    # Fallback: Use legacy object_descriptions if available
    if context.object_descriptions:
        return _build_identity_from_object_descriptions(context.object_descriptions)

    return ""


def _build_identity_from_objects(objects: List[Any]) -> str:
    """
    Build object identity block from structured Object objects.

    PHASE 3: Formats from ObjectFeatures (no pre-formatted text).

    Args:
        objects: List of Object objects with structured features

    Returns:
        Formatted object identity block
    """
    if not objects:
        return ""

    # Build individual object blocks
    object_blocks = []
    for obj in objects:
        # Skip if no features available
        if not hasattr(obj, 'features') or obj.features is None:
            # Fallback to description field if features not available
            if hasattr(obj, 'name') and obj.name:
                object_blocks.append(obj.name)
            continue

        # Get object name
        obj_name = getattr(obj, 'name', None) or getattr(obj, 'id', 'Object')

        # Format features
        features = obj.features
        obj_block = f"""{obj_name}:
Object Type: {features.object_type}
Color: {features.color}
Material: {features.material}
Distinctive Features: {features.distinctive_features}
Size: {features.size}
Condition: {features.condition}"""

        object_blocks.append(obj_block)

    if not object_blocks:
        return ""

    # Proper multi-object formatting
    if len(object_blocks) == 1:
        # Single object
        identity_block = f"""OBJECT IDENTITIES:

{object_blocks[0]}

CRITICAL: These are EXACT, IMMUTABLE features for this object. It must maintain these precise features in every clip where it appears."""
    else:
        # Multiple objects - separate with double newlines
        objects_text = "\n\n".join(object_blocks)
        object_count = len(object_blocks)
        identity_block = f"""OBJECT IDENTITIES:

{objects_text}

CRITICAL: These are EXACT, IMMUTABLE features for ALL {object_count} objects. Each object must maintain these precise features in every clip where it appears."""

    return identity_block


def _build_identity_from_object_descriptions(object_descriptions: List[str]) -> str:
    """
    DEPRECATED: Build object identity block from pre-formatted descriptions.

    This is a fallback for backward compatibility.

    Args:
        object_descriptions: List of pre-formatted object description strings

    Returns:
        Formatted object identity block
    """
    if not object_descriptions:
        return ""

    # Join all object descriptions
    obj_desc = ', '.join(object_descriptions)

    identity_block = (
        f"OBJECT IDENTITY: {obj_desc}. "
        "CRITICAL: These are EXACT, FIXED features - do not modify, reinterpret, "
        "or deviate from these specific details. These objects appear "
        "in multiple video clips - maintain precise consistency with these "
        "physical descriptions."
    )

    return identity_block


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


def _build_reference_hint(context: ClipContext, is_face_heavy: bool = False) -> str:
    hints: List[str] = []
    if context.scene_reference_url:
        hints.append("Match the look and composition of the established scene reference image")
    if context.character_reference_urls:
        # When using character reference images, focus on character/object appearance only
        # Ignore any scene/background in the character reference image - use the prompt's scene description instead
        # Make this very explicit since the model tends to use the image as first frame
        if is_face_heavy:
            hints.append("CRITICAL: Match character's face from reference image exactly (facial features, structure, appearance). Completely ignore all background/scene from reference image.")
        else:
            hints.append("CRITICAL: Match character's overall appearance from reference image (body, proportions, general look). Completely ignore all background/scene from reference image. Let the reference image guide facial features naturally.")
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

