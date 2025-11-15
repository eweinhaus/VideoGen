import json
from pathlib import Path
from uuid import UUID

import pytest

from shared.models.scene import ReferenceImages, ScenePlan
from shared.models.video import ClipPrompts

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture()
def job_uuid() -> UUID:
    return UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture()
def sample_scene_plan() -> ScenePlan:
    data = _load_json("sample_scene_plan.json")
    data["job_id"] = data["job_id"]
    return ScenePlan.model_validate(data)


@pytest.fixture()
def sample_reference_images() -> ReferenceImages:
    data = _load_json("sample_reference_images.json")
    return ReferenceImages.model_validate(data)


@pytest.fixture()
def sample_clip_prompts() -> ClipPrompts:
    data = _load_json("sample_clip_prompts.json")
    return ClipPrompts.model_validate(data)

