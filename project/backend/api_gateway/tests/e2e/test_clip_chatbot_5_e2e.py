"""
End-to-end tests for Clip Chatbot Part 5: Style Transfer & Multi-Clip Intelligence.

Tests:
1. Style transfer endpoint
2. AI-powered prompt suggestions
3. Multi-clip instructions
4. Integration with clip regeneration
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status
from decimal import Decimal

from api_gateway.main import app
from shared.models.video import Clips, Clip, ClipPrompts, ClipPrompt
from shared.models.audio import AudioAnalysis, SongStructure, ClipBoundary, Mood, EnergyLevel


@pytest.fixture
def client(test_env_vars):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_job_id():
    """Sample job ID for testing."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_clips():
    """Sample clips data for testing."""
    return Clips(
        job_id=uuid.uuid4(),
        clips=[
            Clip(
                clip_index=0,
                video_url="https://example.com/clip0.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            ),
            Clip(
                clip_index=1,
                video_url="https://example.com/clip1.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            ),
            Clip(
                clip_index=2,
                video_url="https://example.com/clip2.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            ),
        ],
        total_clips=3,
        successful_clips=3,
        failed_clips=0,
        total_cost=Decimal("0.30"),
        total_generation_time=90.0
    )


@pytest.fixture
def sample_clip_prompts():
    """Sample clip prompts for testing."""
    return ClipPrompts(
        job_id=uuid.uuid4(),
        clip_prompts=[
            ClipPrompt(
                clip_index=0,
                prompt="A cyberpunk street scene with neon lights",
                negative_prompt="blurry, low quality",
                duration=5.0
            ),
            ClipPrompt(
                clip_index=1,
                prompt="A futuristic cityscape at night",
                negative_prompt="blurry, low quality",
                duration=5.0
            ),
            ClipPrompt(
                clip_index=2,
                prompt="A dark alley with glowing signs",
                negative_prompt="blurry, low quality",
                duration=5.0
            ),
        ],
        total_clips=3,
        generation_time=90.0
    )


@pytest.fixture
def sample_audio_analysis():
    """Sample audio analysis for testing."""
    return AudioAnalysis(
        job_id=uuid.uuid4(),
        bpm=120.0,
        duration=15.0,
        beat_timestamps=[0.0, 0.5, 1.0, 1.5, 2.0],
        song_structure=[
            SongStructure(type="verse", start=0.0, end=5.0, energy=EnergyLevel.MEDIUM),
            SongStructure(type="chorus", start=5.0, end=10.0, energy=EnergyLevel.HIGH),
            SongStructure(type="verse", start=10.0, end=15.0, energy=EnergyLevel.MEDIUM),
        ],
        mood=Mood(primary="energetic", confidence=0.8, energy_level=EnergyLevel.HIGH),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=5.0, duration=5.0),
            ClipBoundary(start=5.0, end=10.0, duration=5.0),
            ClipBoundary(start=10.0, end=15.0, duration=5.0),
        ]
    )


@pytest.mark.e2e
def test_style_transfer_endpoint_success(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test successful style transfer."""
    from api_gateway.dependencies import get_current_user
    from api_gateway.main import app
    
    async def mock_get_current_user():
        return {"user_id": sample_user_id}
    
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    try:
        # Mock verify_job_ownership
        async def mock_verify_job_ownership(job_id, current_user):
            return {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
        
        # Mock transfer_style
        async def mock_transfer_style(job_id, source_clip_index, target_clip_index, transfer_options, additional_instruction=None):
            return "A cyberpunk street scene with neon lights, vibrant colors, cinematic lighting, energetic mood"
        
        with patch("api_gateway.routes.clips.verify_job_ownership", side_effect=mock_verify_job_ownership), \
             patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
             patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
             patch("api_gateway.routes.clips.transfer_style", side_effect=mock_transfer_style), \
             patch("api_gateway.routes.clips.acquire_job_lock", new_callable=AsyncMock, return_value=True), \
             patch("api_gateway.routes.clips.regenerate_clip_with_recomposition") as mock_regenerate:
                
            # Mock regeneration result
            from modules.clip_regenerator.process import RegenerationResult
            mock_result = RegenerationResult(
                clip=Clip(
                    clip_index=1,
                    video_url="https://example.com/regenerated_clip.mp4",
                    target_duration=5.0,
                    actual_duration=5.0,
                    duration_diff=0.0,
                    status="success",
                    cost=Decimal("0.10"),
                    generation_time=30.0
                ),
                modified_prompt="A cyberpunk street scene with neon lights, vibrant colors, cinematic lighting",
                template_used=None,
                cost=Decimal("0.10"),
                video_output=None
            )
            mock_regenerate.return_value = mock_result
            
            response = client.post(
                f"/api/v1/jobs/{sample_job_id}/clips/style-transfer",
                json={
                    "source_clip_index": 0,
                    "target_clip_index": 1,
                    "transfer_options": {
                        "color_palette": True,
                        "lighting": True,
                        "mood": True
                    }
                },
                headers={"Authorization": "Bearer mock_token"}
            )
    
        if response.status_code != status.HTTP_200_OK:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == status.HTTP_200_OK, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "regeneration_id" in data
        assert "estimated_cost" in data
        assert "status" in data
        assert data["status"] == "completed"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.e2e
def test_style_transfer_endpoint_invalid_clip_indices(
    client, sample_job_id, sample_user_id, sample_clips
):
    """Test style transfer with invalid clip indices."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips):
                # Test invalid source clip index
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/style-transfer",
                    json={
                        "source_clip_index": 10,  # Invalid
                        "target_clip_index": 1,
                        "transfer_options": {}
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid" in response.json()["detail"].lower() or "out of range" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_suggestions_endpoint_success(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test successful AI suggestions retrieval."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            # Mock data loaders
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips.generate_suggestions") as mock_generate:
                
                # Mock suggestions
                mock_generate.return_value = [
                    {
                        "id": "suggestion_1",
                        "type": "enhancement",
                        "suggestion": "Add more dynamic camera movement",
                        "reasoning": "The clip could benefit from more cinematic motion",
                        "estimated_cost": 0.10
                    },
                    {
                        "id": "suggestion_2",
                        "type": "style",
                        "suggestion": "Increase color saturation",
                        "reasoning": "The colors appear muted",
                        "estimated_cost": 0.10
                    }
                ]
                
                response = client.get(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/suggestions",
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) == 2
    assert all("id" in s for s in data["suggestions"])
    assert all("type" in s for s in data["suggestions"])
    assert all("suggestion" in s for s in data["suggestions"])


@pytest.mark.e2e
def test_suggestions_endpoint_rate_limiting(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test suggestions endpoint rate limiting."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips._check_suggestions_rate_limit") as mock_rate_limit:
                
                # Mock rate limit exceeded
                from fastapi import HTTPException
                mock_rate_limit.side_effect = HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Suggestions rate limit exceeded: 10 requests per job per hour"
                )
                
                response = client.get(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/suggestions",
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    # Should return rate limit error
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "rate limit" in response.json()["detail"].lower() or "too many" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_suggestions_endpoint_caching(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test suggestions endpoint caching."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            cached_suggestions = [
                {
                    "id": "cached_1",
                    "type": "enhancement",
                    "suggestion": "Cached suggestion",
                    "reasoning": "From cache",
                    "estimated_cost": 0.10
                }
            ]
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips._check_suggestions_rate_limit"), \
                 patch("api_gateway.routes.clips.RedisClient") as mock_redis_class:
                
                # Mock cache hit
                mock_redis_instance = AsyncMock()
                mock_redis_instance.get_json = AsyncMock(return_value=cached_suggestions)
                mock_redis_class.return_value = mock_redis_instance
                
                response = client.get(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/suggestions",
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["id"] == "cached_1"


@pytest.mark.e2e
def test_apply_suggestion_endpoint_success(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test successful suggestion application."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            cached_suggestions = [
                {
                    "id": "suggestion_1",
                    "type": "enhancement",
                    "suggestion": "Add more dynamic camera movement",
                    "reasoning": "The clip could benefit from more cinematic motion",
                    "estimated_cost": 0.10
                }
            ]
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips._check_suggestions_rate_limit"), \
                 patch("api_gateway.routes.clips.RedisClient") as mock_redis_class, \
                 patch("api_gateway.routes.clips.regenerate_clip") as mock_regenerate:
                
                # Mock cached suggestion
                mock_redis_instance = AsyncMock()
                mock_redis_instance.get_json = AsyncMock(return_value=cached_suggestions)
                mock_redis_class.return_value = mock_redis_instance
                
                # Mock regeneration result
                from modules.clip_regenerator.process import RegenerationResult
                mock_result = RegenerationResult(
                    clip=Clip(
                        clip_index=0,
                        video_url="https://example.com/new_clip.mp4",
                        target_duration=5.0,
                        actual_duration=5.0,
                        duration_diff=0.0,
                        status="success",
                        cost=Decimal("0.10"),
                        generation_time=30.0
                    ),
                    modified_prompt="A cyberpunk street scene with neon lights, dynamic camera movement",
                    template_used=None,
                    cost=Decimal("0.10")
                )
                mock_regenerate.return_value = mock_result
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/suggestions/suggestion_1/apply",
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "regeneration_id" in data
    assert "estimated_cost" in data
    assert "status" in data


@pytest.mark.e2e
def test_multi_clip_instruction_parse_all_clips(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test multi-clip instruction parsing for 'all clips'."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "make all clips brighter",
                        "preview_only": True
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "clip_instructions" in data
    assert len(data["clip_instructions"]) == 3  # All 3 clips
    assert all("clip_index" in ci for ci in data["clip_instructions"])
    assert all("instruction" in ci for ci in data["clip_instructions"])
    assert all("brighter" in ci["instruction"].lower() for ci in data["clip_instructions"])


@pytest.mark.e2e
def test_multi_clip_instruction_parse_specific_clips(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test multi-clip instruction parsing for specific clips."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "make clips 1 and 3 darker",
                        "preview_only": True
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "clip_instructions" in data
    assert len(data["clip_instructions"]) == 2  # Clips 1 and 3 (indices 0 and 2)
    clip_indices = [ci["clip_index"] for ci in data["clip_instructions"]]
    assert 0 in clip_indices
    assert 2 in clip_indices


@pytest.mark.e2e
def test_multi_clip_instruction_parse_range(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test multi-clip instruction parsing for range notation."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "make clips 1-2 more colorful",
                        "preview_only": True
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "clip_instructions" in data
    assert len(data["clip_instructions"]) == 2  # Clips 1-2 (indices 0-1)
    clip_indices = [ci["clip_index"] for ci in data["clip_instructions"]]
    assert 0 in clip_indices
    assert 1 in clip_indices


@pytest.mark.e2e
def test_multi_clip_instruction_parse_chorus(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts, sample_audio_analysis
):
    """Test multi-clip instruction parsing for audio context (chorus)."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips.load_audio_data_from_job_stages", return_value=sample_audio_analysis):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "make the chorus clips brighter",
                        "preview_only": True
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "clip_instructions" in data
    # Should match clip 2 (index 1) which overlaps with chorus (5.0-10.0)
    assert len(data["clip_instructions"]) >= 1
    clip_indices = [ci["clip_index"] for ci in data["clip_instructions"]]
    assert 1 in clip_indices  # Clip 2 (index 1) overlaps with chorus


@pytest.mark.e2e
def test_multi_clip_instruction_apply(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test multi-clip instruction application (not preview)."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips.regenerate_clip") as mock_regenerate:
                
                # Mock regeneration results
                from modules.clip_regenerator.process import RegenerationResult
                mock_results = [
                    RegenerationResult(
                        clip=Clip(
                            clip_index=i,
                            video_url=f"https://example.com/new_clip{i}.mp4",
                            target_duration=5.0,
                            actual_duration=5.0,
                            duration_diff=0.0,
                            status="success",
                            cost=Decimal("0.10"),
                            generation_time=30.0
                        ),
                        modified_prompt=f"Modified prompt {i}",
                        template_used=None,
                        cost=Decimal("0.10")
                    )
                    for i in range(2)  # For clips 1 and 3
                ]
                mock_regenerate.side_effect = mock_results
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "make clips 1 and 3 darker",
                        "preview_only": False
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "regeneration_ids" in data
    assert len(data["regeneration_ids"]) == 2
    assert "total_estimated_cost" in data
    assert "total_estimated_time" in data


@pytest.mark.e2e
def test_multi_clip_instruction_invalid_instruction(
    client, sample_job_id, sample_user_id, sample_clips
):
    """Test multi-clip instruction with invalid/empty instruction."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips):
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/multi-clip-instruction",
                    json={
                        "instruction": "",  # Empty instruction
                        "preview_only": True
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower() or "instruction" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_end_to_end_workflow_style_transfer_to_regeneration(
    client, sample_job_id, sample_user_id, sample_clips, sample_clip_prompts
):
    """Test complete workflow: style transfer -> apply -> regeneration."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            with patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=sample_clips), \
                 patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=sample_clip_prompts), \
                 patch("api_gateway.routes.clips.transfer_style") as mock_transfer, \
                 patch("api_gateway.routes.clips.regenerate_clip") as mock_regenerate:
                
                # Step 1: Style transfer
                mock_transfer.return_value = {
                    "modified_prompt": "A futuristic cityscape at night, vibrant colors, cinematic lighting",
                    "style_keywords": {
                        "color": ["vibrant colors"],
                        "lighting": ["cinematic lighting"],
                        "mood": []
                    },
                    "estimated_cost": 0.10
                }
                
                transfer_response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/style-transfer",
                    json={
                        "source_clip_index": 0,
                        "target_clip_index": 1,
                        "transfer_options": {
                            "color_palette": True,
                            "lighting": True,
                            "mood": False
                        }
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
                
                assert transfer_response.status_code == status.HTTP_200_OK
                
                # Step 2: Regenerate with modified prompt
                from modules.clip_regenerator.process import RegenerationResult
                mock_result = RegenerationResult(
                    clip=Clip(
                        clip_index=1,
                        video_url="https://example.com/regenerated_clip.mp4",
                        target_duration=5.0,
                        actual_duration=5.0,
                        duration_diff=0.0,
                        status="success",
                        cost=Decimal("0.10"),
                        generation_time=30.0
                    ),
                    modified_prompt="A futuristic cityscape at night, vibrant colors, cinematic lighting",
                    template_used=None,
                    cost=Decimal("0.10")
                )
                mock_regenerate.return_value = mock_result
                
                regenerate_response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/1/regenerate",
                    json={
                        "instruction": "apply style from clip 1",
                        "conversation_history": []
                    },
                    headers={"Authorization": "Bearer mock_token"}
                )
                
                # Verify regeneration was called
                assert regenerate_response.status_code in [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]

