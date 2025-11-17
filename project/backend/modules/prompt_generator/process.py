"""
High-level orchestration for prompt generation.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Union, Any
from uuid import UUID

from shared.config import settings
from shared.errors import GenerationError, RetryableError, ValidationError
from shared.logging import get_logger
from shared.models.scene import ReferenceImages, ScenePlan
from shared.models.video import ClipPrompt, ClipPrompts

from .llm_client import LLMResult, optimize_prompts
from .prompt_synthesizer import (
    ClipContext,
    build_comprehensive_style_block,
    build_character_identity_block,
    build_lyrics_block,
    compute_word_count
)
from .reference_mapper import map_references
from .style_synthesizer import ensure_global_consistency, extract_style_keywords
from .templates import BasePromptTemplate, build_base_prompt_batch, serialize_for_llm
from .validator import validate_clip_prompts

logger = get_logger("prompt_generator")


async def process(
    job_id: Union[str, UUID],
    plan: ScenePlan,
    references: Optional[ReferenceImages] = None,
    beat_timestamps: Optional[List[float]] = None,
) -> ClipPrompts:
    job_uuid = _normalize_job_id(job_id)

    if not plan.clip_scripts:
        raise ValidationError("Scene plan must include clip scripts", job_id=job_uuid)

    start_time = time.monotonic()

    # Check if text-only mode is enabled (disables reference images)
    # ENV: USE_REFERENCE_IMAGES=true/false (default: true for backward compatibility)
    use_reference_images = settings.use_reference_images
    if not use_reference_images:
        logger.info(f"Text-only mode enabled (USE_REFERENCE_IMAGES=false), ignoring reference images")
        references = None

    style_keywords = extract_style_keywords(plan.style)
    reference_mapping = map_references(plan, references)
    clip_contexts = _build_clip_contexts(plan, reference_mapping, style_keywords, beat_timestamps)

    # Build base prompts WITHOUT comprehensive style block (for LLM optimization input)
    # The LLM will optimize the action/description, then we'll append structured style afterward
    base_templates = build_base_prompt_batch(
        clip_contexts,
        reference_mapping,
        style_keywords,
        include_comprehensive_style=False  # Action-only prompts for LLM
    )
    llm_result = await _maybe_optimize_with_llm(job_uuid, base_templates, style_keywords)

    # Get optimized or fallback prompts
    final_prompts = (
        llm_result.prompts if llm_result else [template.prompt for template in base_templates]
    )
    final_prompts = ensure_global_consistency(final_prompts, style_keywords)

    # PHASE 2: Append comprehensive style block AFTER LLM optimization
    # This ensures consistent structure across all clips (LLM can't rewrite it)
    final_prompts = _append_style_blocks(final_prompts, clip_contexts)

    # CHARACTER IDENTITY BLOCKS: Append character identity blocks AFTER style blocks
    # This ensures identical, immutable character descriptions across all clips
    final_prompts = _append_identity_blocks(final_prompts, clip_contexts)

    # LYRICS BLOCKS: Append lyrics blocks AFTER character identity blocks
    # This ensures exact lyrics (filtered to clip time range) are preserved and not modified by LLM
    final_prompts = _append_lyrics_blocks(final_prompts, clip_contexts)

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


def _append_style_blocks(prompts: List[str], contexts: List[ClipContext]) -> List[str]:
    """
    Append comprehensive style block to each prompt after LLM optimization.

    This ensures consistent structured style information across all clips,
    preventing the LLM from rewriting or omitting style details.

    Args:
        prompts: List of optimized prompts (action descriptions)
        contexts: List of ClipContext objects (for building style blocks)

    Returns:
        List of prompts with structured style blocks appended
    """
    if len(prompts) != len(contexts):
        logger.warning(
            "Prompt count mismatch when appending style blocks",
            extra={"prompt_count": len(prompts), "context_count": len(contexts)}
        )
        # Return as-is if mismatch (shouldn't happen, but safety)
        return prompts

    final_prompts = []
    for prompt, context in zip(prompts, contexts):
        # Build comprehensive style block for this clip
        style_block = build_comprehensive_style_block(context)

        if style_block:
            # Append style block with separator for clarity
            # Format: "action description. VISUAL STYLE: ..., MOOD: ..., etc."
            final_prompt = f"{prompt.strip()}. {style_block}"
        else:
            # No style block available, keep original prompt
            final_prompt = prompt

        final_prompts.append(final_prompt)

    logger.debug(
        "Appended comprehensive style blocks to all prompts",
        extra={"clip_count": len(final_prompts)}
    )

    return final_prompts


def _append_identity_blocks(prompts: List[str], contexts: List[ClipContext]) -> List[str]:
    """
    Append character identity blocks to prompts after LLM optimization.

    This mirrors _append_style_blocks() - ensures consistent character
    descriptions that the LLM cannot modify or paraphrase.

    Each clip gets the EXACT SAME character description, creating
    immutable identity across all video clips.

    Args:
        prompts: List of optimized prompts (with style blocks already appended)
        contexts: List of ClipContext objects (for building identity blocks)

    Returns:
        List of prompts with character identity blocks appended
    """
    if len(prompts) != len(contexts):
        logger.warning(
            "Prompt count mismatch when appending identity blocks",
            extra={"prompt_count": len(prompts), "context_count": len(contexts)}
        )
        # Return as-is if mismatch (shouldn't happen, but safety)
        return prompts

    final_prompts = []
    for prompt, context in zip(prompts, contexts):
        # Build character identity block for this clip
        identity_block = build_character_identity_block(context)

        if identity_block:
            # Append identity block after style block
            # Format: "[optimized action + style]. CHARACTER IDENTITY: ..."
            final_prompt = f"{prompt.strip()}\n\n{identity_block}"
        else:
            # No character descriptions available, keep original prompt
            final_prompt = prompt

        final_prompts.append(final_prompt)

    logger.debug(
        "Appended character identity blocks to all prompts",
        extra={"clip_count": len(final_prompts)}
    )

    return final_prompts


def _append_lyrics_blocks(prompts: List[str], contexts: List[ClipContext]) -> List[str]:
    """
    Append lyrics blocks to prompts after LLM optimization and character identity blocks.

    This mirrors _append_identity_blocks() - ensures exact lyrics (filtered to clip time range)
    are preserved and not modified by the LLM. Each clip gets only the lyrics spoken during
    that specific clip's time range, as extracted by the audio parser and filtered by the scene planner.

    Args:
        prompts: List of optimized prompts (with style and identity blocks already appended)
        contexts: List of ClipContext objects (for building lyrics blocks)

    Returns:
        List of prompts with lyrics blocks appended
    """
    if len(prompts) != len(contexts):
        logger.warning(
            "Prompt count mismatch when appending lyrics blocks",
            extra={"prompt_count": len(prompts), "context_count": len(contexts)}
        )
        # Return as-is if mismatch (shouldn't happen, but safety)
        return prompts

    final_prompts = []
    for prompt, context in zip(prompts, contexts):
        # Build lyrics block for this clip
        lyrics_block = build_lyrics_block(context)

        if lyrics_block:
            # Append lyrics block after character identity block
            # Format: "[optimized action + style + character]. LYRICS REFERENCE: \"...\""
            final_prompt = f"{prompt.strip()}\n\n{lyrics_block}"
        else:
            # No lyrics for this clip, keep original prompt
            final_prompt = prompt

        final_prompts.append(final_prompt)

    logger.debug(
        "Appended lyrics blocks to all prompts",
        extra={"clip_count": len(final_prompts), "clips_with_lyrics": sum(1 for ctx in contexts if ctx.lyrics_context)}
    )

    return final_prompts


def extract_clip_beats(clip_start: float, clip_end: float, all_beat_timestamps: List[float]) -> Dict[str, Any]:
    """
    Extract beat timestamps within a clip's time range.

    Args:
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        all_beat_timestamps: All beat timestamps in the audio

    Returns:
        Dictionary with beat metadata for this clip
    """
    if not all_beat_timestamps:
        return {
            "beat_timestamps_in_clip": [],
            "primary_beat_time": None,
            "beat_count": 0
        }

    # Extract beats within this clip's time range
    clip_beats = [
        beat - clip_start  # Normalize to clip-relative time (0 = clip start)
        for beat in all_beat_timestamps
        if clip_start <= beat <= clip_end
    ]

    # Find primary beat (first beat, or middle if multiple)
    primary_beat = None
    if clip_beats:
        # Use middle beat if we have multiple, otherwise first
        middle_index = len(clip_beats) // 2
        primary_beat = clip_beats[middle_index]

    return {
        "beat_timestamps_in_clip": clip_beats,
        "primary_beat_time": primary_beat,
        "beat_count": len(clip_beats)
    }


def _build_clip_contexts(
    plan: ScenePlan,
    reference_mapping,
    style_keywords: List[str],
    beat_timestamps: Optional[List[float]] = None,
) -> List[ClipContext]:
    characters = {char.id: char for char in plan.characters}
    scenes = {scene.id: scene for scene in plan.scenes}
    contexts: List[ClipContext] = []

    for script in plan.clip_scripts:
        mapping = reference_mapping.get(script.clip_index)
        scene_desc = [
            scenes[scene_id].description for scene_id in script.scenes if scene_id in scenes
        ]

        # CHARACTER CONSISTENCY FIX: Pass Character objects (not just descriptions)
        # This allows build_character_identity_block to format from structured features
        clip_characters = [
            characters[char_id]
            for char_id in script.characters
            if char_id in characters
        ]

        # Keep legacy char_desc for backward compatibility
        char_desc = [
            characters[char_id].description
            for char_id in script.characters
            if char_id in characters and characters[char_id].description
        ]

        # Extract beat timing metadata for this clip
        beat_metadata = extract_clip_beats(
            script.start,
            script.end,
            beat_timestamps or []
        )

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
                character_descriptions=char_desc,  # Keep for backward compatibility
                primary_scene_id=mapping.scene_id if mapping else None,
                lyrics_context=script.lyrics_context,
                beat_metadata=beat_metadata,  # Add beat metadata
                # PHASE 2: Pass full style descriptions from scene planner
                visual_style_full=plan.style.visual_style,
                mood_full=plan.style.mood,
                lighting_full=plan.style.lighting,
                cinematography_full=plan.style.cinematography,
                color_palette_full=plan.style.color_palette,
                # CHARACTER CONSISTENCY FIX: Pass Character objects for structured formatting
                characters=clip_characters,
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

        metadata: Dict[str, Union[str, int, bool, List[str], None, Dict[str, Any]]] = {
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
        if template.payload.get("beat_metadata"):
            metadata["beat_metadata"] = template.payload["beat_metadata"]

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

