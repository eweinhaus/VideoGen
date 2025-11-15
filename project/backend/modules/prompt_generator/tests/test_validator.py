import pytest
from shared.models.video import ClipPrompt, ClipPrompts

from modules.prompt_generator.validator import validate_clip_prompts


def test_validate_clip_prompts_aligns_metadata(sample_scene_plan, job_uuid):
    clip_prompts = []
    for script in sample_scene_plan.clip_scripts:
        clip_prompts.append(
            ClipPrompt(
                clip_index=script.clip_index,
                prompt="short prompt text",
                negative_prompt="bad stuff",
                duration=script.end - script.start,
                scene_reference_url=None,
                character_reference_urls=[],
                metadata={},
            )
        )

    model = ClipPrompts(
        job_id=job_uuid,
        clip_prompts=clip_prompts,
        total_clips=len(clip_prompts),
        generation_time=0.1,
    )

    validated = validate_clip_prompts(job_uuid, sample_scene_plan, model)
    assert all(prompt.metadata["validated"] for prompt in validated.clip_prompts)
    assert validated.clip_prompts[0].metadata["style_keywords"] == []


def test_validate_clip_prompts_fails_on_missing_indices(sample_scene_plan, job_uuid):
    clip_prompt = ClipPrompt(
        clip_index=2,
        prompt="prompt",
        negative_prompt="bad",
        duration=5.0,
        scene_reference_url=None,
        character_reference_urls=[],
        metadata={"word_count": 1, "style_keywords": [], "scene_id": None, "character_ids": []},
    )
    model = ClipPrompts(
        job_id=job_uuid,
        clip_prompts=[clip_prompt],
        total_clips=1,
        generation_time=0.1,
    )

    with pytest.raises(Exception):
        validate_clip_prompts(job_uuid, sample_scene_plan, model)

