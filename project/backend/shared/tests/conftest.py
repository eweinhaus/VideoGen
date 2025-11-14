"""
Pytest configuration and fixtures.
"""

import pytest
import os
from pathlib import Path


@pytest.fixture
def test_env_file(tmp_path):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / ".env"
    env_content = """
SUPABASE_URL=https://test.supabase.co
SUPABASE_SERVICE_KEY=test_service_key_1234567890123456789012345678901234567890
SUPABASE_ANON_KEY=test_anon_key_1234567890123456789012345678901234567890
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-test123456789012345678901234567890
REPLICATE_API_TOKEN=r8_test123456789012345678901234567890
JWT_SECRET_KEY=test_secret_key_123456789012345678901234567890
ENVIRONMENT=development
LOG_LEVEL=DEBUG
"""
    env_file.write_text(env_content)
    return env_file


@pytest.fixture
def mock_uuid():
    """Mock UUID for testing."""
    from uuid import UUID
    return UUID("550e8400-e29b-41d4-a716-446655440000")


