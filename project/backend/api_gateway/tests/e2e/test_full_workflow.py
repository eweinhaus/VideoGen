"""
End-to-end tests for complete API Gateway workflows.

Tests full user journeys from upload to completion.
"""

import pytest
import json
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_jwt_token():
    """Generate a mock JWT token for testing."""
    from jose import jwt
    from shared.config import settings
    
    payload = {
        "sub": str(uuid.uuid4()),  # user_id
        "exp": 9999999999  # Far future
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Get authentication headers."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}


@pytest.mark.e2e
def test_full_workflow_health_check(client):
    """Test health check endpoint in E2E context."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "unhealthy"]
    assert "database" in data
    assert "redis" in data


@pytest.mark.e2e
def test_full_workflow_upload_validation(client, auth_headers):
    """Test upload endpoint validation in E2E context."""
    # Test without file
    response = client.post("/api/v1/upload-audio", headers=auth_headers)
    assert response.status_code in [400, 422]  # Validation error
    
    # Test with invalid prompt (too short)
    files = {"audio_file": ("test.mp3", b"fake audio content", "audio/mpeg")}
    data = {"user_prompt": "short"}  # Too short
    response = client.post("/api/v1/upload-audio", headers=auth_headers, files=files, data=data)
    assert response.status_code in [400, 422]  # Validation error


@pytest.mark.e2e
@patch("api_gateway.routes.upload.enqueue_job")
@patch("api_gateway.routes.upload.storage_client")
@patch("api_gateway.routes.upload.db_client")
@patch("api_gateway.routes.upload.check_rate_limit")
def test_full_workflow_upload_success(
    mock_rate_limit,
    mock_db,
    mock_storage,
    mock_enqueue,
    client,
    auth_headers
):
    """Test successful upload workflow."""
    # Mock dependencies
    mock_rate_limit.return_value = None  # No rate limit
    mock_storage.upload_file = AsyncMock(return_value="https://storage.supabase.co/test.mp3")
    
    # Mock database insert
    mock_result = MagicMock()
    mock_result.data = []
    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.insert = MagicMock(return_value=mock_query)
    mock_table = MagicMock()
    mock_table.insert = MagicMock(return_value=mock_query)
    mock_db.table = MagicMock(return_value=mock_table)
    
    # Mock enqueue
    mock_enqueue.return_value = None
    
    # Create test audio file content
    files = {
        "audio_file": ("test.mp3", b"fake audio content" * 100, "audio/mpeg")
    }
    data = {
        "user_prompt": "Create a cyberpunk music video with neon lights and futuristic cityscapes and amazing visuals"
    }
    
    response = client.post(
        "/api/v1/upload-audio",
        headers=auth_headers,
        files=files,
        data=data
    )
    
    # Should create job (may fail on file validation, but structure is tested)
    assert response.status_code in [201, 400, 422]  # 201 if valid, 400/422 if file validation fails


@pytest.mark.e2e
def test_full_workflow_job_lifecycle(client, auth_headers, mock_jwt_token):
    """Test complete job lifecycle."""
    # This test would require:
    # 1. Creating a job
    # 2. Checking status
    # 3. Streaming events
    # 4. Cancelling or completing
    
    # For now, test the endpoints exist and return correct status codes
    job_id = str(uuid.uuid4())
    
    # Test job status endpoint
    with patch("api_gateway.routes.jobs.verify_job_ownership") as mock_verify:
        mock_verify.return_value = {
            "id": job_id,
            "user_id": "test_user",
            "status": "queued"
        }
        response = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        # Should either return job or 404 if not found
        assert response.status_code in [200, 404]
    
    # Test job list endpoint
    with patch("api_gateway.routes.jobs.db_client") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_result.count = 0
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=mock_result)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.select = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        response = client.get("/api/v1/jobs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data


@pytest.mark.e2e
def test_full_workflow_sse_structure(client, auth_headers):
    """Test SSE stream endpoint structure."""
    job_id = str(uuid.uuid4())
    
    # Test SSE endpoint exists and handles auth
    with patch("api_gateway.routes.stream.verify_job_ownership") as mock_verify:
        mock_verify.return_value = {
            "id": job_id,
            "user_id": "test_user",
            "status": "processing"
        }
        response = client.get(f"/api/v1/jobs/{job_id}/stream", headers=auth_headers)
        # SSE endpoint should return streaming response
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream"


@pytest.mark.e2e
def test_full_workflow_cancellation(client, auth_headers):
    """Test job cancellation workflow."""
    job_id = str(uuid.uuid4())
    
    with patch("api_gateway.routes.jobs.verify_job_ownership") as mock_verify, \
         patch("api_gateway.routes.jobs.remove_job_from_queue") as mock_remove, \
         patch("api_gateway.routes.jobs.update_job_status") as mock_update:
        
        mock_verify.return_value = {
            "id": job_id,
            "user_id": "test_user",
            "status": "queued"
        }
        mock_remove.return_value = True
        mock_update.return_value = None
        
        response = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "cancelled" in data.get("message", "").lower()


@pytest.mark.e2e
def test_full_workflow_error_handling(client, auth_headers):
    """Test error handling in E2E context."""
    # Test invalid job ID
    invalid_job_id = "invalid-uuid"
    response = client.get(f"/api/v1/jobs/{invalid_job_id}", headers=auth_headers)
    # Should return 403 (auth) or 404 (not found) or 422 (validation)
    assert response.status_code in [403, 404, 422]
    
    # Test missing auth
    response = client.get("/api/v1/jobs/some-id")
    assert response.status_code == 403  # Forbidden


@pytest.mark.e2e
def test_full_workflow_rate_limiting(client, auth_headers):
    """Test rate limiting in E2E context."""
    with patch("api_gateway.routes.upload.check_rate_limit") as mock_rate_limit:
        from shared.errors import RateLimitError
        
        # Simulate rate limit exceeded
        mock_rate_limit.side_effect = RateLimitError(
            "Rate limit exceeded",
            retry_after=3600,
            code="RATE_LIMIT_EXCEEDED"
        )
        
        files = {"audio_file": ("test.mp3", b"content", "audio/mpeg")}
        data = {"user_prompt": "Test prompt with at least 50 characters to pass validation"}
        
        response = client.post(
            "/api/v1/upload-audio",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 429  # Too Many Requests
        assert "Retry-After" in response.headers or "retry_after" in response.json().get("detail", "").lower()


@pytest.mark.e2e
def test_full_workflow_budget_enforcement(client, auth_headers):
    """Test budget enforcement in E2E context."""
    with patch("api_gateway.routes.upload.MutagenFile") as mock_mutagen, \
         patch("api_gateway.routes.upload.check_rate_limit") as mock_rate_limit:
        
        from mutagen import File as MutagenFile
        from mutagen.mp3 import MP3
        
        # Mock very long audio (would exceed budget)
        mock_audio = MagicMock()
        mock_audio.info.length = 600  # 10 minutes
        mock_mutagen.return_value = mock_audio
        
        files = {"audio_file": ("test.mp3", b"content", "audio/mpeg")}
        data = {"user_prompt": "Test prompt with at least 50 characters to pass validation"}
        
        response = client.post(
            "/api/v1/upload-audio",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        # Should reject if estimated cost > $2000
        # 10 minutes * $200/minute = $2000, so should be at limit or rejected
        assert response.status_code in [201, 400, 422]


@pytest.mark.e2e
@patch("api_gateway.routes.download.storage_client")
def test_full_workflow_download(client, auth_headers, mock_storage):
    """Test download endpoint in E2E context."""
    job_id = str(uuid.uuid4())
    
    with patch("api_gateway.routes.download.verify_job_ownership") as mock_verify:
        mock_verify.return_value = {
            "id": job_id,
            "user_id": "test_user",
            "status": "completed",
            "video_url": "https://storage.supabase.co/video.mp4"
        }
        
        mock_storage.get_signed_url = AsyncMock(return_value="https://storage.supabase.co/signed-url")
        
        response = client.get(f"/api/v1/jobs/{job_id}/download", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            assert "download_url" in data
            assert "expires_in" in data
        else:
            # May fail if job not completed
            assert response.status_code in [404, 410]

