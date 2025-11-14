"""
Integration test for health endpoint.

Tests the health endpoint with real services.
"""

import pytest
from fastapi.testclient import TestClient
from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.mark.integration
def test_health_endpoint(client):
    """Test health check endpoint with real services."""
    response = client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "status" in data
    assert "timestamp" in data
    assert "queue" in data
    assert "database" in data
    assert "redis" in data
    
    # Verify status
    assert data["status"] in ["healthy", "unhealthy"]
    
    # Verify queue structure
    assert "size" in data["queue"]
    assert "active_jobs" in data["queue"]
    assert "workers" in data["queue"]
    
    # Verify service status
    assert data["database"] in ["connected", "disconnected"]
    assert data["redis"] in ["connected", "disconnected"]
    
    # If healthy, verify all services are connected
    if data["status"] == "healthy":
        assert data["database"] == "connected"
        assert data["redis"] == "connected"

