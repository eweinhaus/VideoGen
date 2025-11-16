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
    status: str = "unknown"


@dataclass
class ClipReferenceMapping:
    scene_id: Optional[str]
    character_ids: List[str]
    scene_reference_url: Optional[str]
    character_reference_urls: List[str]
    reference_mode: str


def build_reference_index(references: Optional[ReferenceImages]) -> ReferenceIndex:
    if references is None or references.status in {"failed"}:
        return ReferenceIndex(scene_urls={}, character_urls={}, status="missing")

    scene_urls = {}
    for scene_ref in references.scene_references:
        if scene_ref.scene_id and scene_ref.scene_id not in scene_urls:
            scene_urls[scene_ref.scene_id] = scene_ref.image_url

    character_urls = {}
    for char_ref in references.character_references:
        if char_ref.character_id and char_ref.character_id not in character_urls:
            character_urls[char_ref.character_id] = char_ref.image_url

    return ReferenceIndex(
        scene_urls=scene_urls,
        character_urls=character_urls,
        status=references.status,
    )


def map_clip_references(
    clip: ClipScript,
    index: ReferenceIndex,
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

    character_reference_urls = []
    missing_character_ids = []
    for char_id in clip.characters:
        if char_id in index.character_urls:
            character_reference_urls.append(index.character_urls[char_id])
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

    if scene_reference_url:
        reference_mode = "scene"
    elif character_reference_urls:
        reference_mode = "character"
    else:
        reference_mode = "text_only"

    return ClipReferenceMapping(
        scene_id=primary_scene_id,
        character_ids=list(clip.characters),
        scene_reference_url=scene_reference_url,
        character_reference_urls=character_reference_urls,
        reference_mode=reference_mode,
    )


def map_references(
    plan: ScenePlan,
    references: Optional[ReferenceImages],
) -> Dict[int, ClipReferenceMapping]:
    index = build_reference_index(references)
    mapping: Dict[int, ClipReferenceMapping] = {}

    # Build sets of valid scene and character IDs from ScenePlan for validation
    valid_scene_ids = {scene.id for scene in plan.scenes}
    valid_character_ids = {char.id for char in plan.characters}

    # Validate that reference IDs match ScenePlan IDs
    if references and references.status not in {"failed"}:
        reference_scene_ids = {ref.scene_id for ref in references.scene_references if ref.scene_id}
        reference_character_ids = {ref.character_id for ref in references.character_references if ref.character_id}
        
        invalid_scene_refs = reference_scene_ids - valid_scene_ids
        invalid_char_refs = reference_character_ids - valid_character_ids
        
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

    for clip in plan.clip_scripts:
        # Validate clip references against ScenePlan
        invalid_clip_scenes = [sid for sid in clip.scenes if sid not in valid_scene_ids]
        invalid_clip_chars = [cid for cid in clip.characters if cid not in valid_character_ids]
        
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
        
        mapping[clip.clip_index] = map_clip_references(clip, index)

    return mapping

