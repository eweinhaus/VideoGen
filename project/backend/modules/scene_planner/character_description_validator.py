"""
Post-processing validation and extraction for character descriptions.

Extracts character features from LLM output into structured format.
Does NOT format into text - that happens later in prompt_synthesizer.
"""

import re
from typing import Dict, Any, Optional
from shared.logging import get_logger
from shared.models.scene import CharacterFeatures, FaceFeatures

logger = get_logger("scene_planner")


def extract_character_features(
    character_id: str,
    character_name: str,
    description: str
) -> tuple[Optional[CharacterFeatures], Optional[str]]:
    """
    Extract character features from LLM description into structured format.

    This function ONLY extracts features - it does NOT format them into text.
    Formatting happens later in prompt_synthesizer.build_character_identity_block().

    Args:
        character_id: Character ID (e.g., "protagonist")
        character_name: Character name (e.g., "Alice")
        description: Raw character description from Scene Planner LLM

    Returns:
        Tuple of (CharacterFeatures, character_name) - always returns CharacterFeatures (uses defaults if needed)
    """
    # Extract features from the description
    features_dict = _extract_features(description)

    # ALWAYS create CharacterFeatures object (use defaults if extraction fails)
    # This ensures we never fall back to raw description text without names/roles
    if len(features_dict) < 4:
        logger.warning(
            f"Character {character_id} description missing most features (only {len(features_dict)} found), will use defaults",
            extra={
                "character_id": character_id,
                "features_extracted": list(features_dict.keys()),
                "note": "Using defaults to ensure structured formatting with names/roles"
            }
        )

    # Build CharacterFeatures object with extracted or default values
    # NOTE: ALWAYS returns CharacterFeatures (never None) to ensure proper formatting

    # PHASE 1.2: Create nested FaceFeatures from extracted or default values
    # Parse face string into structured FaceFeatures (or use defaults)
    face_str = features_dict.get("Face") or "medium brown skin tone, oval face shape, smooth features, clean shaven"
    face_features = _parse_face_features(face_str)

    features = CharacterFeatures(
        hair=features_dict.get("Hair") or "short dark brown hair, straight texture, neat style",
        face_features=face_features,
        eyes=features_dict.get("Eyes") or "dark brown eyes, medium eyebrows",
        clothing=features_dict.get("Clothing") or "dark gray hoodie, blue jeans, white sneakers",
        accessories=features_dict.get("Accessories") or "None",
        build=features_dict.get("Build") or "athletic build, approximately 5'9\" height, medium frame",
        age=features_dict.get("Age") or "appears late 20s"
    )

    # Log warning if using defaults
    missing_features = [name for name in ["Hair", "Face", "Eyes", "Clothing", "Build", "Age"]
                       if name not in features_dict or not features_dict[name]]

    if missing_features:
        logger.warning(
            f"Character {character_id} missing features, using defaults",
            extra={
                "character": character_name,
                "missing_features": missing_features,
                "note": "Scene Planner LLM failed to provide specific details"
            }
        )

    logger.info(
        f"Extracted character {character_id} features into structured format",
        extra={
            "character_id": character_id,
            "features_count": len(features_dict),
            "had_all_features": len(missing_features) == 0
        }
    )

    return features, character_name


def validate_and_reformat_character_description(
    character_id: str,
    character_name: str,
    description: str
) -> str:
    """
    DEPRECATED: Use extract_character_features() instead.

    This function is kept for backward compatibility but will be removed.
    It extracts features and then formats them into the old text format.

    Args:
        character_id: Character ID (e.g., "protagonist")
        character_name: Character name (e.g., "Alice")
        description: Raw character description from Scene Planner LLM

    Returns:
        Reformatted description in FIXED CHARACTER IDENTITY format
    """
    # Extract features
    features, name = extract_character_features(character_id, character_name, description)

    if features is None:
        # Fallback: use the original description
        logger.warning(
            f"Could not extract features for {character_id}, using original description",
            extra={"character_id": character_id}
        )
        return description

    # Build the old formatted description for backward compatibility
    # Convert face_features back to string for old format
    face_features = features.face_features
    face_str = f"{face_features.skin_tone} skin tone, {face_features.shape} face shape, {face_features.nose}, {face_features.mouth}, {face_features.cheeks}, {face_features.jawline}"
    if face_features.distinctive_marks != "none":
        face_str += f", {face_features.distinctive_marks}"

    formatted = _build_formatted_description(name or character_name, {
        "Hair": features.hair,
        "Face": face_str,
        "Eyes": features.eyes,
        "Clothing": features.clothing,
        "Accessories": features.accessories,
        "Build": features.build,
        "Age": features.age
    })

    return formatted


def _has_correct_format(description: str) -> bool:
    """
    Check if description already has the correct format.

    Required elements:
    - "FIXED CHARACTER IDENTITY:" header
    - All 7 features as bullet points (Hair:, Face:, Eyes:, Clothing:, Accessories:, Build:, Age:)
    - "CRITICAL:" footer with immutability statement
    """
    has_header = "FIXED CHARACTER IDENTITY:" in description
    has_footer = "CRITICAL:" in description and "EXACT, IMMUTABLE features" in description

    required_features = ["Hair:", "Face:", "Eyes:", "Clothing:", "Accessories:", "Build:", "Age:"]
    has_all_features = all(feature in description for feature in required_features)

    return has_header and has_footer and has_all_features


def _parse_face_features(face_description: str) -> FaceFeatures:
    """
    Parse a face description string into structured FaceFeatures.

    PHASE 1.2: Convert flat face description into nested structured features.

    Args:
        face_description: Face description string (e.g., "fair skin, oval face, small nose")

    Returns:
        FaceFeatures object with structured facial attributes
    """
    # Lowercased for matching
    desc_lower = face_description.lower()

    # Extract skin tone
    skin_tone = "medium"
    if any(word in desc_lower for word in ["fair", "pale", "light"]):
        skin_tone = "fair"
    elif any(word in desc_lower for word in ["olive", "tan"]):
        skin_tone = "olive"
    elif any(word in desc_lower for word in ["brown", "dark"]):
        skin_tone = "brown"

    # Extract face shape
    shape = "oval"
    if "heart" in desc_lower:
        shape = "heart-shaped"
    elif "square" in desc_lower:
        shape = "square"
    elif "round" in desc_lower:
        shape = "round"
    elif "oval" in desc_lower:
        shape = "oval"

    # Extract nose
    nose = "straight nose"
    if "button" in desc_lower or "small" in desc_lower:
        nose = "button nose"
    elif "aquiline" in desc_lower or "prominent" in desc_lower:
        nose = "aquiline nose"

    # Extract mouth
    mouth = "medium lips"
    if "full" in desc_lower or "plump" in desc_lower:
        mouth = "full lips"
    elif "thin" in desc_lower:
        mouth = "thin lips"
    elif "wide" in desc_lower:
        mouth = "wide smile"

    # Extract cheeks
    cheeks = "rounded cheeks"
    if "high" in desc_lower and "cheek" in desc_lower:
        cheeks = "high cheekbones"

    # Extract jawline
    jawline = "soft"
    if "strong" in desc_lower or "angular" in desc_lower:
        jawline = "strong"
    elif "soft" in desc_lower or "rounded" in desc_lower:
        jawline = "soft"

    # Extract distinctive marks
    distinctive_marks = "none"
    if "freckle" in desc_lower:
        distinctive_marks = "freckles"
    elif "mole" in desc_lower:
        distinctive_marks = "mole"
    elif "scar" in desc_lower:
        distinctive_marks = "scar"

    return FaceFeatures(
        shape=shape,
        skin_tone=skin_tone,
        nose=nose,
        mouth=mouth,
        cheeks=cheeks,
        jawline=jawline,
        distinctive_marks=distinctive_marks
    )


def _extract_features(description: str) -> Dict[str, str]:
    """
    Extract character features from description text.

    Uses regex patterns to find feature descriptions even if format is not perfect.
    Handles both newline-separated and dash-separated formats.

    Returns:
        Dictionary mapping feature names to descriptions
    """
    features = {}

    # Pattern to match "Feature: description" format
    # Handles both bullet point format and inline format (with " - " separators)
    # FIXED: Pattern now correctly captures descriptions that contain hyphens (e.g., "shoulder-length", "5'7\"")
    # Uses positive lookahead to stop at next " - FeatureName:" pattern, not just any hyphen
    # This allows hyphens within feature descriptions (like "shoulder-length", "mid-20s", etc.)
    feature_patterns = {
        "Hair": r"[-•]?\s*(?i:Hair):\s*(.+?)(?=\s*-\s*(?:Face|Eyes|Clothing|Accessories|Build|Age|CRITICAL)|\n|$)",
        "Face": r"[-•]?\s*(?i:Face):\s*(.+?)(?=\s*-\s*(?:Hair|Eyes|Clothing|Accessories|Build|Age|CRITICAL)|\n|$)",
        "Eyes": r"[-•]?\s*(?i:Eyes):\s*(.+?)(?=\s*-\s*(?:Hair|Face|Clothing|Accessories|Build|Age|CRITICAL)|\n|$)",
        "Clothing": r"[-•]?\s*(?i:Clothing):\s*(.+?)(?=\s*-\s*(?:Hair|Face|Eyes|Accessories|Build|Age|CRITICAL)|\n|$)",
        "Accessories": r"[-•]?\s*(?i:Accessories):\s*(.+?)(?=\s*-\s*(?:Hair|Face|Eyes|Clothing|Build|Age|CRITICAL)|\n|$)",
        "Build": r"[-•]?\s*(?i:Build):\s*(.+?)(?=\s*-\s*(?:Hair|Face|Eyes|Clothing|Accessories|Age|CRITICAL)|\n|$)",
        "Age": r"[-•]?\s*(?i:Age):\s*(.+?)(?=\s*-\s*(?:Hair|Face|Eyes|Clothing|Accessories|Build|CRITICAL)|\n|$)",
    }
    
    # Extract features using improved patterns
    for feature_name, pattern in feature_patterns.items():
        match = re.search(pattern, description, re.MULTILINE)
        if match:
            feature_text = match.group(1).strip()
            # Remove trailing punctuation
            feature_text = feature_text.rstrip('.,;')
            features[feature_name] = feature_text
        else:
            logger.warning(
                f"Could not extract {feature_name} from character description",
                extra={"feature": feature_name, "description_preview": description[:200]}
            )

    # Fallback: Try to extract features from unstructured text using keyword matching
    if len(features) < 4:  # If we didn't find most features
        logger.warning(
            "Character description missing structured features, attempting unstructured extraction",
            extra={"features_found": len(features)}
        )

        # Try to extract clothing from common words (if not already found)
        if "Clothing" not in features:
            clothing_keywords = ["hoodie", "jacket", "shirt", "t-shirt", "dress", "jeans", "pants", "shorts", "sweater", "blazer"]
            for keyword in clothing_keywords:
                if keyword in description.lower():
                    # Extract sentence containing the clothing item
                    sentences = description.split('.')
                    for sentence in sentences:
                        if keyword in sentence.lower():
                            features["Clothing"] = sentence.strip()
                            break
                    break

        # Try to extract hair color/style from common patterns
        if "Hair" not in features:
            hair_patterns = [
                r"(short|long|medium|shoulder-length)\s+(black|brown|blonde|red|gray|white)\s+hair",
                r"(curly|straight|wavy)\s+hair",
                r"(black|brown|blonde|red|gray|white)\s+hair"
            ]
            for pattern in hair_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    features["Hair"] = match.group(0)
                    break

        # Try to extract age from common patterns
        if "Age" not in features:
            age_patterns = [
                r"appears?\s+(early|mid|late)\s+(\d+)s",
                r"(young|middle-aged|elderly|teen)",
                r"(\d+)\s+years?\s+old"
            ]
            for pattern in age_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    features["Age"] = f"appears {match.group(0)}"
                    break

    return features


def _build_formatted_description(character_name: str, features: Dict[str, str]) -> str:
    """
    Build properly formatted character description.

    Uses extracted features or smart defaults (NEVER "unspecified").

    Args:
        character_name: Character name (e.g., "Alice")
        features: Dictionary of extracted features

    Returns:
        Formatted description in FIXED CHARACTER IDENTITY format
    """
    # Use extracted features or provide smart defaults (NEVER "unspecified")
    # These defaults are better than nothing - at least they constrain the character
    hair = features.get("Hair") or "short dark brown hair, straight texture, neat style"
    face = features.get("Face") or "medium brown skin tone, oval face shape, smooth features, clean shaven"
    eyes = features.get("Eyes") or "dark brown eyes, medium eyebrows"
    clothing = features.get("Clothing") or "dark gray hoodie, blue jeans, white sneakers"
    accessories = features.get("Accessories") or "None"
    build = features.get("Build") or "athletic build, approximately 5'9\" height, medium frame"
    age = features.get("Age") or "appears late 20s"

    # Log warning if using defaults
    missing_features = [name for name in ["Hair", "Face", "Eyes", "Clothing", "Build", "Age"]
                       if name not in features or not features[name]]

    if missing_features:
        logger.warning(
            f"Character {character_name} missing features, using defaults",
            extra={
                "character": character_name,
                "missing_features": missing_features,
                "note": "Scene Planner LLM failed to provide specific details"
            }
        )

    # Build the formatted description
    formatted = f"""{character_name} - FIXED CHARACTER IDENTITY:
- Hair: {hair}
- Face: {face}
- Eyes: {eyes}
- Clothing: {clothing}
- Accessories: {accessories}
- Build: {build}
- Age: {age}

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance."""

    return formatted


def validate_character_specificity(description: str) -> Dict[str, Any]:
    """
    Validate that character description has sufficient specificity.

    Checks for:
    - Specific color modifiers (bright, dark, deep, etc.)
    - Measurements (height, lengths)
    - Avoidance of vague words (stylish, cool, beautiful, confident)

    Returns:
        Dictionary with validation results and warnings
    """
    results = {
        "is_specific": True,
        "warnings": [],
        "has_measurements": False,
        "has_specific_colors": False,
        "vague_words_found": []
    }

    # Check for specific color modifiers
    color_modifiers = [
        "bright", "dark", "deep", "light", "navy", "forest",
        "burgundy", "olive", "golden", "ash", "warm", "cool",
        "pale", "rich", "vivid", "muted"
    ]
    has_specific_colors = any(modifier in description.lower() for modifier in color_modifiers)
    results["has_specific_colors"] = has_specific_colors

    if not has_specific_colors:
        results["warnings"].append("Missing specific color modifiers (e.g., 'bright blue' not 'blue')")
        results["is_specific"] = False

    # Check for measurements
    measurement_indicators = ["'", '"', "inch", "cm", "foot", "feet", "shoulder", "waist", "length"]
    has_measurements = any(indicator in description.lower() for indicator in measurement_indicators)
    results["has_measurements"] = has_measurements

    if not has_measurements:
        results["warnings"].append("Missing specific measurements (e.g., height, hair length)")
        results["is_specific"] = False

    # Check for vague words
    vague_words = ["stylish", "cool", "nice", "beautiful", "confident", "attractive", "handsome", "pretty"]
    vague_found = [word for word in vague_words if word in description.lower()]
    results["vague_words_found"] = vague_found

    if vague_found:
        results["warnings"].append(f"Found vague words: {', '.join(vague_found)}")
        results["is_specific"] = False

    return results
