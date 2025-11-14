"""
Tests for Redis client.
"""

import pytest
import json
import sys
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

# Mock redis.asyncio before importing shared modules
mock_redis_asyncio = Mock()
mock_redis_asyncio.from_url = AsyncMock()
sys.modules['redis'] = Mock()
sys.modules['redis.asyncio'] = mock_redis_asyncio

from shared.redis_client import RedisClient
from shared.errors import RetryableError, ConfigError


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis async client."""
    client = AsyncMock()
    return client


@pytest.fixture
def redis_client(mock_redis_client):
    """Create a Redis client with mocked Redis."""
    # Create new instance directly with mocked client
    client = RedisClient.__new__(RedisClient)
    client.client = mock_redis_client
    client.prefix = "videogen:cache:"
    return client


@pytest.mark.asyncio
async def test_redis_client_initialization():
    """Test that Redis client initializes correctly."""
    mock_client = AsyncMock()
    
    # Patch redis.asyncio.from_url (since it's imported as redis.asyncio as redis)
    with patch("shared.redis_client.redis.from_url", return_value=mock_client):
        with patch("shared.redis_client.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"
            
            # Create new instance - __init__ will use the patched redis.from_url
            client = RedisClient()
            
            assert client.client == mock_client
            assert client.prefix == "videogen:cache:"


@pytest.mark.asyncio
async def test_redis_client_initialization_failure():
    """Test that ConfigError is raised on initialization failure."""
    with patch("shared.redis_client.redis.from_url", side_effect=Exception("Connection failed")):
        with patch("shared.redis_client.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"
            
            with pytest.raises(ConfigError, match="Failed to initialize Redis client"):
                # Create new instance to avoid singleton
                client = RedisClient.__new__(RedisClient)
                client.__init__()


@pytest.mark.asyncio
async def test_redis_set(redis_client):
    """Test setting a string value."""
    redis_client.client.set = AsyncMock(return_value=True)
    
    result = await redis_client.set("test_key", "test_value", ex=3600)
    
    assert result is True
    redis_client.client.set.assert_called_once_with(
        "videogen:cache:test_key",
        "test_value".encode("utf-8"),
        ex=3600
    )


@pytest.mark.asyncio
async def test_redis_get(redis_client):
    """Test getting a string value."""
    redis_client.client.get = AsyncMock(return_value="test_value".encode("utf-8"))
    
    result = await redis_client.get("test_key")
    
    assert result == "test_value"
    redis_client.client.get.assert_called_once_with("videogen:cache:test_key")


@pytest.mark.asyncio
async def test_redis_get_none(redis_client):
    """Test getting a non-existent key returns None."""
    redis_client.client.get = AsyncMock(return_value=None)
    
    result = await redis_client.get("nonexistent_key")
    
    assert result is None


@pytest.mark.asyncio
async def test_redis_delete(redis_client):
    """Test deleting a key."""
    redis_client.client.delete = AsyncMock(return_value=1)
    
    result = await redis_client.delete("test_key")
    
    assert result is True
    redis_client.client.delete.assert_called_once_with("videogen:cache:test_key")


@pytest.mark.asyncio
async def test_redis_delete_nonexistent(redis_client):
    """Test deleting a non-existent key returns False."""
    redis_client.client.delete = AsyncMock(return_value=0)
    
    result = await redis_client.delete("nonexistent_key")
    
    assert result is False


@pytest.mark.asyncio
async def test_redis_set_json(redis_client):
    """Test setting a JSON value."""
    data = {"key": "value", "number": 123}
    json_str = json.dumps(data)
    
    redis_client.set = AsyncMock(return_value=True)
    
    result = await redis_client.set_json("test_key", data, ttl=3600)
    
    assert result is True
    redis_client.set.assert_called_once_with("test_key", json_str, ex=3600)


@pytest.mark.asyncio
async def test_redis_get_json(redis_client):
    """Test getting a JSON value."""
    data = {"key": "value", "number": 123}
    json_str = json.dumps(data)
    
    redis_client.get = AsyncMock(return_value=json_str)
    
    result = await redis_client.get_json("test_key")
    
    assert result == data


@pytest.mark.asyncio
async def test_redis_get_json_none(redis_client):
    """Test getting a non-existent JSON key returns None."""
    redis_client.get = AsyncMock(return_value=None)
    
    result = await redis_client.get_json("nonexistent_key")
    
    assert result is None


@pytest.mark.asyncio
async def test_redis_get_json_invalid(redis_client):
    """Test that invalid JSON raises RetryableError."""
    redis_client.get = AsyncMock(return_value="invalid json")
    
    with pytest.raises(RetryableError, match="Failed to decode JSON"):
        await redis_client.get_json("test_key")


@pytest.mark.asyncio
async def test_redis_set_raises_retryable_error(redis_client):
    """Test that set raises RetryableError on failure."""
    redis_client.client.set = AsyncMock(side_effect=Exception("Connection failed"))
    
    with pytest.raises(RetryableError, match="Failed to set Redis key"):
        await redis_client.set("test_key", "value")


@pytest.mark.asyncio
async def test_redis_get_raises_retryable_error(redis_client):
    """Test that get raises RetryableError on failure."""
    redis_client.client.get = AsyncMock(side_effect=Exception("Connection failed"))
    
    with pytest.raises(RetryableError, match="Failed to get Redis key"):
        await redis_client.get("test_key")


@pytest.mark.asyncio
async def test_redis_health_check_success(redis_client):
    """Test that health check returns True on success."""
    redis_client.client.ping = AsyncMock(return_value=True)
    
    is_healthy = await redis_client.health_check()
    
    assert is_healthy is True
    redis_client.client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_redis_health_check_failure(redis_client):
    """Test that health check returns False on failure."""
    redis_client.client.ping = AsyncMock(side_effect=Exception("Connection failed"))
    
    is_healthy = await redis_client.health_check()
    
    assert is_healthy is False


@pytest.mark.asyncio
async def test_redis_close(redis_client):
    """Test that close method works."""
    redis_client.client.close = AsyncMock()
    
    await redis_client.close()
    
    redis_client.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_redis_key_prefixing(redis_client):
    """Test that keys are prefixed correctly."""
    redis_client.client.set = AsyncMock(return_value=True)
    
    await redis_client.set("my_key", "value")
    
    # Check that key was prefixed
    call_args = redis_client.client.set.call_args
    assert call_args[0][0] == "videogen:cache:my_key"


@pytest.mark.asyncio
async def test_redis_json_with_complex_types(redis_client):
    """Test that JSON serialization handles complex types."""
    from datetime import datetime
    from uuid import uuid4
    
    data = {
        "uuid": uuid4(),
        "timestamp": datetime.utcnow(),
        "nested": {"key": "value"}
    }
    
    redis_client.set = AsyncMock(return_value=True)
    redis_client.get = AsyncMock(return_value=json.dumps(data, default=str))
    
    await redis_client.set_json("test_key", data, ttl=3600)
    result = await redis_client.get_json("test_key")
    
    # Complex types should be serialized as strings
    assert isinstance(result["uuid"], str)
    assert isinstance(result["timestamp"], str)

