"""
Pytest configuration for integration tests.
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from api_gateway.main import app


@pytest.fixture
def client():
    """Create test client for integration tests."""
    return TestClient(app)


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

