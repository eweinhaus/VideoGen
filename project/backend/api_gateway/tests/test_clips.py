"""
Tests for clips API endpoint.

Tests GET /api/v1/jobs/{job_id}/clips endpoint with authentication and authorization.
"""
import pytest
import json
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status

from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_job_id():
    """Sample job ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return str(uuid4())


@pytest.fixture
def mock_jwt_token(sample_user_id):
    """Mock JWT token for testing."""
    # In real tests, this would be a valid JWT token
    # For testing, we'll mock the get_current_user dependency
    return "mock_jwt_token"


@pytest.fixture
def sample_clips_metadata():
    """Sample clips metadata structure."""
    return {
        "clips": {
            "job_id": str(uuid4()),
            "clips": [
                {
                    "clip_index": 0,
                    "video_url": "https://storage.supabase.co/video-clips/job/clip_0.mp4",
                    "actual_duration": 12.5,
                    "target_duration": 12.0,
                    "original_target_duration": 12.0,
                    "duration_diff": 0.5,
                    "status": "success",
                    "cost": "0.10",
                    "retry_count": 0,
                    "generation_time": 45.2
                }
            ],
            "total_clips": 1,
            "successful_clips": 1,
            "failed_clips": 0,
            "total_cost": "0.10",
            "total_generation_time": 45.2
        }
    }


@pytest.fixture
def sample_audio_metadata():
    """Sample audio parser metadata with lyrics and clip boundaries."""
    return {
        "lyrics": [
            {"text": "In", "timestamp": 0.5, "confidence": 0.95},
            {"text": "the", "timestamp": 0.7, "confidence": 0.94},
            {"text": "city", "timestamp": 1.0, "confidence": 0.96}
        ],
        "clip_boundaries": [
            {"start": 0.0, "end": 12.5, "duration": 12.5}
        ]
    }


def test_clips_endpoint_no_auth(client, sample_job_id):
    """Test clips endpoint without authentication."""
    response = client.get(f"/api/v1/jobs/{sample_job_id}/clips")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_clips_endpoint_job_not_found(client, sample_job_id, sample_user_id):
    """Test clips endpoint with non-existent job."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database to return empty result
        mock_db = AsyncMock()
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_table)
        mock_table.eq = MagicMock(return_value=mock_table)
        mock_table.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_db.table = MagicMock(return_value=mock_table)
        
        with patch("api_gateway.routes.clips.db_client", mock_db):
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_clips_endpoint_wrong_user(client, sample_job_id, sample_user_id):
    """Test clips endpoint with job belonging to different user."""
    different_user_id = str(uuid4())
    
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database to return job with different user_id
        mock_db = AsyncMock()
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_table)
        mock_table.eq = MagicMock(return_value=mock_table)
        mock_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": different_user_id,
            "status": "completed"
        }]))
        mock_db.table = MagicMock(return_value=mock_table)
        
        with patch("api_gateway.routes.clips.db_client", mock_db):
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "denied" in response.json()["detail"].lower() or "access" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_clips_endpoint_job_not_completed(client, sample_job_id, sample_user_id):
    """Test clips endpoint with job not completed."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database to return job with status "processing"
        mock_db = AsyncMock()
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_table)
        mock_table.eq = MagicMock(return_value=mock_table)
        mock_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": sample_user_id,
            "status": "processing"
        }]))
        mock_db.table = MagicMock(return_value=mock_table)
        
        with patch("api_gateway.routes.clips.db_client", mock_db):
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not completed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_clips_endpoint_success(
    client, sample_job_id, sample_user_id, sample_clips_metadata, sample_audio_metadata
):
    """Test clips endpoint with valid completed job."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database client
        mock_db = AsyncMock()
        
        # Mock jobs table query
        mock_jobs_table = MagicMock()
        mock_jobs_table.select = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.eq = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": sample_user_id,
            "status": "completed"
        }]))
        
        # Mock job_stages table query for clips
        mock_stages_table = MagicMock()
        mock_stages_table.select = MagicMock(return_value=mock_stages_table)
        mock_stages_table.eq = MagicMock(return_value=mock_stages_table)
        
        # First call: video_generator stage (clips)
        # Second call: audio_parser stage (lyrics)
        # Third call: clip_thumbnails table
        def mock_execute_side_effect(*args, **kwargs):
            # Determine which query based on context
            if hasattr(mock_stages_table, '_call_count'):
                mock_stages_table._call_count += 1
            else:
                mock_stages_table._call_count = 1
            
            if mock_stages_table._call_count == 1:
                # video_generator stage
                return MagicMock(data=[{"metadata": sample_clips_metadata}])
            elif mock_stages_table._call_count == 2:
                # audio_parser stage
                return MagicMock(data=[{"metadata": sample_audio_metadata}])
            else:
                # clip_thumbnails table
                return MagicMock(data=[])
        
        mock_stages_table.execute = AsyncMock(side_effect=mock_execute_side_effect)
        
        # Mock table() to return appropriate table
        def mock_table(table_name):
            if table_name == "jobs":
                return mock_jobs_table
            elif table_name == "job_stages":
                return mock_stages_table
            elif table_name == "clip_thumbnails":
                mock_thumbnails_table = MagicMock()
                mock_thumbnails_table.select = MagicMock(return_value=mock_thumbnails_table)
                mock_thumbnails_table.eq = MagicMock(return_value=mock_thumbnails_table)
                mock_thumbnails_table.execute = AsyncMock(return_value=MagicMock(data=[]))
                return mock_thumbnails_table
            return mock_stages_table
        
        mock_db.table = MagicMock(side_effect=mock_table)
        
        # Mock data loader
        from shared.models.video import Clips, Clip
        from decimal import Decimal
        
        mock_clips = Clips(
            job_id=uuid4(),
            clips=[
                Clip(
                    clip_index=0,
                    video_url="https://storage.supabase.co/video-clips/job/clip_0.mp4",
                    actual_duration=12.5,
                    target_duration=12.0,
                    original_target_duration=12.0,
                    duration_diff=0.5,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=45.2
                )
            ],
            total_clips=1,
            successful_clips=1,
            failed_clips=0,
            total_cost=Decimal("0.10"),
            total_generation_time=45.2
        )
        
        with patch("api_gateway.routes.clips.db_client", mock_db), \
             patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=mock_clips), \
             patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=None):
            
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "clips" in data
    assert "total_clips" in data
    assert len(data["clips"]) == 1
    assert data["clips"][0]["clip_index"] == 0
    assert "thumbnail_url" in data["clips"][0]
    assert "timestamp_start" in data["clips"][0]
    assert "timestamp_end" in data["clips"][0]
    assert "lyrics_preview" in data["clips"][0]
    assert "duration" in data["clips"][0]
    assert "is_regenerated" in data["clips"][0]
    assert data["clips"][0]["is_regenerated"] is False


@pytest.mark.asyncio
async def test_clips_endpoint_missing_clips(client, sample_job_id, sample_user_id):
    """Test clips endpoint when clips not found."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database
        mock_db = AsyncMock()
        mock_jobs_table = MagicMock()
        mock_jobs_table.select = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.eq = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": sample_user_id,
            "status": "completed"
        }]))
        mock_db.table = MagicMock(return_value=mock_jobs_table)
        
        with patch("api_gateway.routes.clips.db_client", mock_db), \
             patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=None):
            
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "clips not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_clips_endpoint_with_thumbnails(
    client, sample_job_id, sample_user_id, sample_clips_metadata
):
    """Test clips endpoint with thumbnails available."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database
        mock_db = AsyncMock()
        mock_jobs_table = MagicMock()
        mock_jobs_table.select = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.eq = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": sample_user_id,
            "status": "completed"
        }]))
        
        mock_thumbnails_table = MagicMock()
        mock_thumbnails_table.select = MagicMock(return_value=mock_thumbnails_table)
        mock_thumbnails_table.eq = MagicMock(return_value=mock_thumbnails_table)
        mock_thumbnails_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "clip_index": 0,
            "thumbnail_url": "https://storage.supabase.co/clip-thumbnails/job/clip_0_thumbnail.jpg"
        }]))
        
        def mock_table(table_name):
            if table_name == "jobs":
                return mock_jobs_table
            elif table_name == "clip_thumbnails":
                return mock_thumbnails_table
            else:
                mock_stages_table = MagicMock()
                mock_stages_table.select = MagicMock(return_value=mock_stages_table)
                mock_stages_table.eq = MagicMock(return_value=mock_stages_table)
                mock_stages_table.execute = AsyncMock(return_value=MagicMock(data=[]))
                return mock_stages_table
        
        mock_db.table = MagicMock(side_effect=mock_table)
        
        # Mock data loader
        from shared.models.video import Clips, Clip
        from decimal import Decimal
        
        mock_clips = Clips(
            job_id=uuid4(),
            clips=[
                Clip(
                    clip_index=0,
                    video_url="https://storage.supabase.co/video-clips/job/clip_0.mp4",
                    actual_duration=12.5,
                    target_duration=12.0,
                    original_target_duration=12.0,
                    duration_diff=0.5,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=45.2
                )
            ],
            total_clips=1,
            successful_clips=1,
            failed_clips=0,
            total_cost=Decimal("0.10"),
            total_generation_time=45.2
        )
        
        with patch("api_gateway.routes.clips.db_client", mock_db), \
             patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=mock_clips), \
             patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=None):
            
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["clips"][0]["thumbnail_url"] == "https://storage.supabase.co/clip-thumbnails/job/clip_0_thumbnail.jpg"


@pytest.mark.asyncio
async def test_clips_endpoint_with_lyrics(
    client, sample_job_id, sample_user_id, sample_clips_metadata, sample_audio_metadata
):
    """Test clips endpoint with lyrics alignment."""
    # Mock authentication
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock database
        mock_db = AsyncMock()
        mock_jobs_table = MagicMock()
        mock_jobs_table.select = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.eq = MagicMock(return_value=mock_jobs_table)
        mock_jobs_table.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": sample_job_id,
            "user_id": sample_user_id,
            "status": "completed"
        }]))
        
        call_count = {"count": 0}
        
        def mock_stages_execute(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                # video_generator stage
                return MagicMock(data=[{"metadata": sample_clips_metadata}])
            else:
                # audio_parser stage
                return MagicMock(data=[{"metadata": sample_audio_metadata}])
        
        mock_stages_table = MagicMock()
        mock_stages_table.select = MagicMock(return_value=mock_stages_table)
        mock_stages_table.eq = MagicMock(return_value=mock_stages_table)
        mock_stages_table.execute = AsyncMock(side_effect=mock_stages_execute)
        
        mock_thumbnails_table = MagicMock()
        mock_thumbnails_table.select = MagicMock(return_value=mock_thumbnails_table)
        mock_thumbnails_table.eq = MagicMock(return_value=mock_thumbnails_table)
        mock_thumbnails_table.execute = AsyncMock(return_value=MagicMock(data=[]))
        
        def mock_table(table_name):
            if table_name == "jobs":
                return mock_jobs_table
            elif table_name == "clip_thumbnails":
                return mock_thumbnails_table
            else:
                return mock_stages_table
        
        mock_db.table = MagicMock(side_effect=mock_table)
        
        # Mock data loader
        from shared.models.video import Clips, Clip
        from decimal import Decimal
        
        mock_clips = Clips(
            job_id=uuid4(),
            clips=[
                Clip(
                    clip_index=0,
                    video_url="https://storage.supabase.co/video-clips/job/clip_0.mp4",
                    actual_duration=12.5,
                    target_duration=12.0,
                    original_target_duration=12.0,
                    duration_diff=0.5,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=45.2
                )
            ],
            total_clips=1,
            successful_clips=1,
            failed_clips=0,
            total_cost=Decimal("0.10"),
            total_generation_time=45.2
        )
        
        with patch("api_gateway.routes.clips.db_client", mock_db), \
             patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=mock_clips), \
             patch("api_gateway.routes.clips.load_clip_prompts_from_job_stages", return_value=None):
            
            response = client.get(
                f"/api/v1/jobs/{sample_job_id}/clips",
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Verify lyrics preview is included
    assert "lyrics_preview" in data["clips"][0]
    # Should have lyrics from sample_audio_metadata
    assert data["clips"][0]["lyrics_preview"] is not None


# Regeneration endpoint tests
@pytest.mark.asyncio
async def test_regenerate_endpoint_no_auth(client, sample_job_id):
    """Test regeneration endpoint without authentication."""
    response = client.post(
        f"/api/v1/jobs/{sample_job_id}/clips/0/regenerate",
        json={"instruction": "make it nighttime"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_regenerate_endpoint_job_not_completed(client, sample_job_id, sample_user_id):
    """Test regeneration endpoint with job not completed."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        # Mock verify_job_ownership to return job with status "processing"
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "processing"
            }
            
            response = client.post(
                f"/api/v1/jobs/{sample_job_id}/clips/0/regenerate",
                json={"instruction": "make it nighttime"},
                headers={"Authorization": "Bearer mock_token"}
            )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "completed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_regenerate_endpoint_invalid_clip_index(client, sample_job_id, sample_user_id):
    """Test regeneration endpoint with invalid clip index."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            # Mock database
            mock_db = AsyncMock()
            mock_table = MagicMock()
            mock_table.select = MagicMock(return_value=mock_table)
            mock_table.eq = MagicMock(return_value=mock_table)
            mock_table.update = MagicMock(return_value=mock_table)
            mock_table.execute = AsyncMock(return_value=MagicMock(data=[{"status": "completed"}]))
            mock_db.table = MagicMock(return_value=mock_table)
            
            # Mock clips loader to return clips with only 1 clip
            from shared.models.video import Clips, Clip
            from decimal import Decimal
            
            mock_clips = Clips(
                job_id=uuid4(),
                clips=[
                    Clip(
                        clip_index=0,
                        video_url="https://example.com/clip0.mp4",
                        target_duration=5.0,
                        actual_duration=5.0,
                        status="completed",
                        cost=Decimal("0.10")
                    )
                ],
                total_clips=1,
                successful_clips=1,
                failed_clips=0,
                total_cost=Decimal("0.10")
            )
            
            with patch("api_gateway.routes.clips.db_client", mock_db), \
                 patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=mock_clips):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/10/regenerate",  # Invalid index
                    json={"instruction": "make it nighttime"},
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid" in response.json()["detail"].lower() or "range" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_regenerate_endpoint_empty_instruction(client, sample_job_id, sample_user_id):
    """Test regeneration endpoint with empty instruction."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            # Mock database
            mock_db = AsyncMock()
            mock_table = MagicMock()
            mock_table.select = MagicMock(return_value=mock_table)
            mock_table.eq = MagicMock(return_value=mock_table)
            mock_table.update = MagicMock(return_value=mock_table)
            mock_table.execute = AsyncMock(return_value=MagicMock(data=[{"status": "completed"}]))
            mock_db.table = MagicMock(return_value=mock_table)
            
            with patch("api_gateway.routes.clips.db_client", mock_db):
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/regenerate",
                    json={"instruction": ""},  # Empty instruction
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower() or "instruction" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_regenerate_endpoint_success_template(
    client, sample_job_id, sample_user_id, sample_clips_metadata
):
    """Test successful regeneration with template match."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            # Mock database
            mock_db = AsyncMock()
            mock_table = MagicMock()
            mock_table.select = MagicMock(return_value=mock_table)
            mock_table.eq = MagicMock(return_value=mock_table)
            mock_table.update = MagicMock(return_value=mock_table)
            mock_table.single = MagicMock(return_value=mock_table)
            mock_table.execute = AsyncMock(return_value=MagicMock(data=[{"status": "completed"}]))
            mock_db.table = MagicMock(return_value=mock_table)
            
            # Mock clips loader
            from shared.models.video import Clips, Clip, ClipPrompts, ClipPrompt
            from decimal import Decimal
            
            mock_clips = Clips(
                job_id=uuid4(),
                clips=[
                    Clip(
                        clip_index=0,
                        video_url="https://example.com/clip0.mp4",
                        target_duration=5.0,
                        actual_duration=5.0,
                        status="completed",
                        cost=Decimal("0.10")
                    )
                ],
                total_clips=1,
                successful_clips=1,
                failed_clips=0,
                total_cost=Decimal("0.10")
            )
            
            mock_prompts = ClipPrompts(
                job_id=uuid4(),
                clip_prompts=[
                    ClipPrompt(
                        clip_index=0,
                        prompt="A cyberpunk street scene",
                        negative_prompt="blurry",
                        duration=5.0
                    )
                ],
                total_clips=1
            )
            
            # Mock regeneration process
            from modules.clip_regenerator.process import RegenerationResult
            
            mock_result = RegenerationResult(
                clip=Clip(
                    clip_index=0,
                    video_url="https://example.com/new_clip.mp4",
                    target_duration=5.0,
                    actual_duration=5.0,
                    status="completed",
                    cost=Decimal("0.10")
                ),
                modified_prompt="A cyberpunk street scene, nighttime scene",
                template_used="nighttime",
                cost=Decimal("0.10")
            )
            
            with patch("api_gateway.routes.clips.db_client", mock_db), \
                 patch("api_gateway.routes.clips.load_clips_from_job_stages", return_value=mock_clips), \
                 patch("api_gateway.routes.clips.regenerate_clip", return_value=mock_result):
                
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/regenerate",
                    json={"instruction": "make it nighttime", "conversation_history": []},
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "regeneration_id" in data
    assert "estimated_cost" in data
    assert "estimated_time" in data
    assert "status" in data
    assert data["status"] == "completed"
    assert data["template_matched"] == "nighttime"


@pytest.mark.asyncio
async def test_regenerate_endpoint_concurrent_prevention(client, sample_job_id, sample_user_id):
    """Test concurrent regeneration prevention."""
    with patch("api_gateway.dependencies.get_current_user") as mock_auth:
        mock_auth.return_value = {"user_id": sample_user_id}
        
        with patch("api_gateway.routes.clips.verify_job_ownership") as mock_verify:
            mock_verify.return_value = {
                "id": sample_job_id,
                "user_id": sample_user_id,
                "status": "completed"
            }
            
            # Mock database - simulate job already in "regenerating" status
            mock_db = AsyncMock()
            mock_table = MagicMock()
            mock_table.select = MagicMock(return_value=mock_table)
            mock_table.eq = MagicMock(return_value=mock_table)
            mock_table.single = MagicMock(return_value=mock_table)
            mock_table.execute = AsyncMock(return_value=MagicMock(data=[{"status": "regenerating"}]))
            mock_db.table = MagicMock(return_value=mock_table)
            
            with patch("api_gateway.routes.clips.db_client", mock_db):
                response = client.post(
                    f"/api/v1/jobs/{sample_job_id}/clips/0/regenerate",
                    json={"instruction": "make it nighttime"},
                    headers={"Authorization": "Bearer mock_token"}
                )
    
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already in progress" in response.json()["detail"].lower() or "regenerating" in response.json()["detail"].lower()

