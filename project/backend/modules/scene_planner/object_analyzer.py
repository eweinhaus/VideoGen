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


# Object patterns to detect in clip descriptions and user input
OBJECT_PATTERNS = {
    # Musical instruments
    "guitar": r"\b(guitar|guitars|acoustic\s+guitar|electric\s+guitar|vintage\s+guitar|classical\s+guitar|bass\s+guitar)\b",
    "piano": r"\b(piano|keyboard|keys|grand\s+piano|upright\s+piano|electric\s+piano)\b",
    "drums": r"\b(drums|drum\s+set|drum\s+kit|drumkit|percussion)\b",
    "microphone": r"\b(microphone|mic|mics|wireless\s+mic|studio\s+mic)\b",
    "violin": r"\b(violin|fiddle|string\s+instrument)\b",
    "saxophone": r"\b(saxophone|sax|alto\s+sax|tenor\s+sax)\b",
    "trumpet": r"\b(trumpet|horn|brass\s+instrument)\b",
    "bass": r"\b(bass|bass\s+guitar|electric\s+bass|upright\s+bass)\b",

    # Vehicles
    "car": r"\b(car|automobile|vehicle|sedan|coupe|sports\s+car|vintage\s+car|classic\s+car)\b",
    "motorcycle": r"\b(motorcycle|bike|motorbike|chopper|harley|scooter)\b",
    "bicycle": r"\b(bicycle|bike|cycle|mountain\s+bike|road\s+bike)\b",
    "truck": r"\b(truck|pickup|pickup\s+truck|suv)\b",
    "boat": r"\b(boat|yacht|sailboat|speedboat|vessel)\b",
    "van": r"\b(van|minivan|camper\s+van)\b",

    # Jewelry/Accessories
    "necklace": r"\b(necklace|pendant|chain\s+necklace|choker|locket)\b",
    "ring": r"\b(ring|rings|wedding\s+ring|diamond\s+ring|engagement\s+ring)\b",
    "bracelet": r"\b(bracelet|bangle|cuff|wristband)\b",
    "watch": r"\b(watch|wristwatch|timepiece|smartwatch)\b",
    "earrings": r"\b(earrings|ear\s+rings|studs|hoops|dangly\s+earrings)\b",
    "chain": r"\b(chain|gold\s+chain|silver\s+chain|neck\s+chain)\b",

    # Electronics
    "phone": r"\b(phone|smartphone|mobile\s+phone|cellphone|cell\s+phone|iphone|android)\b",
    "laptop": r"\b(laptop|computer|notebook|macbook|pc)\b",
    "camera": r"\b(camera|cameras|video\s+camera|film\s+camera|dslr|mirrorless)\b",
    "headphones": r"\b(headphones|earbuds|ear\s+buds|earphones|airpods)\b",
    "speaker": r"\b(speaker|speakers|bluetooth\s+speaker|sound\s+system)\b",

    # Props
    "book": r"\b(book|books|novel|journal|notebook|diary)\b",
    "bottle": r"\b(bottle|bottles|wine\s+bottle|beer\s+bottle|water\s+bottle)\b",
    "glass": r"\b(glass|glasses|wine\s+glass|drinking\s+glass|champagne\s+glass)\b",
    "bag": r"\b(bag|backpack|purse|handbag|suitcase|briefcase|tote\s+bag)\b",
    "hat": r"\b(hat|cap|beanie|fedora|baseball\s+cap|snapback)\b",
    "jacket": r"\b(jacket|coat|blazer|leather\s+jacket|denim\s+jacket|bomber\s+jacket)\b",
    "sunglasses": r"\b(sunglasses|shades|aviators|wayfarers)\b",
    "umbrella": r"\b(umbrella|parasol)\b",
    "flower": r"\b(flower|flowers|bouquet|rose|tulip|daisy)\b",
    "guitar_case": r"\b(guitar\s+case|instrument\s+case|case)\b",
}


def extract_objects_from_user_input(user_prompt: str) -> List[Object]:
    """
    Extract object mentions from user input prompt before LLM generation.
    
    This allows us to pass explicit object hints to the LLM and ensure
    objects mentioned in user input are tracked even if they only appear once.
    
    Args:
        user_prompt: User's creative prompt text
        
    Returns:
        List of Object objects detected from user input (marked as primary)
    """
    detected_objects = []
    existing_ids = set()
    
    user_prompt_lower = user_prompt.lower()
    
    # Scan user prompt for object mentions
    for object_type, pattern in OBJECT_PATTERNS.items():
        if re.search(pattern, user_prompt_lower, re.IGNORECASE):
            # Generate object ID
            obj_id = _generate_object_id(object_type, existing_ids)
            existing_ids.add(obj_id)
            
            # Generate object profile (marked as primary since user mentioned it)
            obj = _generate_object_profile(obj_id, object_type)
            # Mark as primary since user explicitly mentioned it
            obj.importance = "primary"
            
            detected_objects.append(obj)
            
            logger.info(
                f"Extracted object '{object_type}' from user input",
                extra={
                    "object_id": obj_id,
                    "object_type": object_type,
                    "importance": "primary"
                }
            )
    
    return detected_objects


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
    
    # Build object_type to Object mapping for consolidation
    # Normalize object types to prevent duplicates (e.g., "truck", "pickup truck" → "truck")
    object_type_map = {}
    for obj in existing_objects:
        normalized_type = _normalize_object_type(obj.features.object_type)
        if normalized_type not in object_type_map:
            object_type_map[normalized_type] = obj
        # Prefer primary importance
        elif obj.importance == "primary" and object_type_map[normalized_type].importance != "primary":
            object_type_map[normalized_type] = obj

    # Scan all clips for object mentions
    object_mentions, clip_object_map = _scan_clips_for_objects(clip_scripts)

    # Generate new objects for recurring props
    new_objects = []
    for object_type, mention_count in object_mentions.items():
        # Normalize object type for comparison
        normalized_type = _normalize_object_type(object_type)
        
        # Check if an object of this type already exists (consolidation)
        if normalized_type in object_type_map:
            existing_obj = object_type_map[normalized_type]
            logger.debug(
                f"Object type '{object_type}' (normalized: '{normalized_type}') already exists as '{existing_obj.id}', skipping duplicate",
                extra={
                    "object_type": object_type,
                    "normalized_type": normalized_type,
                    "existing_object_id": existing_obj.id,
                    "mention_count": mention_count
                }
            )
            continue
        
        # Create objects for:
        # 1. Those mentioned in 2+ clips (recurring)
        # 2. Primary objects (even if single-clip, if marked as primary by LLM or user)
        # Check if this object type already exists as primary
        is_primary = any(
            _normalize_object_type(obj.features.object_type) == normalized_type
            for obj in existing_objects
            if obj.importance == "primary"
        )
        
        if mention_count < 2 and not is_primary:
            logger.debug(
                f"Object type '{object_type}' only mentioned {mention_count} time(s) and not primary, skipping",
                extra={"object_type": object_type, "mention_count": mention_count}
            )
            continue

        # Generate object ID
        obj_id = _generate_object_id(object_type, existing_ids)

        # Generate object profile
        obj = _generate_object_profile(obj_id, object_type)
        # If it's primary (from user input or LLM), mark it
        if is_primary:
            obj.importance = "primary"
        new_objects.append(obj)
        existing_ids.add(obj_id)
        # Add to type map to prevent further duplicates
        object_type_map[normalized_type] = obj

        logger.info(
            f"Generated object profile for '{object_type}'",
            extra={
                "object_id": obj_id,
                "object_type": object_type,
                "mention_count": mention_count,
                "importance": obj.importance
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


def _normalize_object_type(object_type: str) -> str:
    """
    Normalize object type to base type for consolidation.
    
    Maps variations like "pickup truck", "truck", "pickup" to base type "truck".
    
    Args:
        object_type: Object type string
        
    Returns:
        Normalized base object type
    """
    object_type_lower = object_type.lower()
    
    # Normalization mappings
    normalizations = {
        # Vehicles
        "pickup": "truck",
        "pickup truck": "truck",
        "suv": "truck",
        "automobile": "car",
        "vehicle": "car",
        "sedan": "car",
        "coupe": "car",
        "sports car": "car",
        "vintage car": "car",
        "classic car": "car",
        "motorbike": "motorcycle",
        "bike": "motorcycle",  # Context-dependent, but default to motorcycle
        "chopper": "motorcycle",
        "harley": "motorcycle",
        "scooter": "motorcycle",
        "yacht": "boat",
        "sailboat": "boat",
        "speedboat": "boat",
        "vessel": "boat",
        "minivan": "van",
        "camper van": "van",
        
        # Musical instruments
        "acoustic guitar": "guitar",
        "electric guitar": "guitar",
        "vintage guitar": "guitar",
        "classical guitar": "guitar",
        "bass guitar": "bass",
        "electric bass": "bass",
        "upright bass": "bass",
        "grand piano": "piano",
        "upright piano": "piano",
        "electric piano": "piano",
        "drum set": "drums",
        "drum kit": "drums",
        "drumkit": "drums",
        "wireless mic": "microphone",
        "studio mic": "microphone",
        "alto sax": "saxophone",
        "tenor sax": "saxophone",
        "string instrument": "violin",
        
        # Electronics
        "smartphone": "phone",
        "mobile phone": "phone",
        "cellphone": "phone",
        "cell phone": "phone",
        "iphone": "phone",
        "android": "phone",
        "computer": "laptop",
        "notebook": "laptop",
        "macbook": "laptop",
        "pc": "laptop",
        "video camera": "camera",
        "film camera": "camera",
        "dslr": "camera",
        "mirrorless": "camera",
        "earbuds": "headphones",
        "ear buds": "headphones",
        "earphones": "headphones",
        "airpods": "headphones",
        "bluetooth speaker": "speaker",
        "sound system": "speaker",
        
        # Accessories
        "pendant": "necklace",
        "chain necklace": "necklace",
        "choker": "necklace",
        "locket": "necklace",
        "wedding ring": "ring",
        "diamond ring": "ring",
        "engagement ring": "ring",
        "bangle": "bracelet",
        "cuff": "bracelet",
        "wristband": "bracelet",
        "wristwatch": "watch",
        "timepiece": "watch",
        "smartwatch": "watch",
        "ear rings": "earrings",
        "ear rings": "earrings",
        "studs": "earrings",
        "hoops": "earrings",
        "dangly earrings": "earrings",
        "gold chain": "chain",
        "silver chain": "chain",
        "neck chain": "chain",
        
        # Props
        "novel": "book",
        "journal": "book",
        "notebook": "book",
        "diary": "book",
        "wine bottle": "bottle",
        "beer bottle": "bottle",
        "water bottle": "bottle",
        "wine glass": "glass",
        "drinking glass": "glass",
        "champagne glass": "glass",
        "backpack": "bag",
        "purse": "bag",
        "handbag": "bag",
        "suitcase": "bag",
        "briefcase": "bag",
        "tote bag": "bag",
        "cap": "hat",
        "beanie": "hat",
        "fedora": "hat",
        "baseball cap": "hat",
        "snapback": "hat",
        "coat": "jacket",
        "blazer": "jacket",
        "leather jacket": "jacket",
        "denim jacket": "jacket",
        "bomber jacket": "jacket",
        "shades": "sunglasses",
        "aviators": "sunglasses",
        "wayfarers": "sunglasses",
        "parasol": "umbrella",
        "bouquet": "flower",
        "rose": "flower",
        "tulip": "flower",
        "daisy": "flower",
        "instrument case": "guitar_case",
    }
    
    # Check if exact match exists
    if object_type_lower in normalizations:
        return normalizations[object_type_lower]
    
    # Check if any normalization key is contained in the object type
    for key, base_type in normalizations.items():
        if key in object_type_lower:
            return base_type
    
    # Return normalized version (lowercase, spaces to underscores)
    return object_type_lower.replace(" ", "_")


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
