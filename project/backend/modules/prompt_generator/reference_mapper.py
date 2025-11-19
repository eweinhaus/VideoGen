"""
Reference image mapping helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from shared.models.scene import ClipScript, ReferenceImages, ScenePlan
from shared.logging import get_logger

logger = get_logger("prompt_generator.reference_mapper")


@dataclass
class ReferenceIndex:
    scene_urls: Dict[str, str]
    character_urls: Dict[str, str]
    object_urls: Dict[str, str]
    status: str = "unknown"


@dataclass
class ClipReferenceMapping:
    scene_id: Optional[str]
    character_ids: List[str]
    object_ids: List[str]
    scene_reference_url: Optional[str]
    character_reference_urls: List[str]
    object_reference_urls: List[str]
    reference_mode: str


def build_reference_index(references: Optional[ReferenceImages]) -> ReferenceIndex:
    if references is None or references.status in {"failed"}:
        return ReferenceIndex(scene_urls={}, character_urls={}, object_urls={}, status="missing")

    scene_urls = {}
    for scene_ref in references.scene_references:
        if scene_ref.scene_id and scene_ref.scene_id not in scene_urls:
            scene_urls[scene_ref.scene_id] = scene_ref.image_url

    # Build character_urls to support multiple variations per character
    # character_urls will be a dict of character_id -> list of image URLs
    # For backward compatibility, we'll use Dict[str, str] but store all variations
    character_urls = {}
    for char_ref in references.character_references:
        if char_ref.character_id:
            # Reconstruct variation key: base_id for variation 0, base_id_var{N} for variations > 0
            if char_ref.variation_index == 0:
                variation_key = char_ref.character_id
            else:
                variation_key = f"{char_ref.character_id}_var{char_ref.variation_index}"
            character_urls[variation_key] = char_ref.image_url

    # Build object_urls to support multiple variations per object
    # Similar to character_urls, stores all variations with variation suffix keys
    object_urls = {}
    for obj_ref in references.object_references:
        if obj_ref.object_id:
            # Reconstruct variation key: base_id for variation 0, base_id_var{N} for variations > 0
            if obj_ref.variation_index == 0:
                variation_key = obj_ref.object_id
            else:
                variation_key = f"{obj_ref.object_id}_var{obj_ref.variation_index}"
            object_urls[variation_key] = obj_ref.image_url

    return ReferenceIndex(
        scene_urls=scene_urls,
        character_urls=character_urls,
        object_urls=object_urls,
        status=references.status,
    )


def map_clip_references(
    clip: ClipScript,
    index: ReferenceIndex,
    clip_index: int = 0,
) -> ClipReferenceMapping:
    scene_reference_url = None
    primary_scene_id = clip.scenes[0] if clip.scenes else None

    if primary_scene_id and primary_scene_id in index.scene_urls:
        scene_reference_url = index.scene_urls[primary_scene_id]
    elif primary_scene_id and index.status != "missing":
        # Log when scene ID doesn't have a reference (but references exist)
        logger.debug(
            f"Clip {clip.clip_index}: Scene ID '{primary_scene_id}' not found in reference images",
            extra={
                "clip_index": clip.clip_index,
                "scene_id": primary_scene_id,
                "available_scene_ids": list(index.scene_urls.keys())
            }
        )

    # Map character references - use variation 0 (frontal portrait) for each character
    # This ensures every character mentioned in the clip gets their reference image
    character_reference_urls = []
    missing_character_ids = []

    for char_id in clip.characters:
        # Find variation 0 (base character_id) for this character
        # Variation 0 is stored as the base character_id (without _var suffix)
        variation_0_url = None
        
        # First, try to find the exact match (variation 0)
        if char_id in index.character_urls:
            variation_0_url = index.character_urls[char_id]
            character_reference_urls.append(variation_0_url)
            
            logger.debug(
                f"Clip {clip_index}: Using variation 0 (frontal portrait) for character '{char_id}'",
                extra={
                    "clip_index": clip_index,
                    "character_id": char_id,
                    "variation_index": 0,
                    "variation_key": char_id
                }
            )
        else:
            # If variation 0 not found, check if any variations exist (for error reporting)
            char_variations = []
            for stored_char_id, url in index.character_urls.items():
                if stored_char_id.startswith(f"{char_id}_var"):
                    char_variations.append(stored_char_id)
            
            if char_variations:
                logger.warning(
                    f"Clip {clip_index}: Character '{char_id}' has variations but missing variation 0 (base)",
                    extra={
                        "clip_index": clip_index,
                        "character_id": char_id,
                        "available_variations": char_variations
                    }
                )
            else:
                missing_character_ids.append(char_id)
    
    if missing_character_ids and index.status != "missing":
        # Log when character IDs don't have references (but references exist)
        logger.debug(
            f"Clip {clip.clip_index}: Character IDs {missing_character_ids} not found in reference images",
            extra={
                "clip_index": clip.clip_index,
                "missing_character_ids": missing_character_ids,
                "available_character_ids": list(index.character_urls.keys())
            }
        )

    # Map object references with rotation through variations
    # Find all variations for each object and rotate based on clip_index
    object_reference_urls = []
    missing_object_ids = []
    
    # Get object IDs from clip (if objects field exists)
    clip_object_ids = getattr(clip, 'objects', [])
    
    for obj_id in clip_object_ids:
        # Find all variations for this object (obj_id, obj_id_var1, obj_id_var2, etc.)
        obj_variations = []
        for stored_obj_id, url in index.object_urls.items():
            # Match base object ID or variations
            if stored_obj_id == obj_id or stored_obj_id.startswith(f"{obj_id}_var"):
                obj_variations.append((stored_obj_id, url))

        if obj_variations:
            # Sort variations to ensure consistent ordering (var0, var1, var2, etc.)
            obj_variations.sort(key=lambda x: x[0])

            # Rotate through variations based on clip_index
            variation_index = clip_index % len(obj_variations)
            selected_variation_id, selected_url = obj_variations[variation_index]

            object_reference_urls.append(selected_url)

            logger.debug(
                f"Clip {clip_index}: Using variation {variation_index} for object '{obj_id}'",
                extra={
                    "clip_index": clip_index,
                    "object_id": obj_id,
                    "variation_index": variation_index,
                    "total_variations": len(obj_variations),
                    "selected_variation_id": selected_variation_id
                }
            )
        else:
            missing_object_ids.append(obj_id)
    
    if missing_object_ids and index.status != "missing":
        # Log when object IDs don't have references (but references exist)
        logger.debug(
            f"Clip {clip.clip_index}: Object IDs {missing_object_ids} not found in reference images",
            extra={
                "clip_index": clip.clip_index,
                "missing_object_ids": missing_object_ids,
                "available_object_ids": list(index.object_urls.keys())
            }
        )

    if scene_reference_url:
        reference_mode = "scene"
    elif character_reference_urls:
        reference_mode = "character"
    elif object_reference_urls:
        reference_mode = "object"
    else:
        reference_mode = "text_only"

    return ClipReferenceMapping(
        scene_id=primary_scene_id,
        character_ids=list(clip.characters),
        object_ids=list(clip_object_ids),
        scene_reference_url=scene_reference_url,
        character_reference_urls=character_reference_urls,
        object_reference_urls=object_reference_urls,
        reference_mode=reference_mode,
    )


def map_references(
    plan: ScenePlan,
    references: Optional[ReferenceImages],
) -> Dict[int, ClipReferenceMapping]:
    index = build_reference_index(references)
    mapping: Dict[int, ClipReferenceMapping] = {}

    # Build sets of valid scene, character, and object IDs from ScenePlan for validation
    valid_scene_ids = {scene.id for scene in plan.scenes}
    valid_character_ids = {char.id for char in plan.characters}
    valid_object_ids = {obj.id for obj in plan.objects} if plan.objects else set()

    # Validate that reference IDs match ScenePlan IDs
    if references and references.status not in {"failed"}:
        reference_scene_ids = {ref.scene_id for ref in references.scene_references if ref.scene_id}
        reference_character_ids = {ref.character_id for ref in references.character_references if ref.character_id}
        reference_object_ids = {ref.object_id for ref in references.object_references if ref.object_id}
        
        invalid_scene_refs = reference_scene_ids - valid_scene_ids
        invalid_char_refs = reference_character_ids - valid_character_ids
        invalid_obj_refs = reference_object_ids - valid_object_ids
        
        if invalid_scene_refs:
            logger.warning(
                f"Reference images contain scene IDs not in ScenePlan: {invalid_scene_refs}",
                extra={
                    "invalid_scene_ids": list(invalid_scene_refs),
                    "valid_scene_ids": list(valid_scene_ids)
                }
            )
        
        if invalid_char_refs:
            logger.warning(
                f"Reference images contain character IDs not in ScenePlan: {invalid_char_refs}",
                extra={
                    "invalid_character_ids": list(invalid_char_refs),
                    "valid_character_ids": list(valid_character_ids)
                }
            )
        
        if invalid_obj_refs:
            logger.warning(
                f"Reference images contain object IDs not in ScenePlan: {invalid_obj_refs}",
                extra={
                    "invalid_object_ids": list(invalid_obj_refs),
                    "valid_object_ids": list(valid_object_ids)
                }
            )

    for clip in plan.clip_scripts:
        # Validate clip references against ScenePlan
        invalid_clip_scenes = [sid for sid in clip.scenes if sid not in valid_scene_ids]
        invalid_clip_chars = [cid for cid in clip.characters if cid not in valid_character_ids]
        clip_object_ids = getattr(clip, 'objects', [])
        invalid_clip_objects = [oid for oid in clip_object_ids if oid not in valid_object_ids]

        if invalid_clip_scenes:
            logger.warning(
                f"Clip {clip.clip_index} references invalid scene IDs: {invalid_clip_scenes}",
                extra={
                    "clip_index": clip.clip_index,
                    "invalid_scene_ids": invalid_clip_scenes,
                    "valid_scene_ids": list(valid_scene_ids)
                }
            )

        if invalid_clip_chars:
            logger.warning(
                f"Clip {clip.clip_index} references invalid character IDs: {invalid_clip_chars}",
                extra={
                    "clip_index": clip.clip_index,
                    "invalid_character_ids": invalid_clip_chars,
                    "valid_character_ids": list(valid_character_ids)
                }
            )

        if invalid_clip_objects:
            logger.warning(
                f"Clip {clip.clip_index} references invalid object IDs: {invalid_clip_objects}",
                extra={
                    "clip_index": clip.clip_index,
                    "invalid_object_ids": invalid_clip_objects,
                    "valid_object_ids": list(valid_object_ids)
                }
            )

        # Pass clip_index for reference variation rotation
        mapping[clip.clip_index] = map_clip_references(clip, index, clip.clip_index)

    return mapping

