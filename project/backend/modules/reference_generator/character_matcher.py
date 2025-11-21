"""
Character matching logic for user-uploaded character reference images.

Matches uploaded images to ScenePlan characters using multiple strategies.
"""

from typing import Dict, List, Optional
from shared.models.scene import ScenePlan
from shared.logging import get_logger

logger = get_logger("reference_generator.character_matcher")


def match_uploaded_image_to_main_character(
    uploaded_image: Dict,
    scene_plan: ScenePlan
) -> Optional[str]:
    """
    Match uploaded main character image to the main character in ScenePlan.
    
    Matching strategy (priority order):
    1. By role: Find character with role "main character" or "protagonist"
    2. By order: First character in the list (fallback)
    
    Args:
        uploaded_image: Dict with keys: url, index
        scene_plan: ScenePlan with characters to match against
        
    Returns:
        Character ID if main character found, None otherwise
    """
    if not uploaded_image:
        return None
    
    if not scene_plan.characters:
        logger.warning(
            "No characters in scene plan to match uploaded image against",
            extra={"uploaded_image": uploaded_image.get("url")}
        )
        return None
    
    # Log all characters for debugging
    logger.info(
        "Attempting to match uploaded image to main character",
        extra={
            "total_characters": len(scene_plan.characters),
            "all_character_roles": [char.role for char in scene_plan.characters] if scene_plan.characters else [],
            "all_character_ids": [char.id for char in scene_plan.characters] if scene_plan.characters else [],
            "all_character_names": [char.name for char in scene_plan.characters] if scene_plan.characters else []
        }
    )
    
    # Strategy 1: Find main character by role (flexible matching)
    # Check for various role names that indicate main character (case-insensitive)
    main_characters = []
    for char in scene_plan.characters:
        role_lower = char.role.lower() if char.role else ""
        # Check for main character indicators (substring match for flexibility)
        if any(keyword in role_lower for keyword in [
            "main character", "protagonist", "lead", "hero", "heroine",
            "primary character", "central character", "main", "principal"
        ]):
            main_characters.append(char)
            logger.debug(
                f"Found potential main character by role",
                extra={
                    "character_id": char.id,
                    "character_role": char.role,
                    "role_lower": role_lower,
                    "matching_keywords": [kw for kw in [
                        "main character", "protagonist", "lead", "hero", "heroine",
                        "primary character", "central character", "main", "principal"
                    ] if kw in role_lower]
                }
            )
    
    if main_characters:
        # If multiple main characters, use the first one
        main_char = main_characters[0]
        logger.info(
            f"Matched uploaded image to main character '{main_char.id}' by role",
            extra={
                "character_id": main_char.id,
                "character_role": main_char.role,
                "character_name": main_char.name,
                "matching_keyword": "found in role",
                "total_matches": len(main_characters)
            }
        )
        return main_char.id
    
    # Strategy 2: If only one character, use it (very likely the main character)
    if len(scene_plan.characters) == 1:
        single_char = scene_plan.characters[0]
        logger.info(
            f"Matched uploaded image to single character '{single_char.id}' (only character)",
            extra={
                "character_id": single_char.id,
                "character_role": single_char.role,
                "character_name": single_char.name,
                "note": "Only one character in scene plan, assuming it's the main character"
            }
        )
        return single_char.id
    
    # Strategy 3: Use first character as fallback (assuming it's the main character)
    # This is a reasonable assumption since Scene Planner typically lists main character first
    if scene_plan.characters:
        first_char = scene_plan.characters[0]
        logger.info(
            f"Matched uploaded image to first character '{first_char.id}' (fallback)",
            extra={
                "character_id": first_char.id,
                "character_role": first_char.role,
                "character_name": first_char.name,
                "note": "No explicit main character found, using first character",
                "all_character_roles": [char.role for char in scene_plan.characters],
                "total_characters": len(scene_plan.characters)
            }
        )
        return first_char.id
    
    # Final fallback: If we have an uploaded image but couldn't match, 
    # use the first character anyway (it's almost always the main character)
    # This is better than returning None and generating a new image
    if scene_plan.characters and uploaded_image:
        first_char = scene_plan.characters[0]
        logger.warning(
            f"Could not match uploaded image by role, using first character '{first_char.id}' as final fallback",
            extra={
                "character_id": first_char.id,
                "character_role": first_char.role,
                "character_name": first_char.name,
                "total_characters": len(scene_plan.characters),
                "all_character_roles": [char.role for char in scene_plan.characters],
                "note": "Using first character as fallback to ensure uploaded image is used"
            }
        )
        return first_char.id
    
    logger.warning(
        "Could not find main character to match uploaded image",
        extra={
            "total_characters": len(scene_plan.characters),
            "character_roles": [char.role for char in scene_plan.characters] if scene_plan.characters else [],
            "has_uploaded_image": bool(uploaded_image)
        }
    )
    return None

