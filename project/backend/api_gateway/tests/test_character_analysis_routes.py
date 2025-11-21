import asyncio
import json
import pytest
import httpx
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks

from api_gateway.main import app
from api_gateway.dependencies import get_current_user
from api_gateway.services.character_analysis_service import get_analysis_job, process_analysis_job
from uuid import UUID


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    """Override the get_current_user dependency and rate limiter for all tests."""
    async def _mock_get_current_user(*args, **kwargs):
        return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "user@example.com"}
    
    async def _mock_rate_limit(*args, **kwargs):
        return None  # Rate limiter doesn't return anything
    
    app.dependency_overrides[get_current_user] = _mock_get_current_user
    
    # Mock rate limiter
    from api_gateway.services import rate_limiter
    monkeypatch.setattr(rate_limiter, "check_rate_limit", _mock_rate_limit)
    
    # Override BackgroundTasks to ensure it's properly injected
    # TestClient should handle this automatically, but we make it explicit
    def _get_background_tasks():
        return BackgroundTasks()
    
    # Note: BackgroundTasks is not a dependency, it's automatically injected by FastAPI
    # TestClient handles it automatically, so we don't need to override it
    
    yield
    # Clean up after test
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_env_vars):
    """Create test client. TestClient automatically handles BackgroundTasks."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_get_character_analysis_endpoint(test_env_vars, monkeypatch):
    """Test GET endpoint for character analysis results."""
    from modules.character_analyzer import vision as vision_mod
    from api_gateway.services.character_analysis_service import create_analysis_job, process_analysis_job

    # Mock analyzer
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

    # Create and process job directly (bypass BackgroundTasks)
    job_id = await create_analysis_job(
        user_id="00000000-0000-0000-0000-000000000001",
        image_url="https://example.com/test.png",
        analysis_version="v1",
        background_tasks=None,
    )

    # Test GET endpoint
    from httpx import ASGITransport
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        resp = await async_client.get(
            f"/api/v1/upload/character/analyze/{job_id}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "analysis" in data, f"Expected 'analysis' in response, got: {data}"
        assert data["analysis"]["age_range"] == "mid_20s"
        assert data["used_cache"] in (False, True)


