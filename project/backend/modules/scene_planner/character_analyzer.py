"""
Character analyzer for finding implicit/background characters in clip scripts.

Scans clip descriptions to identify mentioned characters that don't have profiles yet,
then generates character profiles for them to ensure consistency across clips.
"""

import re
from typing import List, Dict, Set, Tuple
from shared.logging import get_logger
from shared.models.scene import Character, CharacterFeatures, ClipScript

logger = get_logger("scene_planner")


# Character role patterns to detect in clip descriptions
CHARACTER_PATTERNS = {
    "bartender": r"\b(bartender|barkeeper|bar\s+tender)\b",
    "crowd": r"\b(crowd|audience|onlookers?|spectators?|people\s+in\s+the\s+background)\b",
    "band": r"\b(band\s+member|guitarist|drummer|bassist|keyboardist|musician|singer|vocalist)\b",
    "passerby": r"\b(passerby|passersby|pedestrian|walker|person\s+walking)\b",
    "waiter": r"\b(waiter|waitress|server|attendant)\b",
    "patron": r"\b(patron|customer|guest|visitor)\b",
    "friend": r"\b(friend|companion|buddy|pal)\b",
    "stranger": r"\b(stranger|unknown\s+person|mysterious\s+figure)\b",
}


def analyze_clips_for_implicit_characters(
    clip_scripts: List[ClipScript],
    existing_characters: List[Character]
) -> List[Character]:
    """
    Analyze clip scripts to find implicit/background characters that need profiles.

    Scans all clip visual descriptions for mentions of character roles (bartender, crowd, etc.)
    and generates character profiles for any that don't already exist.

    Args:
        clip_scripts: List of ClipScript objects with visual descriptions
        existing_characters: List of Character objects already created

    Returns:
        List of new Character objects for implicit/background characters
    """
    # Get existing character IDs and roles
    existing_ids = {char.id for char in existing_characters}
    existing_roles = {char.role.lower() for char in existing_characters}

    # Scan all clips for character mentions
    character_mentions = _scan_clips_for_characters(clip_scripts)

    # Generate new characters for implicit roles
    new_characters = []
    for role, mention_count in character_mentions.items():
        # Check if we already have a character for this role
        if role in existing_roles:
            logger.debug(f"Character role '{role}' already exists, skipping")
            continue

        # Only create characters for roles mentioned in 2+ clips (recurring)
        # Exception: bartender, band members always created if mentioned
        always_create = role in ["bartender", "band_guitarist", "band_drummer", "band_bassist"]
        if mention_count < 2 and not always_create:
            logger.debug(
                f"Character role '{role}' only mentioned {mention_count} time(s), skipping",
                extra={"role": role, "mention_count": mention_count}
            )
            continue

        # Generate character ID
        char_id = _generate_character_id(role, existing_ids)

        # Generate character profile
        character = _generate_character_profile(char_id, role)
        new_characters.append(character)
        existing_ids.add(char_id)

        logger.info(
            f"Generated implicit character profile for '{role}'",
            extra={
                "character_id": char_id,
                "role": role,
                "mention_count": mention_count
            }
        )

    return new_characters


def _scan_clips_for_characters(clip_scripts: List[ClipScript]) -> Dict[str, int]:
    """
    Scan clip scripts for character mentions.

    Args:
        clip_scripts: List of ClipScript objects

    Returns:
        Dictionary mapping character role to number of mentions
    """
    character_mentions: Dict[str, int] = {}

    for script in clip_scripts:
        description = script.visual_description.lower()

        # Check each character pattern
        for role, pattern in CHARACTER_PATTERNS.items():
            if re.search(pattern, description, re.IGNORECASE):
                # Special handling for band members (extract specific role)
                if role == "band":
                    if "guitarist" in description or "guitar" in description:
                        character_mentions["band_guitarist"] = character_mentions.get("band_guitarist", 0) + 1
                    if "drummer" in description or "drum" in description:
                        character_mentions["band_drummer"] = character_mentions.get("band_drummer", 0) + 1
                    if "bassist" in description or "bass" in description:
                        character_mentions["band_bassist"] = character_mentions.get("band_bassist", 0) + 1
                    if "singer" in description or "vocalist" in description:
                        character_mentions["band_vocalist"] = character_mentions.get("band_vocalist", 0) + 1
                else:
                    character_mentions[role] = character_mentions.get(role, 0) + 1

    return character_mentions


def _generate_character_id(role: str, existing_ids: Set[str]) -> str:
    """
    Generate unique character ID for a role.

    Args:
        role: Character role (e.g., "bartender", "crowd")
        existing_ids: Set of existing character IDs

    Returns:
        Unique character ID (e.g., "bartender_1", "crowd_1")
    """
    # Try base ID first
    base_id = role.lower().replace(" ", "_")
    if base_id not in existing_ids:
        return base_id

    # Add counter if base ID exists
    counter = 1
    while f"{base_id}_{counter}" in existing_ids:
        counter += 1

    return f"{base_id}_{counter}"


def _generate_character_profile(char_id: str, role: str) -> Character:
    """
    Generate character profile with features for an implicit character.

    Creates a Character object with structured features based on the character's role.

    Args:
        char_id: Character ID (e.g., "bartender_1")
        role: Character role (e.g., "bartender")

    Returns:
        Character object with features and description
    """
    # Generate character name from role
    char_name = _role_to_name(role)

    # Generate features based on role
    features = _generate_features_for_role(role)

    # Determine character role category
    if role in ["bartender", "waiter", "patron"]:
        role_category = "background"
    elif role.startswith("band_"):
        role_category = "supporting"
    elif role in ["crowd", "passerby"]:
        role_category = "background"
    else:
        role_category = "supporting"

    # Generate description from features for backward compatibility
    description = _build_description_from_features(char_name, features, role_category)

    return Character(
        id=char_id,
        name=char_name,
        role=role_category,
        features=features,
        description=description
    )


def _build_description_from_features(name: str, features: CharacterFeatures, role: str) -> str:
    """
    Build description string from structured features for backward compatibility.
    
    Args:
        name: Character name
        features: CharacterFeatures object
        role: Character role category
        
    Returns:
        Formatted description string
    """
    return f"{name} ({role}) - FIXED CHARACTER IDENTITY:\n- Hair: {features.hair}\n- Face: {features.face}\n- Eyes: {features.eyes}\n- Clothing: {features.clothing}\n- Accessories: {features.accessories}\n- Build: {features.build}\n- Age: {features.age}"


def _role_to_name(role: str) -> str:
    """
    Convert role to character name.

    Args:
        role: Character role (e.g., "bartender", "band_guitarist")

    Returns:
        Character name (e.g., "Bartender", "Guitarist")
    """
    # Handle band members
    if role.startswith("band_"):
        instrument = role.replace("band_", "").replace("_", " ").title()
        return instrument

    # Handle other roles
    return role.replace("_", " ").title()


def _generate_features_for_role(role: str) -> CharacterFeatures:
    """
    Generate character features based on role.

    Creates plausible, specific features for background characters
    based on their role to ensure consistency.

    Args:
        role: Character role (e.g., "bartender", "crowd")

    Returns:
        CharacterFeatures object with all 7 features
    """
    # Default features (generic background character)
    features = {
        "hair": "short dark brown hair, neat style",
        "face": "medium skin tone, oval face shape, clean shaven",
        "eyes": "brown eyes, medium eyebrows",
        "clothing": "casual button-up shirt, dark jeans",
        "accessories": "None",
        "build": "average build, approximately 5'10\" height",
        "age": "appears late 30s"
    }

    # Customize features based on role
    if role == "bartender":
        features.update({
            "hair": "short gray hair with receding hairline",
            "face": "fair skin tone, weathered features, full gray beard",
            "eyes": "blue eyes, bushy gray eyebrows",
            "clothing": "white button-up shirt, black vest, black slacks",
            "accessories": "None",
            "build": "stocky build, approximately 5'10\" height",
            "age": "appears late 50s"
        })
    elif role == "band_guitarist":
        features.update({
            "hair": "shoulder-length black hair, slightly wavy, middle part",
            "face": "tan skin tone, angular face shape, light stubble",
            "eyes": "dark brown eyes, thick eyebrows",
            "clothing": "black leather jacket, dark gray t-shirt, black jeans, black boots",
            "accessories": "silver chain necklace, black wristband on right wrist",
            "build": "lean build, approximately 5'11\" height, narrow shoulders",
            "age": "appears mid-20s"
        })
    elif role == "band_drummer":
        features.update({
            "hair": "short spiky blonde hair, styled with gel",
            "face": "fair skin tone, round face shape, clean shaven",
            "eyes": "green eyes, thin eyebrows",
            "clothing": "white tank top, dark blue jeans, red sneakers",
            "accessories": "black sweatband on forehead, silver earring in left ear",
            "build": "muscular build, approximately 6'0\" height, broad shoulders",
            "age": "appears early 30s"
        })
    elif role == "band_bassist":
        features.update({
            "hair": "long black hair in dreadlocks, tied back with red band",
            "face": "dark brown skin tone, oval face shape, goatee",
            "eyes": "dark brown eyes, thick eyebrows",
            "clothing": "red flannel shirt unbuttoned, black t-shirt underneath, dark jeans",
            "accessories": "multiple silver rings on both hands, black beanie",
            "build": "tall lean build, approximately 6'2\" height, lanky frame",
            "age": "appears late 20s"
        })
    elif role == "crowd":
        features.update({
            "hair": "medium length brown hair, casual style",
            "face": "medium skin tone, friendly features, slight smile",
            "eyes": "hazel eyes, expressive eyebrows",
            "clothing": "casual graphic t-shirt, blue jeans, sneakers",
            "accessories": "baseball cap, smartwatch on left wrist",
            "build": "average build, approximately 5'9\" height",
            "age": "appears mid-20s"
        })
    elif role == "patron":
        features.update({
            "hair": "short auburn hair, neat professional style",
            "face": "fair skin tone, square jaw, clean shaven",
            "eyes": "gray eyes, medium eyebrows",
            "clothing": "collared button-up shirt, khaki pants, brown leather shoes",
            "accessories": "silver watch on left wrist, wedding ring",
            "build": "athletic build, approximately 5'11\" height, fit frame",
            "age": "appears early 40s"
        })

    return CharacterFeatures(**features)


def update_clip_scripts_with_characters(
    clip_scripts: List[ClipScript],
    all_characters: List[Character]
) -> List[ClipScript]:
    """
    Update clip scripts to include implicit character IDs.

    Scans clip descriptions and adds character IDs for any mentioned characters.

    Args:
        clip_scripts: List of ClipScript objects
        all_characters: List of all Character objects (including new implicit ones)

    Returns:
        Updated list of ClipScript objects with character IDs added
    """
    # Create mapping of role keywords to character IDs
    role_to_char_id = {}
    for char in all_characters:
        # Use character name or ID as keyword
        keyword = char.name.lower() if char.name else char.id
        role_to_char_id[keyword] = char.id

        # Also map common role patterns
        if char.role == "background":
            if "bartender" in char.id:
                role_to_char_id["bartender"] = char.id
            elif "patron" in char.id:
                role_to_char_id["patron"] = char.id
            elif "crowd" in char.id:
                role_to_char_id["crowd"] = char.id

    # Update each clip script
    updated_scripts = []
    for script in clip_scripts:
        description = script.visual_description.lower()

        # Find all mentioned characters in this clip
        mentioned_char_ids = set(script.characters)  # Start with existing characters

        for keyword, char_id in role_to_char_id.items():
            if keyword in description:
                mentioned_char_ids.add(char_id)

        # Create updated script with new character IDs
        updated_script = ClipScript(
            clip_index=script.clip_index,
            start=script.start,
            end=script.end,
            visual_description=script.visual_description,
            motion=script.motion,
            camera_angle=script.camera_angle,
            characters=list(mentioned_char_ids),
            scenes=script.scenes,
            lyrics_context=script.lyrics_context,
            beat_intensity=script.beat_intensity
        )
        updated_scripts.append(updated_script)

    return updated_scripts
