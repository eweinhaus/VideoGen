"""
High-level orchestration for prompt generation.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Union
from uuid import UUID

from shared.config import settings
from shared.errors import GenerationError, RetryableError, ValidationError
from shared.logging import get_logger
from shared.models.scene import ReferenceImages, ScenePlan
from shared.models.video import ClipPrompt, ClipPrompts

from .llm_client import LLMResult, optimize_prompts
from .prompt_synthesizer import ClipContext, compute_word_count
from .reference_mapper import map_references
from .style_synthesizer import ensure_global_consistency, extract_style_keywords
from .templates import BasePromptTemplate, build_base_prompt_batch, serialize_for_llm
from .validator import validate_clip_prompts

logger = get_logger("prompt_generator")


async def process(
    job_id: Union[str, UUID],
    plan: ScenePlan,
    references: Optional[ReferenceImages] = None,
) -> ClipPrompts:
    job_uuid = _normalize_job_id(job_id)

    if not plan.clip_scripts:
        raise ValidationError("Scene plan must include clip scripts", job_id=job_uuid)

    start_time = time.monotonic()

    style_keywords = extract_style_keywords(plan.style)
    reference_mapping = map_references(plan, references)
    clip_contexts = _build_clip_contexts(plan, reference_mapping, style_keywords)

    base_templates = build_base_prompt_batch(clip_contexts, reference_mapping, style_keywords)
    llm_result = await _maybe_optimize_with_llm(job_uuid, base_templates, style_keywords)

    final_prompts = (
        llm_result.prompts if llm_result else [template.prompt for template in base_templates]
    )
    final_prompts = ensure_global_consistency(final_prompts, style_keywords)

    clip_prompts = _assemble_clip_prompts(
        base_templates=base_templates,
        final_prompts=final_prompts,
        style_keywords=style_keywords,
        llm_result=llm_result,
    )

    clip_prompt_model = ClipPrompts(
        job_id=job_uuid,
        clip_prompts=clip_prompts,
        total_clips=len(clip_prompts),
        generation_time=time.monotonic() - start_time,
    )

    return validate_clip_prompts(job_uuid, plan, clip_prompt_model)


def _normalize_job_id(job_id: Union[str, UUID]) -> UUID:
    if isinstance(job_id, UUID):
        return job_id
    try:
        return UUID(str(job_id))
    except ValueError as exc:
        raise ValidationError("Invalid job_id", job_id=None) from exc


def _build_clip_contexts(
    plan: ScenePlan,
    reference_mapping,
    style_keywords: List[str],
) -> List[ClipContext]:
    characters = {char.id: char for char in plan.characters}
    scenes = {scene.id: scene for scene in plan.scenes}
    contexts: List[ClipContext] = []

    for script in plan.clip_scripts:
        mapping = reference_mapping.get(script.clip_index)
        scene_desc = [
            scenes[scene_id].description for scene_id in script.scenes if scene_id in scenes
        ]
        char_desc = [
            characters[char_id].description
            for char_id in script.characters
            if char_id in characters
        ]

        contexts.append(
            ClipContext(
                clip_index=script.clip_index,
                visual_description=script.visual_description,
                motion=script.motion,
                camera_angle=script.camera_angle,
                style_keywords=style_keywords,
                color_palette=plan.style.color_palette,
                mood=plan.style.mood,
                lighting=plan.style.lighting,
                cinematography=plan.style.cinematography,
                scene_reference_url=mapping.scene_reference_url if mapping else None,
                character_reference_urls=mapping.character_reference_urls if mapping else [],
                beat_intensity=script.beat_intensity,
                duration=script.end - script.start,
                scene_ids=list(script.scenes),
                character_ids=list(script.characters),
                scene_descriptions=scene_desc,
                character_descriptions=char_desc,
                primary_scene_id=mapping.scene_id if mapping else None,
                lyrics_context=script.lyrics_context,
            )
        )
    return contexts


async def _maybe_optimize_with_llm(
    job_id: UUID,
    base_templates: List[BasePromptTemplate],
    style_keywords: List[str],
) -> Optional[LLMResult]:
    if not settings.prompt_generator_use_llm:
        return None

    try:
        payload = serialize_for_llm(base_templates)
        return await optimize_prompts(job_id, payload, style_keywords)
    except (GenerationError, RetryableError) as exc:
        logger.warning(
            "LLM optimization unavailable, falling back to deterministic prompts",
            extra={"job_id": str(job_id), "error": str(exc)},
        )
        return None


def _assemble_clip_prompts(
    base_templates: List[BasePromptTemplate],
    final_prompts: List[str],
    style_keywords: List[str],
    llm_result: Optional[LLMResult],
) -> List[ClipPrompt]:
    clip_prompts: List[ClipPrompt] = []

    for template, prompt_text in zip(base_templates, final_prompts):
        prompt = prompt_text.strip() or template.prompt
        word_count = compute_word_count(prompt)

        metadata: Dict[str, Union[str, int, bool, List[str], None]] = {
            "word_count": word_count,
            "style_keywords": list(style_keywords),
            "scene_id": template.payload.get("scene_id"),
            "character_ids": template.payload.get("character_ids", []),
            "reference_mode": template.payload.get("reference_mode"),
            "validated": False,
            "llm_used": bool(llm_result),
            "llm_model": llm_result.model if llm_result else None,
        }
        if template.payload.get("lyrics_context"):
            metadata["lyrics_context"] = template.payload["lyrics_context"]

        clip_prompts.append(
            ClipPrompt(
                clip_index=template.clip_index,
                prompt=prompt,
                negative_prompt=template.negative_prompt,
                duration=float(template.payload["duration"]),
                scene_reference_url=template.scene_reference_url,
                character_reference_urls=template.character_reference_urls,
                metadata=metadata,
            )
        )

    return clip_prompts

