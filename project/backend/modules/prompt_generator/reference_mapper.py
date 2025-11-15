"""
Reference image mapping helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from shared.models.scene import ClipScript, ReferenceImages, ScenePlan


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

    character_reference_urls = [
        index.character_urls[char_id]
        for char_id in clip.characters
        if char_id in index.character_urls
    ]

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

    for clip in plan.clip_scripts:
        mapping[clip.clip_index] = map_clip_references(clip, index)

    return mapping

