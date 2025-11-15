import pytest

from modules.prompt_generator import process as prompt_process
from modules.prompt_generator.llm_client import LLMResult


@pytest.mark.asyncio
async def test_process_generates_prompts_without_llm(monkeypatch, job_uuid, sample_scene_plan):
    monkeypatch.setattr(prompt_process.settings, "prompt_generator_use_llm", False)

    result = await prompt_process.process(job_uuid, sample_scene_plan, None)
    assert result.total_clips == len(sample_scene_plan.clip_scripts)
    assert all(prompt.metadata["validated"] for prompt in result.clip_prompts)


@pytest.mark.asyncio
async def test_process_uses_llm_results(monkeypatch, job_uuid, sample_scene_plan, sample_reference_images):
    async def fake_optimize(job_id, payload, keywords):
        prompts = [f"LLM prompt {idx}" for idx in range(len(payload))]
        return LLMResult(prompts=prompts, model="gpt-4o", input_tokens=10, output_tokens=10)

    monkeypatch.setattr(prompt_process.settings, "prompt_generator_use_llm", True)
    monkeypatch.setattr(prompt_process, "optimize_prompts", fake_optimize)

    result = await prompt_process.process(job_uuid, sample_scene_plan, sample_reference_images)
    assert result.clip_prompts[0].metadata["llm_used"] is True
    assert result.clip_prompts[0].prompt.startswith("LLM prompt 0")

