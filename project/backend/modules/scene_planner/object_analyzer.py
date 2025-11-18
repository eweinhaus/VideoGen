"""
Object analyzer for finding recurring objects/props in clip scripts.

Scans clip descriptions to identify objects mentioned in multiple clips,
then generates object profiles to ensure visual consistency across clips.
"""

import re
from typing import List, Dict, Set, Tuple
from shared.logging import get_logger
from shared.models.scene import Object, ObjectFeatures, ClipScript

logger = get_logger("scene_planner.object_analyzer")


# Object patterns to detect in clip descriptions
OBJECT_PATTERNS = {
    # Musical instruments
    "guitar": r"\b(guitar|guitars|acoustic\s+guitar|electric\s+guitar)\b",
    "piano": r"\b(piano|keyboard|keys|grand\s+piano)\b",
    "drums": r"\b(drums|drum\s+set|drum\s+kit)\b",
    "microphone": r"\b(microphone|mic|mics)\b",
    "violin": r"\b(violin|fiddle)\b",
    "saxophone": r"\b(saxophone|sax)\b",

    # Vehicles
    "car": r"\b(car|automobile|vehicle|sedan|coupe)\b",
    "motorcycle": r"\b(motorcycle|bike|motorbike|chopper)\b",
    "bicycle": r"\b(bicycle|bike|cycle)\b",
    "truck": r"\b(truck|pickup)\b",
    "boat": r"\b(boat|yacht|sailboat)\b",

    # Jewelry/Accessories
    "necklace": r"\b(necklace|pendant|chain\s+necklace)\b",
    "ring": r"\b(ring|rings|wedding\s+ring|diamond\s+ring)\b",
    "bracelet": r"\b(bracelet|bangle)\b",
    "watch": r"\b(watch|wristwatch|timepiece)\b",
    "earrings": r"\b(earrings|ear\s+rings|studs)\b",

    # Electronics
    "phone": r"\b(phone|smartphone|mobile\s+phone|cellphone|cell\s+phone)\b",
    "laptop": r"\b(laptop|computer|notebook)\b",
    "camera": r"\b(camera|cameras|video\s+camera|film\s+camera)\b",
    "headphones": r"\b(headphones|earbuds|ear\s+buds)\b",

    # Props
    "book": r"\b(book|books|novel|journal)\b",
    "bottle": r"\b(bottle|bottles|wine\s+bottle|beer\s+bottle)\b",
    "glass": r"\b(glass|glasses|wine\s+glass|drinking\s+glass)\b",
    "bag": r"\b(bag|backpack|purse|handbag|suitcase)\b",
    "hat": r"\b(hat|cap|beanie|fedora)\b",
    "jacket": r"\b(jacket|coat|blazer)\b",
    "sunglasses": r"\b(sunglasses|shades)\b",
}


def analyze_clips_for_objects(
    clip_scripts: List[ClipScript],
    existing_objects: List[Object]
) -> Tuple[List[Object], List[ClipScript]]:
    """
    Analyze clip scripts to find recurring objects that need profiles.

    Scans all clip visual descriptions for mentions of objects (guitar, car, etc.)
    and generates object profiles for any that appear in 2+ clips (or are flagged as primary).

    Args:
        clip_scripts: List of ClipScript objects with visual descriptions
        existing_objects: List of Object objects already created

    Returns:
        Tuple of (new_objects, updated_clip_scripts)
        - new_objects: List of new Object objects for recurring props
        - updated_clip_scripts: Clip scripts with object IDs added
    """
    # Get existing object IDs
    existing_ids = {obj.id for obj in existing_objects}

    # Scan all clips for object mentions
    object_mentions, clip_object_map = _scan_clips_for_objects(clip_scripts)

    # Generate new objects for recurring props
    new_objects = []
    for object_type, mention_count in object_mentions.items():
        # Only create objects for those mentioned in 2+ clips (recurring)
        # Exception: primary objects (user can manually specify later)
        if mention_count < 2:
            logger.debug(
                f"Object type '{object_type}' only mentioned {mention_count} time(s), skipping",
                extra={"object_type": object_type, "mention_count": mention_count}
            )
            continue

        # Generate object ID
        obj_id = _generate_object_id(object_type, existing_ids)

        # Generate object profile
        obj = _generate_object_profile(obj_id, object_type)
        new_objects.append(obj)
        existing_ids.add(obj_id)

        logger.info(
            f"Generated object profile for '{object_type}'",
            extra={
                "object_id": obj_id,
                "object_type": object_type,
                "mention_count": mention_count
            }
        )

    # Update clip scripts with object IDs
    updated_clip_scripts = _update_clip_scripts_with_objects(
        clip_scripts,
        new_objects,
        clip_object_map
    )

    return new_objects, updated_clip_scripts


def _scan_clips_for_objects(
    clip_scripts: List[ClipScript]
) -> Tuple[Dict[str, int], Dict[int, Set[str]]]:
    """
    Scan clip scripts for object mentions.

    Args:
        clip_scripts: List of ClipScript objects

    Returns:
        Tuple of:
        - Dictionary mapping object type to number of clips mentioning it
        - Dictionary mapping clip_index to set of object types mentioned
    """
    object_mentions: Dict[str, int] = {}
    clip_object_map: Dict[int, Set[str]] = {}

    for clip in clip_scripts:
        description_lower = clip.visual_description.lower()
        objects_in_clip = set()

        # Check each object pattern
        for object_type, pattern in OBJECT_PATTERNS.items():
            if re.search(pattern, description_lower, re.IGNORECASE):
                objects_in_clip.add(object_type)

        # Count unique clips mentioning each object
        for obj_type in objects_in_clip:
            object_mentions[obj_type] = object_mentions.get(obj_type, 0) + 1

        # Track which objects appear in which clip
        if objects_in_clip:
            clip_object_map[clip.clip_index] = objects_in_clip

    logger.debug(
        f"Scanned {len(clip_scripts)} clips for objects",
        extra={
            "total_clips": len(clip_scripts),
            "objects_found": len(object_mentions),
            "clips_with_objects": len(clip_object_map)
        }
    )

    return object_mentions, clip_object_map


def _generate_object_id(object_type: str, existing_ids: Set[str]) -> str:
    """
    Generate a unique object ID.

    Args:
        object_type: Type of object (e.g., "guitar", "car")
        existing_ids: Set of existing object IDs

    Returns:
        Unique object ID (e.g., "guitar_1", "vintage_car")
    """
    # Try base ID first
    base_id = object_type.replace(" ", "_").lower()
    if base_id not in existing_ids:
        return base_id

    # Add numeric suffix if needed
    counter = 1
    while f"{base_id}_{counter}" in existing_ids:
        counter += 1

    return f"{base_id}_{counter}"


def _generate_object_profile(obj_id: str, object_type: str) -> Object:
    """
    Generate an object profile with default features.

    This creates a generic object profile. The LLM should ideally generate
    more specific features based on the actual video context.

    Args:
        obj_id: Object ID
        object_type: Type of object (e.g., "guitar", "car")

    Returns:
        Object with default ObjectFeatures
    """
    # Object-specific defaults
    defaults = {
        # Musical instruments
        "guitar": {
            "name": "Guitar",
            "object_type": "acoustic guitar",
            "color": "natural wood finish with honey sunburst",
            "material": "solid spruce top, mahogany back and sides, rosewood fingerboard",
            "distinctive_features": "worn finish around soundhole, vintage tuning pegs, mother-of-pearl fret markers",
            "size": "full-size dreadnought body (approximately 20 inches long)",
            "condition": "well-used but maintained, authentic wear patterns"
        },
        "piano": {
            "name": "Piano",
            "object_type": "grand piano",
            "color": "glossy black lacquer finish",
            "material": "polished ebony wood, ivory keys",
            "distinctive_features": "ornate music stand, three pedals, brand emblem on fallboard",
            "size": "full concert grand (9 feet long)",
            "condition": "pristine, professionally maintained"
        },
        # Vehicles
        "car": {
            "name": "Car",
            "object_type": "sports car",
            "color": "cherry red metallic paint",
            "material": "steel body, chrome accents, leather interior",
            "distinctive_features": "racing stripes, custom wheels, tinted windows",
            "size": "two-door coupe (approximately 15 feet long)",
            "condition": "pristine, freshly detailed"
        },
        "motorcycle": {
            "name": "Motorcycle",
            "object_type": "cruiser motorcycle",
            "color": "matte black with chrome accents",
            "material": "steel frame, chrome exhaust pipes, leather seat",
            "distinctive_features": "custom handlebars, saddlebags, chrome headlight",
            "size": "full-size cruiser (approximately 7 feet long)",
            "condition": "well-maintained, some road wear"
        },
        # Jewelry
        "necklace": {
            "name": "Necklace",
            "object_type": "pendant necklace",
            "color": "gold with blue gemstone",
            "material": "18k gold chain, sapphire pendant",
            "distinctive_features": "filigree detailing, antique clasp, intricate setting",
            "size": "20-inch chain with 1-inch pendant",
            "condition": "vintage, heirloom quality"
        },
        # Electronics
        "phone": {
            "name": "Smartphone",
            "object_type": "smartphone",
            "color": "matte black with silver trim",
            "material": "aluminum frame, glass screen and back",
            "distinctive_features": "cracked screen protector, custom case with stickers",
            "size": "6-inch screen diagonal",
            "condition": "used, shows signs of daily wear"
        },
        # Props
        "bottle": {
            "name": "Bottle",
            "object_type": "wine bottle",
            "color": "dark green glass with gold foil label",
            "material": "heavy glass, cork stopper",
            "distinctive_features": "vintage label, wax seal, embossed design",
            "size": "standard 750ml wine bottle",
            "condition": "aged, dusty, unopened"
        },
    }

    # Get defaults for this object type, or use generic defaults
    obj_defaults = defaults.get(object_type, {
        "name": object_type.replace("_", " ").title(),
        "object_type": object_type,
        "color": "unspecified color",
        "material": "unspecified material",
        "distinctive_features": "generic design",
        "size": "standard size",
        "condition": "good condition"
    })

    features = ObjectFeatures(
        object_type=obj_defaults["object_type"],
        color=obj_defaults["color"],
        material=obj_defaults["material"],
        distinctive_features=obj_defaults["distinctive_features"],
        size=obj_defaults["size"],
        condition=obj_defaults["condition"]
    )

    return Object(
        id=obj_id,
        name=obj_defaults["name"],
        features=features,
        importance="secondary"  # Default to secondary, LLM can upgrade to primary
    )


def _update_clip_scripts_with_objects(
    clip_scripts: List[ClipScript],
    objects: List[Object],
    clip_object_map: Dict[int, Set[str]]
) -> List[ClipScript]:
    """
    Update clip scripts with object IDs.

    Args:
        clip_scripts: Original clip scripts
        objects: List of Object objects
        clip_object_map: Mapping of clip_index to object types mentioned

    Returns:
        Updated clip scripts with object IDs
    """
    # Build object type to ID mapping
    object_type_to_id = {
        obj.features.object_type: obj.id
        for obj in objects
    }

    # Also check base object type (e.g., "guitar" maps to "acoustic guitar")
    for obj in objects:
        # Extract base type (e.g., "acoustic guitar" -> "guitar")
        obj_type = obj.features.object_type
        for base_type in OBJECT_PATTERNS.keys():
            if base_type in obj_type or obj_type.endswith(base_type):
                object_type_to_id[base_type] = obj.id

    updated_clips = []
    for clip in clip_scripts:
        # Get objects mentioned in this clip
        mentioned_types = clip_object_map.get(clip.clip_index, set())

        # Map to object IDs
        object_ids = [
            object_type_to_id[obj_type]
            for obj_type in mentioned_types
            if obj_type in object_type_to_id
        ]

        # Update clip with object IDs
        if object_ids:
            # Create updated clip with objects
            updated_clip = clip.model_copy(update={"objects": object_ids})
            updated_clips.append(updated_clip)
            logger.debug(
                f"Added {len(object_ids)} objects to clip {clip.clip_index}",
                extra={"clip_index": clip.clip_index, "objects": object_ids}
            )
        else:
            # No changes
            updated_clips.append(clip)

    return updated_clips


def update_clip_scripts_with_objects(
    clip_scripts: List[ClipScript],
    objects: List[Object]
) -> List[ClipScript]:
    """
    Public helper to update clip scripts with object IDs from existing objects.

    Useful when objects are generated by LLM and we need to map them to clips.

    Args:
        clip_scripts: List of ClipScript objects
        objects: List of Object objects

    Returns:
        Updated clip scripts with object IDs
    """
    _, clip_object_map = _scan_clips_for_objects(clip_scripts)
    return _update_clip_scripts_with_objects(clip_scripts, objects, clip_object_map)
