"""
Pytest configuration and fixtures for API Gateway tests.
"""

import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Use pytest_configure to patch before test collection
def pytest_configure(config):
    """Configure pytest - patch RedisClient before any imports."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from typing import Optional
    
    # Create mock Redis client
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.zadd = AsyncMock(return_value=1)
    mock_redis.zcard = AsyncMock(return_value=0)
    mock_redis.zremrangebyscore = AsyncMock(return_value=0)
    mock_redis.zrange = AsyncMock(return_value=[])
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.lpush = AsyncMock(return_value=1)
    mock_redis.llen = AsyncMock(return_value=0)
    mock_redis.brpop = AsyncMock(return_value=None)
    mock_redis.sadd = AsyncMock(return_value=1)
    mock_redis.srem = AsyncMock(return_value=1)
    
    # Mock pubsub
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    
    # Create a mock RedisClient class that doesn't connect
    class MockRedisClient:
        def __init__(self):
            self.client = mock_redis
            self.prefix = "videogen:cache:"
        
        def _prefix_key(self, key: str) -> str:
            return f"{self.prefix}{key}"
        
        async def get(self, key: str) -> Optional[str]:
            return await mock_redis.get(self._prefix_key(key))
        
        async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
            return await mock_redis.set(self._prefix_key(key), value, ex=ex)
        
        async def delete(self, key: str) -> int:
            return await mock_redis.delete(self._prefix_key(key))
        
        async def health_check(self) -> bool:
            return True
    
    # Patch RedisClient in shared.redis_client module
    import shared.redis_client
    shared.redis_client.RedisClient = MockRedisClient
    
    # Also patch DatabaseClient to avoid supabase import
    class MockDatabaseClient:
        def __init__(self):
            pass
        
        def table(self, name: str):
            mock_table = MagicMock()
            mock_table.select = MagicMock(return_value=mock_table)
            mock_table.insert = MagicMock(return_value=mock_table)
            mock_table.update = MagicMock(return_value=mock_table)
            mock_table.delete = MagicMock(return_value=mock_table)
            mock_table.eq = MagicMock(return_value=mock_table)
            mock_table.limit = MagicMock(return_value=mock_table)
            mock_table.offset = MagicMock(return_value=mock_table)
            mock_table.execute = AsyncMock(return_value=MagicMock(data=[], count=0))
            return mock_table
        
        async def health_check(self) -> bool:
            return True
    
    # Patch supabase import to avoid requiring the package
    import sys
    from unittest.mock import MagicMock
    
    # Create a mock supabase module
    mock_supabase = MagicMock()
    mock_supabase.create_client = MagicMock()
    mock_supabase.Client = MagicMock()
    sys.modules['supabase'] = mock_supabase
    
    # Now patch DatabaseClient in shared.database
    try:
        import shared.database
        shared.database.DatabaseClient = MockDatabaseClient
    except Exception:
        # If import fails, patch it for future imports
        import importlib.util
        # Create a spec for the module
        pass


@pytest.fixture
def test_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test_service_key_1234567890123456789012345678901234567890")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test_anon_key_1234567890123456789012345678901234567890")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678901234567890")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test123456789012345678901234567890")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_123456789012345678901234567890")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test_jwt_secret_123456789012345678901234567890")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock(return_value=True)
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.zadd = AsyncMock(return_value=1)
    mock_client.zcard = AsyncMock(return_value=0)
    mock_client.zremrangebyscore = AsyncMock(return_value=0)
    mock_client.zrange = AsyncMock(return_value=[])
    mock_client.expire = AsyncMock(return_value=True)
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.publish = AsyncMock(return_value=1)
    mock_client.lpush = AsyncMock(return_value=1)
    mock_client.llen = AsyncMock(return_value=0)
    mock_client.brpop = AsyncMock(return_value=None)
    mock_client.sadd = AsyncMock(return_value=1)
    mock_client.srem = AsyncMock(return_value=1)
    
    # Mock pubsub
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_client.pubsub = MagicMock(return_value=mock_pubsub)
    
    return mock_client


@pytest.fixture
def mock_database_client():
    """Mock database client for testing."""
    mock_client = AsyncMock()
    
    # Mock table query builder
    mock_table = AsyncMock()
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.insert = MagicMock(return_value=mock_table)
    mock_table.update = MagicMock(return_value=mock_table)
    mock_table.delete = MagicMock(return_value=mock_table)
    mock_table.eq = MagicMock(return_value=mock_table)
    mock_table.limit = MagicMock(return_value=mock_table)
    mock_table.offset = MagicMock(return_value=mock_table)
    
    # Mock execute result
    mock_result = MagicMock()
    mock_result.data = []
    mock_result.count = 0
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    mock_client.table = MagicMock(return_value=mock_table)
    mock_client.health_check = AsyncMock(return_value=True)
    
    return mock_client


@pytest.fixture
def sample_jwt_token():
    """Sample JWT token for testing."""
    # This is a mock token - in real tests, generate valid JWT
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAiLCJleHAiOjk5OTk5OTk5OTl9.test_signature"


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "queued",
        "audio_url": "https://storage.supabase.co/audio-uploads/test.mp3",
        "user_prompt": "Create a cyberpunk music video with neon lights and futuristic cityscapes",
        "progress": 0,
        "total_cost": 0.0
    }

