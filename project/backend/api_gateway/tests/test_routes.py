"""
Tests for API Gateway routes.

Tests endpoints with FastAPI TestClient.
"""

import pytest
from fastapi.testclient import TestClient
from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200


def test_health_endpoint_no_auth(client):
    """Test health endpoint (no auth required)."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data


def test_upload_endpoint_no_auth(client):
    """Test upload endpoint without authentication."""
    response = client.post("/api/v1/upload-audio")
    # Should return 403 (no auth) or 422 (validation error)
    assert response.status_code in [403, 422]


def test_jobs_endpoint_no_auth(client):
    """Test jobs endpoint without authentication."""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 403  # Forbidden


def test_job_status_endpoint_no_auth(client):
    """Test job status endpoint without authentication."""
    response = client.get("/api/v1/jobs/invalid-id")
    assert response.status_code == 403  # Forbidden


def test_stream_endpoint_no_auth(client):
    """Test SSE stream endpoint without authentication."""
    response = client.get("/api/v1/jobs/invalid-id/stream")
    assert response.status_code == 403  # Forbidden


def test_download_endpoint_no_auth(client):
    """Test download endpoint without authentication."""
    response = client.get("/api/v1/jobs/invalid-id/download")
    assert response.status_code == 403  # Forbidden


def test_cancel_endpoint_no_auth(client):
    """Test cancel endpoint without authentication."""
    response = client.post("/api/v1/jobs/invalid-id/cancel")
    assert response.status_code == 403  # Forbidden

