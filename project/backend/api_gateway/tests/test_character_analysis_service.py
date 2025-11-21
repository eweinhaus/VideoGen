"""
Tests for character analysis service (bypasses BackgroundTasks issue).
"""

import pytest
from uuid import UUID
from modules.character_analyzer import vision as vision_mod
from api_gateway.services.character_analysis_service import (
    create_analysis_job,
    get_analysis_job,
    process_analysis_job,
)


@pytest.mark.asyncio
async def test_create_and_process_analysis_job(test_env_vars, monkeypatch):
    """Test creating and processing an analysis job."""
    # Mock analyzer to avoid real GPT-4V calls - must patch before import
    from modules.character_analyzer import vision as vision_mod
    
    async def _fake_analyze(image_url: str, job_id, user_id=None, use_mock=None):
        return {
            "analysis": {
                "age_range": "mid_20s",
                "gender_presentation": "masculine",
                "hair_color": "dark_brown",
                "hair_style": "short_wavy",
                "eye_color": "blue",
                "build": "athletic",
                "height_bucket": "tall",
                "skin_tone": "fair",
                "style": "photo_realistic",
                "distinctive_features": [],
                "clothing": ["hoodie", "jeans"],
                "confidence": 0.85,
                "confidence_binned": "high",
                "confidence_per_attribute": {"hair_color": 0.9},
                "analysis_version": "v1",
            },
            "warnings": [],
            "used_cache": False,
        }

    monkeypatch.setattr(vision_mod, "analyze_character_image", _fake_analyze)

    # Create job without BackgroundTasks (process inline)
    job_id = await create_analysis_job(
        user_id="00000000-0000-0000-0000-000000000001",
        image_url="https://example.com/test.png",
        analysis_version="v1",
        background_tasks=None,  # Process inline for testing
    )

    assert job_id is not None
    assert isinstance(job_id, str)

    # Get job result
    job = await get_analysis_job(job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert "result" in job
    assert "analysis" in job["result"]
    assert job["result"]["analysis"]["age_range"] == "mid_20s"
    assert job["result"]["used_cache"] in (False, True)


@pytest.mark.asyncio
async def test_get_analysis_job_not_found(test_env_vars):
    """Test getting a non-existent analysis job."""
    job = await get_analysis_job("00000000-0000-0000-0000-000000000000")
    assert job is None

