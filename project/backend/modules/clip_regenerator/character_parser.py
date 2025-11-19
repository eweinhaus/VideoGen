"""
Character parser for lipsync and regeneration instructions.

Extracts character references from user instructions and matches them
to character IDs from the scene plan.
"""

import re
from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel, Field
from shared.models.scene import ScenePlan, Character
from shared.logging import get_logger

logger = get_logger("clip_regenerator.character_parser")


class CharacterMatch(BaseModel):
    """Character match result."""
    
    character_id: str
    character_name: str
    confidence: float = Field(description="Match confidence 0.0-1.0")
    match_type: str = Field(description="How the match was made: 'name', 'pronoun', 'role', 'id'")


def extract_character_references(instruction: str) -> List[str]:
    """
    Extract potential character references from user instruction.
    
    Looks for:
    - Character names (capitalized words)
    - Pronouns (him, her, them, they, he, she)
    - Role references (protagonist, main character, singer, etc.)
    - Character IDs (if user knows them)
    
    Args:
        instruction: User instruction string
        
    Returns:
        List of potential character references (normalized)
    """
    if not instruction or not instruction.strip():
        return []
    
    instruction_lower = instruction.lower()
    references = []
    
    # Extract pronouns
    pronouns = {
        "him", "her", "them", "they", "he", "she",
        "his", "hers", "their", "theirs"
    }
    for pronoun in pronouns:
        if pronoun in instruction_lower:
            references.append(pronoun)
    
    # Extract capitalized words (potential character names)
    # Match words that start with capital letter and are 2+ characters
    capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', instruction)
    for word in capitalized_words:
        # Skip common words that aren't names
        common_words = {
            "Make", "Make", "Add", "Change", "Fix", "Regenerate",
            "Clip", "Clips", "Video", "Scene", "The", "This", "That"
        }
        if word not in common_words:
            references.append(word.lower())
    
    # Extract role references
    role_keywords = [
        "protagonist", "main character", "singer", "artist", "rapper",
        "lead", "background", "character", "person", "guy", "girl",
        "man", "woman", "boy", "girl", "first", "second", "third"
    ]
    for role in role_keywords:
        if role in instruction_lower:
            references.append(role)
    
    # Extract "the [name]" patterns
    the_pattern = re.findall(r'the\s+([a-z]+)', instruction_lower)
    references.extend(the_pattern)
    
    # Remove duplicates and return
    return list(set(references))


def match_characters_to_references(
    references: List[str],
    scene_plan: ScenePlan,
    clip_index: Optional[int] = None
) -> List[CharacterMatch]:
    """
    Match user references to character IDs from scene plan.
    
    Args:
        references: List of character references from user instruction
        scene_plan: ScenePlan with character definitions
        clip_index: Optional clip index to filter characters by clip
        
    Returns:
        List of CharacterMatch objects (sorted by confidence, highest first)
    """
    if not references or not scene_plan.characters:
        return []
    
    matches = []
    
    # Get characters that appear in this clip (if clip_index provided)
    clip_characters = set()
    if clip_index is not None and scene_plan.clip_scripts:
        for script in scene_plan.clip_scripts:
            if script.clip_index == clip_index:
                clip_characters.update(script.characters or [])
    
    # Match each reference to characters
    for ref in references:
        ref_lower = ref.lower()
        
        for character in scene_plan.characters:
            # Skip if character doesn't appear in this clip
            if clip_index is not None and character.id not in clip_characters:
                continue
            
            confidence = 0.0
            match_type = None
            
            # Exact name match (highest confidence)
            if character.name:
                name_lower = character.name.lower()
                if ref_lower == name_lower:
                    confidence = 1.0
                    match_type = "name"
                elif ref_lower in name_lower or name_lower in ref_lower:
                    confidence = 0.8
                    match_type = "name"
            
            # ID match
            if character.id.lower() == ref_lower:
                confidence = max(confidence, 0.9)
                match_type = "id"
            
            # Role match
            if character.role:
                role_lower = character.role.lower()
                if ref_lower in role_lower or role_lower in ref_lower:
                    confidence = max(confidence, 0.6)
                    match_type = "role"
            
            # Pronoun matching (context-dependent)
            if ref_lower in ["him", "he", "his"]:
                # Assume male character (could be enhanced with gender detection)
                if character.role and "main" in character.role.lower():
                    confidence = max(confidence, 0.5)
                    match_type = "pronoun"
            elif ref_lower in ["her", "she", "hers"]:
                # Assume female character
                if character.role and "main" in character.role.lower():
                    confidence = max(confidence, 0.5)
                    match_type = "pronoun"
            elif ref_lower in ["them", "they", "their", "theirs"]:
                # Multiple characters - match all main characters
                if character.role and "main" in character.role.lower():
                    confidence = max(confidence, 0.4)
                    match_type = "pronoun"
            
            # Generic references
            if ref_lower in ["protagonist", "main character", "lead", "singer", "artist"]:
                if character.role and "main" in character.role.lower():
                    confidence = max(confidence, 0.7)
                    match_type = "role"
            
            # Add match if confidence > 0
            if confidence > 0:
                matches.append(CharacterMatch(
                    character_id=character.id,
                    character_name=character.name or character.id,
                    confidence=confidence,
                    match_type=match_type or "unknown"
                ))
    
    # Remove duplicates (keep highest confidence)
    unique_matches = {}
    for match in matches:
        if match.character_id not in unique_matches:
            unique_matches[match.character_id] = match
        elif match.confidence > unique_matches[match.character_id].confidence:
            unique_matches[match.character_id] = match
    
    # Sort by confidence (highest first)
    sorted_matches = sorted(
        unique_matches.values(),
        key=lambda m: m.confidence,
        reverse=True
    )
    
    return sorted_matches


def parse_character_selection(
    instruction: str,
    scene_plan: ScenePlan,
    clip_index: Optional[int] = None
) -> List[str]:
    """
    Parse character selection from user instruction.
    
    This is the main entry point for character parsing.
    
    Args:
        instruction: User instruction (e.g., "make him lipsync", "sync Sarah's lips")
        scene_plan: ScenePlan with character definitions
        clip_index: Optional clip index to filter characters
        
    Returns:
        List of character IDs to target (empty if none found or "all characters")
    """
    if not instruction or not scene_plan.characters:
        return []
    
    # Extract references
    references = extract_character_references(instruction)
    
    if not references:
        # No specific character mentioned - could mean "all characters"
        # Check if instruction suggests "all" or "both"
        instruction_lower = instruction.lower()
        if "all" in instruction_lower or "both" in instruction_lower or "everyone" in instruction_lower:
            # Return all character IDs in this clip
            if clip_index is not None and scene_plan.clip_scripts:
                for script in scene_plan.clip_scripts:
                    if script.clip_index == clip_index:
                        return script.characters or []
            # Or all characters in scene plan
            return [char.id for char in scene_plan.characters]
        return []
    
    # Match references to characters
    matches = match_characters_to_references(references, scene_plan, clip_index)
    
    if not matches:
        logger.warning(
            f"No character matches found for references: {references}",
            extra={
                "instruction": instruction,
                "clip_index": clip_index,
                "available_characters": [char.id for char in scene_plan.characters]
            }
        )
        return []
    
    # Filter by confidence threshold (0.4 minimum)
    confident_matches = [m for m in matches if m.confidence >= 0.4]
    
    if not confident_matches:
        logger.warning(
            f"No confident character matches (threshold: 0.4)",
            extra={
                "instruction": instruction,
                "matches": [{"id": m.character_id, "confidence": m.confidence} for m in matches]
            }
        )
        return []
    
    # Return character IDs
    character_ids = [m.character_id for m in confident_matches]
    
    logger.info(
        f"Parsed character selection: {character_ids}",
        extra={
            "instruction": instruction,
            "clip_index": clip_index,
            "matches": [
                {
                    "character_id": m.character_id,
                    "name": m.character_name,
                    "confidence": m.confidence,
                    "match_type": m.match_type
                }
                for m in confident_matches
            ]
        }
    )
    
    return character_ids


def get_clip_characters(
    scene_plan: ScenePlan,
    clip_index: int
) -> List[Character]:
    """
    Get all characters that appear in a specific clip.
    
    Args:
        scene_plan: ScenePlan with character definitions
        clip_index: Clip index (0-based)
        
    Returns:
        List of Character objects appearing in the clip
    """
    if not scene_plan.clip_scripts:
        return []
    
    # Find clip script
    clip_script = None
    for script in scene_plan.clip_scripts:
        if script.clip_index == clip_index:
            clip_script = script
            break
    
    if not clip_script or not clip_script.characters:
        return []
    
    # Get character objects
    character_dict = {char.id: char for char in scene_plan.characters}
    clip_characters = [
        character_dict[char_id]
        for char_id in clip_script.characters
        if char_id in character_dict
    ]
    
    return clip_characters

