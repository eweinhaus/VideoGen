"""
Post-processing validation and reformatting for character descriptions.

Ensures character descriptions follow the FIXED CHARACTER IDENTITY format
required for text-to-video generation consistency.
"""

import re
from typing import Dict, Any
from shared.logging import get_logger

logger = get_logger("scene_planner")


def validate_and_reformat_character_description(
    character_id: str,
    character_name: str,
    description: str
) -> str:
    """
    Validate and reformat character description to ensure it matches the required format.

    This is Option 2: Post-Process the Description - ensures LLM output matches
    the exact format specification even if the LLM deviates.

    Args:
        character_id: Character ID (e.g., "protagonist")
        character_name: Character name (e.g., "Alice")
        description: Raw character description from Scene Planner LLM

    Returns:
        Reformatted description in FIXED CHARACTER IDENTITY format
    """

    # Check if description already has the correct format
    if _has_correct_format(description):
        logger.debug(
            f"Character {character_id} description already in correct format",
            extra={"character_id": character_id}
        )
        return description

    # Extract features from the description
    features = _extract_features(description)

    # Build properly formatted description
    formatted = _build_formatted_description(character_name, features)

    logger.info(
        f"Reformatted character {character_id} description to FIXED CHARACTER IDENTITY format",
        extra={
            "character_id": character_id,
            "had_format_header": "FIXED CHARACTER IDENTITY:" in description,
            "had_critical_footer": "CRITICAL:" in description,
            "features_extracted": len(features)
        }
    )

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


def _extract_features(description: str) -> Dict[str, str]:
    """
    Extract character features from description text.

    Uses regex patterns to find feature descriptions even if format is not perfect.

    Returns:
        Dictionary mapping feature names to descriptions
    """
    features = {}

    # Pattern to match "Feature: description" format
    # Handles both bullet point format and inline format
    feature_patterns = {
        "Hair": r"(?:^|\n)\s*[-•]?\s*Hair:\s*([^\n]+)",
        "Face": r"(?:^|\n)\s*[-•]?\s*Face:\s*([^\n]+)",
        "Eyes": r"(?:^|\n)\s*[-•]?\s*Eyes:\s*([^\n]+)",
        "Clothing": r"(?:^|\n)\s*[-•]?\s*Clothing:\s*([^\n]+)",
        "Accessories": r"(?:^|\n)\s*[-•]?\s*Accessories:\s*([^\n]+)",
        "Build": r"(?:^|\n)\s*[-•]?\s*Build:\s*([^\n]+)",
        "Age": r"(?:^|\n)\s*[-•]?\s*Age:\s*([^\n]+)",
    }

    for feature_name, pattern in feature_patterns.items():
        match = re.search(pattern, description, re.IGNORECASE | re.MULTILINE)
        if match:
            # Clean up the extracted text
            feature_text = match.group(1).strip()
            # Remove trailing punctuation or "CRITICAL" if it got captured
            feature_text = re.sub(r'(CRITICAL|\.|\n).*$', '', feature_text, flags=re.DOTALL).strip()
            features[feature_name] = feature_text
        else:
            logger.warning(
                f"Could not extract {feature_name} from character description",
                extra={"feature": feature_name}
            )

    # Fallback: Try to extract features from unstructured text
    if len(features) < 4:  # If we didn't find most features
        logger.warning(
            "Character description missing structured features, attempting unstructured extraction",
            extra={"features_found": len(features)}
        )
        # This would require more sophisticated NLP, for now just log warning
        # Return empty dict to trigger default values

    return features


def _build_formatted_description(character_name: str, features: Dict[str, str]) -> str:
    """
    Build properly formatted character description.

    Args:
        character_name: Character name (e.g., "Alice")
        features: Dictionary of extracted features

    Returns:
        Formatted description in FIXED CHARACTER IDENTITY format
    """
    # Use extracted features or provide defaults if missing
    hair = features.get("Hair", "unspecified hair")
    face = features.get("Face", "unspecified face")
    eyes = features.get("Eyes", "unspecified eyes")
    clothing = features.get("Clothing", "unspecified clothing")
    accessories = features.get("Accessories", "None")
    build = features.get("Build", "average build")
    age = features.get("Age", "unspecified age")

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
