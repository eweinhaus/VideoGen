"""
Tests for queue service.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch
from api_gateway.services.queue_service import enqueue_job, remove_job, get_queue_size


@pytest.mark.asyncio
async def test_enqueue_job(mock_redis_client):
    """Test job enqueueing."""
    with patch("api_gateway.services.queue_service.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        
        job_id = "test_job_id"
        user_id = "test_user_id"
        audio_url = "https://storage.supabase.co/test.mp3"
        user_prompt = "Test prompt"
        
        await enqueue_job(job_id, user_id, audio_url, user_prompt)
        
        # Verify job data was stored
        assert mock_redis_client.set.called
        set_call = mock_redis_client.set.call_args_list[0]
        assert "job:test_job_id" in set_call[0][0]  # Key contains job_id
        
        # Verify job was added to queue
        assert mock_redis_client.lpush.called
        lpush_call = mock_redis_client.lpush.call_args
        assert "video_generation:queue" in lpush_call[0][0]
        
        # Verify job data structure
        job_data_str = lpush_call[0][1]
        if isinstance(job_data_str, bytes):
            job_data_str = job_data_str.decode("utf-8")
        job_data = json.loads(job_data_str)
        assert job_data["job_id"] == job_id
        assert job_data["user_id"] == user_id
        assert job_data["audio_url"] == audio_url
        assert job_data["user_prompt"] == user_prompt


@pytest.mark.asyncio
async def test_remove_job(mock_redis_client):
    """Test job removal from queue."""
    with patch("api_gateway.services.queue_service.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        
        job_id = "test_job_id"
        result = await remove_job(job_id)
        
        assert result is True
        assert mock_redis_client.delete.called
        delete_call = mock_redis_client.delete.call_args
        assert "job:test_job_id" in delete_call[0][0]


@pytest.mark.asyncio
async def test_get_queue_size(mock_redis_client):
    """Test queue size retrieval."""
    with patch("api_gateway.services.queue_service.redis_client") as mock_redis:
        mock_redis.client = mock_redis_client
        mock_redis_client.llen.return_value = 5
        
        size = await get_queue_size()
        
        assert size == 5
        assert mock_redis_client.llen.called
        llen_call = mock_redis_client.llen.call_args
        assert "video_generation:queue" in llen_call[0][0]
