"""
Tests for event publisher service.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch
from api_gateway.services.event_publisher import publish_event


@pytest.mark.asyncio
async def test_publish_event(mock_redis_client):
    """Test event publishing to Redis pub/sub."""
    with patch("api_gateway.services.event_publisher.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        
        job_id = "test_job_id"
        event_type = "progress"
        data = {"progress": 50, "stage": "video_generation"}
        
        await publish_event(job_id, event_type, data)
        
        # Verify publish was called
        assert mock_redis_client.publish.called
        
        # Verify channel format
        call_args = mock_redis_client.publish.call_args
        assert call_args[0][0] == f"job_events:{job_id}"
        
        # Verify message format (JSON string)
        message = call_args[0][1]
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        event_data = json.loads(message)
        assert event_data["event_type"] == event_type
        assert event_data["data"] == data


@pytest.mark.asyncio
async def test_publish_event_message_format(mock_redis_client):
    """Test that message is JSON string, not Python dict."""
    with patch("api_gateway.services.event_publisher.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        
        await publish_event("test_job", "stage_update", {"stage": "audio_parser", "status": "completed"})
        
        call_args = mock_redis_client.publish.call_args
        message = call_args[0][1]
        
        # Message should be string (or bytes that decode to string)
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        
        assert isinstance(message, str)
        # Should be valid JSON
        event_data = json.loads(message)
        assert "event_type" in event_data
        assert "data" in event_data


@pytest.mark.asyncio
async def test_publish_event_channel_format(mock_redis_client):
    """Test channel format is correct."""
    with patch("api_gateway.services.event_publisher.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        await publish_event(job_id, "test_event", {})
        
        call_args = mock_redis_client.publish.call_args
        channel = call_args[0][0]
        
        assert channel == f"job_events:{job_id}"
