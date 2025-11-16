"""
Unit tests for image generation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from uuid import UUID
from modules.reference_generator.generator import generate_image, get_model_version


@pytest.mark.asyncio
async def test_get_model_version():
    """Test model version selection."""
    version = get_model_version()
    assert version == "stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245"
    assert "latest" not in version  # Should pin specific version


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.client')
@patch('httpx.AsyncClient')
async def test_generate_image_success(mock_httpx, mock_client):
    """Test successful image generation."""
    # Mock Replicate API response
    mock_output = "https://replicate.delivery/pbxt/test-image.png"
    mock_client.run = Mock(return_value=mock_output)
    
    # Mock HTTP client for image download
    mock_response = Mock()
    mock_response.content = b"fake_image_bytes"
    mock_response.raise_for_status = Mock()
    mock_http_client = AsyncMock()
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)
    mock_http_client.get = AsyncMock(return_value=mock_response)
    mock_httpx.return_value = mock_http_client
    
    # Generate image (returns 4 values: image_bytes, gen_time, cost, retry_count)
    image_bytes, gen_time, cost, retry_count = await generate_image(
        prompt="Test prompt",
        image_type="scene",
        image_id="test_scene",
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000")
    )
    
    assert image_bytes == b"fake_image_bytes"
    assert gen_time > 0
    assert cost == Decimal("0.005")  # Default estimate
    assert retry_count == 0


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.replicate.run')
async def test_generate_image_timeout(mock_replicate_run):
    """Test image generation timeout."""
    import asyncio
    
    # Mock timeout
    async def slow_run(*args, **kwargs):
        await asyncio.sleep(130)  # Longer than 120s timeout
        return "https://test.com/image.png"
    
    # Wrap in asyncio.to_thread call
    def sync_slow_run(*args, **kwargs):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(slow_run(*args, **kwargs))
        finally:
            loop.close()
    
    mock_replicate_run.side_effect = sync_slow_run
    
    with pytest.raises(Exception):  # Should raise timeout error
        await generate_image(
            prompt="Test prompt",
            image_type="scene",
            image_id="test_scene",
            job_id=UUID("550e8400-e29b-41d4-a716-446655440000")
        )


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.replicate.run')
async def test_generate_image_rate_limit(mock_replicate_run):
    """Test rate limit error handling."""
    import httpx
    
    # Mock rate limit error
    mock_replicate_run.side_effect = httpx.HTTPStatusError(
        "Rate limit exceeded",
        request=Mock(),
        response=Mock(status_code=429, headers={"Retry-After": "5"})
    )
    
    with pytest.raises(Exception):  # Should raise RateLimitError or RetryableError
        await generate_image(
            prompt="Test prompt",
            image_type="scene",
            image_id="test_scene",
            job_id=UUID("550e8400-e29b-41d4-a716-446655440000")
        )

