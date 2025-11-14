"""
Tests for retry logic with exponential backoff.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from shared.retry import retry_with_backoff
from shared.errors import RetryableError, ValidationError


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_attempt():
    """Test that function succeeds on first attempt."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    async def successful_function():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = await successful_function()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_retries():
    """Test that function succeeds after retries."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    async def retryable_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RetryableError("Temporary failure")
        return "success"
    
    result = await retryable_function()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_fails_after_max_attempts():
    """Test that function raises exception after max attempts."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    async def always_fails():
        nonlocal call_count
        call_count += 1
        raise RetryableError("Always fails")
    
    with pytest.raises(RetryableError, match="Always fails"):
        await always_fails()
    
    assert call_count == 3  # Should retry 3 times


@pytest.mark.asyncio
async def test_retry_exponential_backoff():
    """Test that backoff delay increases exponentially."""
    call_times = []
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    async def track_timing():
        call_times.append(time.time())
        if len(call_times) < 3:
            raise RetryableError("Retry")
        return "success"
    
    start_time = time.time()
    await track_timing()
    
    # Check that delays increase: 0.1s, 0.2s (2^0 * 0.1, 2^1 * 0.1)
    assert len(call_times) == 3
    delay1 = call_times[1] - call_times[0]
    delay2 = call_times[2] - call_times[1]
    
    # Allow some tolerance for timing
    assert 0.08 < delay1 < 0.15  # ~0.1s
    assert 0.18 < delay2 < 0.25  # ~0.2s


@pytest.mark.asyncio
async def test_retry_only_on_retryable_error():
    """Test that non-retryable errors are not retried."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    async def non_retryable_error():
        nonlocal call_count
        call_count += 1
        raise ValidationError("Non-retryable")
    
    with pytest.raises(ValidationError, match="Non-retryable"):
        await non_retryable_error()
    
    assert call_count == 1  # Should not retry


@pytest.mark.asyncio
async def test_retry_custom_retryable_exceptions():
    """Test that custom retryable exceptions work."""
    call_count = 0
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=0.1,
        retryable_exceptions=(ConnectionError, RetryableError)
    )
    async def custom_retryable():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Connection failed")
        return "success"
    
    result = await custom_retryable()
    assert result == "success"
    assert call_count == 2


def test_retry_sync_function():
    """Test that retry works with sync functions."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, base_delay=0.1)
    def sync_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RetryableError("Retry")
        return "success"
    
    result = sync_function()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_logs_attempts(caplog):
    """Test that retry attempts are logged."""
    import logging
    logging.getLogger("retry").setLevel(logging.WARNING)
    
    @retry_with_backoff(max_attempts=2, base_delay=0.1)
    async def logged_function():
        raise RetryableError("Retry")
    
    with pytest.raises(RetryableError):
        await logged_function()
    
    # Check that retry attempts were logged
    log_messages = [record.message for record in caplog.records]
    assert any("Retry attempt" in msg for msg in log_messages)

