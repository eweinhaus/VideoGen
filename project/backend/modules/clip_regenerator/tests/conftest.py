"""
Pytest configuration and fixtures for clip regenerator tests.
"""

import pytest
import os


def pytest_configure(config):
    """Set up environment variables before any imports."""
    # Set environment variables before modules are imported
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test_service_key_1234567890123456789012345678901234567890")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test_anon_key_1234567890123456789012345678901234567890")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test123456789012345678901234567890")
    os.environ.setdefault("REPLICATE_API_TOKEN", "r8_test123456789012345678901234567890")
    os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_123456789012345678901234567890")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "test_jwt_secret_123456789012345678901234567890")
    os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture(autouse=True)
def test_env_vars(monkeypatch):
    """Set up test environment variables (autouse to ensure they're set)."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test_service_key_1234567890123456789012345678901234567890")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test_anon_key_1234567890123456789012345678901234567890")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678901234567890")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test123456789012345678901234567890")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_123456789012345678901234567890")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test_jwt_secret_123456789012345678901234567890")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

