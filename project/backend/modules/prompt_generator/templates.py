"""
Deterministic prompt templates used for LLM input and fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .prompt_synthesizer import ClipContext, build_clip_prompt
from .reference_mapper import ClipReferenceMapping


@dataclass
class BasePromptTemplate:
    clip_index: int
    prompt: str
    negative_prompt: str
    payload: Dict[str, Any]
    scene_reference_url: Optional[str]
    character_reference_urls: List[str]


def build_base_prompt(
    context: ClipContext,
    mapping: ClipReferenceMapping,
    style_keywords: List[str],
) -> BasePromptTemplate:
    prompt, negative_prompt = build_clip_prompt(context)
    payload = {
        "clip_index": context.clip_index,
        "visual_description": context.visual_description,
        "motion": context.motion,
        "camera_angle": context.camera_angle,
        "scene_id": mapping.scene_id,
        "character_ids": context.character_ids,
        "duration": context.duration,
        "beat_intensity": context.beat_intensity,
        "style_keywords": style_keywords,
        "reference_mode": mapping.reference_mode,
        "lyrics_context": context.lyrics_context,
        "draft_prompt": prompt,
    }

    return BasePromptTemplate(
        clip_index=context.clip_index,
        prompt=prompt,
        negative_prompt=negative_prompt,
        payload=payload,
        scene_reference_url=mapping.scene_reference_url,
        character_reference_urls=mapping.character_reference_urls,
    )


def build_base_prompt_batch(
    contexts: List[ClipContext],
    reference_mapping: Dict[int, ClipReferenceMapping],
    style_keywords: List[str],
) -> List[BasePromptTemplate]:
    batch: List[BasePromptTemplate] = []
    for context in contexts:
        mapping = reference_mapping.get(
            context.clip_index,
            ClipReferenceMapping(
                scene_id=None,
                character_ids=context.character_ids,
                scene_reference_url=None,
                character_reference_urls=[],
                reference_mode="text_only",
            ),
        )
        batch.append(build_base_prompt(context, mapping, style_keywords))
    return batch


def serialize_for_llm(base_prompts: List[BasePromptTemplate]) -> List[Dict[str, Any]]:
    return [item.payload for item in base_prompts]

