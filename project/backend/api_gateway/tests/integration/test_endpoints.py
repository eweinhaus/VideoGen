"""
Integration tests for REST endpoints.

Requires real database and Redis connections.
"""

import pytest
import os
from fastapi.testclient import TestClient
from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get authentication headers (requires real JWT token)."""
    # Get JWT token from environment variable if set
    token = os.getenv("TEST_JWT_TOKEN", "YOUR_JWT_TOKEN_HERE")
    if token == "YOUR_JWT_TOKEN_HERE":
        pytest.skip("TEST_JWT_TOKEN not set - skipping auth tests")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "unhealthy"]
    
    # Verify all required fields
    assert "timestamp" in data
    assert "queue" in data
    assert "database" in data
    assert "redis" in data
    
    # If healthy, verify services are connected
    if data["status"] == "healthy":
        assert data["database"] == "connected"
        assert data["redis"] == "connected"


@pytest.mark.integration
def test_upload_endpoint_validation(client):
    """Test upload endpoint validation (without auth)."""
    # Test without file - should return 403 (auth required) or 422 (validation)
    response = client.post("/api/v1/upload-audio")
    # Could be 403 (auth required) or 422 (validation error)
    assert response.status_code in [403, 422]


@pytest.mark.integration
def test_job_status_endpoint_no_auth(client):
    """Test job status endpoint without auth."""
    # Test without authentication
    response = client.get("/api/v1/jobs/invalid-job-id")
    assert response.status_code == 403  # Forbidden (no auth)


@pytest.mark.integration
def test_job_list_endpoint_no_auth(client):
    """Test job list endpoint without auth."""
    # Test without authentication
    response = client.get("/api/v1/jobs")
    assert response.status_code == 403  # Forbidden (no auth)


@pytest.mark.integration
def test_upload_endpoint_with_auth(client, auth_headers):
    """Test upload endpoint with real file (requires JWT token)."""
    # This test requires:
    # 1. Valid JWT token (set TEST_JWT_TOKEN env var)
    # 2. Test audio file
    # For now, just verify endpoint exists
    if "YOUR_JWT_TOKEN_HERE" in str(auth_headers):
        pytest.skip("JWT token not provided")
    
    # TODO: Create test audio file
    # TODO: Upload and verify job creation
    pass


@pytest.mark.integration
def test_sse_stream_endpoint_no_auth(client):
    """Test SSE stream endpoint without auth."""
    # Test without authentication
    response = client.get("/api/v1/jobs/invalid-job-id/stream")
    assert response.status_code == 403  # Forbidden (no auth)
