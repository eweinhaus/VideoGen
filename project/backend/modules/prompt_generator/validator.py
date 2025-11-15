"""
Validation utilities for ClipPrompts output.
"""

from __future__ import annotations

from typing import List
from urllib.parse import urlparse
from uuid import UUID

from shared.errors import GenerationError, ValidationError
from shared.logging import get_logger
from shared.models.scene import ScenePlan
from shared.models.video import ClipPrompt, ClipPrompts

logger = get_logger("prompt_generator")


def validate_clip_prompts(
    job_id: UUID,
    plan: ScenePlan,
    clip_prompts: ClipPrompts,
) -> ClipPrompts:
    clip_count = len(plan.clip_scripts)
    if clip_count == 0:
        raise ValidationError("Scene plan must include clip scripts", job_id=job_id)

    prompts = clip_prompts.clip_prompts
    if len(prompts) != clip_count:
        raise GenerationError(
            f"Expected {clip_count} prompts, received {len(prompts)}",
            job_id=job_id,
        )

    _validate_indices(prompts, job_id)

    style_reference = None
    for clip_script, clip_prompt in zip(plan.clip_scripts, prompts):
        expected_duration = clip_script.end - clip_script.start
        if abs(clip_prompt.duration - expected_duration) > 0.25:
            clip_prompt.duration = expected_duration

        if clip_prompt.scene_reference_url and not _is_valid_url(clip_prompt.scene_reference_url):
            raise GenerationError("Invalid scene reference URL", job_id=job_id)

        invalid_char_urls = [
            url for url in clip_prompt.character_reference_urls if not _is_valid_url(url)
        ]
        if invalid_char_urls:
            raise GenerationError("Invalid character reference URL", job_id=job_id)

        metadata = clip_prompt.metadata or {}
        word_count = metadata.get("word_count")
        if not word_count:
            word_count = len(clip_prompt.prompt.split())
            metadata["word_count"] = word_count
        if word_count > 200:
            metadata["word_count"] = 200
            words = clip_prompt.prompt.split()
            clip_prompt.prompt = " ".join(words[:200]) + "..."

        style_keywords = metadata.get("style_keywords")
        if style_keywords:
            if style_reference is None:
                style_reference = style_keywords
            elif style_reference != style_keywords:
                metadata["style_keywords"] = style_reference
        else:
            metadata["style_keywords"] = style_reference or []

        metadata.setdefault("scene_id", clip_script.scenes[0] if clip_script.scenes else None)
        metadata.setdefault("character_ids", list(clip_script.characters))
        metadata["validated"] = True
        clip_prompt.metadata = metadata

    clip_prompts.clip_prompts = prompts
    return clip_prompts


def normalize_negative_prompt(negative_prompt: str) -> str:
    if not negative_prompt:
        return negative_prompt
    tokens = [token.strip() for token in negative_prompt.split(",") if token.strip()]
    seen = set()
    deduped: List[str] = []
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(token)
    return ", ".join(deduped)


def _validate_indices(prompts: List[ClipPrompt], job_id: UUID) -> None:
    indices = sorted(prompt.clip_index for prompt in prompts)
    expected = list(range(len(prompts)))
    if indices != expected:
        raise GenerationError(
            f"Clip indices must be contiguous starting at 0, received {indices}",
            job_id=job_id,
        )


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False

