import json
from types import SimpleNamespace

import pytest

from modules.prompt_generator import llm_client


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    async def create(self, **kwargs):
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response))


@pytest.mark.asyncio
async def test_optimize_prompts_returns_llm_result(monkeypatch, job_uuid):
    payload = [{"clip_index": 0, "draft_prompt": "Base prompt"}]
    response_content = json.dumps({"prompts": [{"clip_index": 0, "prompt": "Optimized prompt"}]})
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )

    async def fake_track_cost(**kwargs):
        return None

    monkeypatch.setattr(llm_client, "_get_client", lambda: _FakeClient(fake_response))
    monkeypatch.setattr(llm_client.cost_tracker, "track_cost", fake_track_cost)

    result = await llm_client.optimize_prompts(job_uuid, payload, ["cyberpunk"])
    assert result.prompts[0] == "Optimized prompt"
    assert result.model == "gpt-4o"

