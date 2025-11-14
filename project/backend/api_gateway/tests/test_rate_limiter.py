"""
Tests for rate limiter service.
"""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from shared.errors import RateLimitError


@pytest.mark.asyncio
async def test_rate_limit_within_limit(mock_redis_client, test_env_vars):
    """Test rate limit check when within limit."""
    # Import after patching to avoid connection attempts
    with patch("api_gateway.services.rate_limiter.redis_client") as mock_redis_wrapper:
        # Create a mock RedisClient instance
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.zcard = AsyncMock(return_value=3)  # 3 jobs in last hour
        mock_redis_client.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis_client.zadd = AsyncMock(return_value=1)
        mock_redis_client.expire = AsyncMock(return_value=True)
        mock_redis_client.zrange = AsyncMock(return_value=[])
        
        # Now import the function
        from api_gateway.services.rate_limiter import check_rate_limit
        
        # Should not raise
        await check_rate_limit("test_user_id")
        
        # Verify Redis operations
        assert mock_redis_client.zremrangebyscore.called
        assert mock_redis_client.zadd.called
        assert mock_redis_client.expire.called


@pytest.mark.asyncio
async def test_rate_limit_exceeded(mock_redis_client, test_env_vars):
    """Test rate limit check when limit exceeded."""
    with patch("api_gateway.services.rate_limiter.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.zcard = AsyncMock(return_value=5)  # Already at limit
        mock_redis_client.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis_client.zrange = AsyncMock(return_value=[(b"timestamp", int(time.time()) - 1800)])
        
        from api_gateway.services.rate_limiter import check_rate_limit
        
        # Should raise RateLimitError
        with pytest.raises(RateLimitError) as exc_info:
            await check_rate_limit("test_user_id")
        
        assert exc_info.value.retry_after is not None
        assert exc_info.value.code == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_rate_limit_sliding_window(mock_redis_client, test_env_vars):
    """Test sliding window behavior."""
    with patch("api_gateway.services.rate_limiter.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis_client.zadd = AsyncMock(return_value=1)
        mock_redis_client.expire = AsyncMock(return_value=True)
        mock_redis_client.zrange = AsyncMock(return_value=[])
        
        from api_gateway.services.rate_limiter import check_rate_limit
        
        # First 4 requests should succeed
        for i in range(4):
            mock_redis_client.zcard = AsyncMock(return_value=i)
            await check_rate_limit("test_user_id")
        
        # 5th request should succeed (at limit but not exceeded)
        mock_redis_client.zcard = AsyncMock(return_value=4)
        await check_rate_limit("test_user_id")
        
        # 6th request should fail
        mock_redis_client.zcard = AsyncMock(return_value=5)
        with pytest.raises(RateLimitError):
            await check_rate_limit("test_user_id")


@pytest.mark.asyncio
async def test_rate_limit_retry_after_calculation(mock_redis_client, test_env_vars):
    """Test Retry-After header calculation."""
    with patch("api_gateway.services.rate_limiter.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.zcard = AsyncMock(return_value=5)  # At limit
        mock_redis_client.zremrangebyscore = AsyncMock(return_value=0)
        
        # Mock oldest entry (30 minutes ago)
        current_time = int(time.time())
        oldest_time = current_time - 1800  # 30 minutes ago
        mock_redis_client.zrange = AsyncMock(return_value=[(b"timestamp", oldest_time)])
        
        from api_gateway.services.rate_limiter import check_rate_limit
        
        with pytest.raises(RateLimitError) as exc_info:
            await check_rate_limit("test_user_id")
        
        # Retry-After should be ~1800 seconds (30 minutes)
        assert exc_info.value.retry_after is not None
        assert 1700 <= exc_info.value.retry_after <= 1900  # Allow some tolerance


@pytest.mark.asyncio
async def test_rate_limit_old_entries_cleanup(mock_redis_client, test_env_vars):
    """Test that old entries are removed from sorted set."""
    with patch("api_gateway.services.rate_limiter.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.zcard = AsyncMock(return_value=2)
        mock_redis_client.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis_client.zadd = AsyncMock(return_value=1)
        mock_redis_client.expire = AsyncMock(return_value=True)
        mock_redis_client.zrange = AsyncMock(return_value=[])
        
        from api_gateway.services.rate_limiter import check_rate_limit
        
        await check_rate_limit("test_user_id")
        
        # Verify zremrangebyscore was called to remove old entries
        assert mock_redis_client.zremrangebyscore.called
        call_args = mock_redis_client.zremrangebyscore.call_args
        assert call_args[0][0] == "rate_limit:test_user_id"  # Key
        assert call_args[0][1] == 0  # Min score
        # Max score should be current_time - 3600
