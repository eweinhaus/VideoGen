"""
Tests for pipeline orchestrator.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api_gateway.orchestrator import (
    check_cancellation,
    update_progress,
    handle_pipeline_error,
    execute_pipeline
)


@pytest.mark.asyncio
async def test_check_cancellation_false(mock_redis_client, test_env_vars):
    """Test cancellation check when not cancelled."""
    with patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper:
        # Mock RedisClient instance - it uses .get() method
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        cancelled = await check_cancellation("test_job_id")
        assert cancelled is False
        assert mock_redis_wrapper.get.called


@pytest.mark.asyncio
async def test_check_cancellation_true(mock_redis_client, test_env_vars):
    """Test cancellation check when cancelled."""
    with patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper:
        # Mock RedisClient instance - it uses .get() method
        mock_redis_wrapper.get = AsyncMock(return_value="1")
        
        cancelled = await check_cancellation("test_job_id")
        assert cancelled is True
        assert mock_redis_wrapper.get.called


@pytest.mark.asyncio
async def test_update_progress(mock_database_client, mock_redis_client, test_env_vars):
    """Test progress update."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast:
        
        # Mock database
        mock_result = MagicMock()
        mock_result.data = [{"id": "test_job"}]
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=mock_result)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.update = MagicMock(return_value=mock_query)
        mock_table = MagicMock()
        mock_table.update = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        # Mock Redis client
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.delete = AsyncMock(return_value=1)
        
        await update_progress("test_job_id", 50, "video_generation")
        
        # Verify database update was called
        assert mock_table.update.called
        # Verify cache invalidation
        assert mock_redis_client.delete.called
        # Verify events published
        assert mock_publish.called
        assert mock_broadcast.called


@pytest.mark.asyncio
async def test_handle_pipeline_error(mock_database_client, mock_redis_client, test_env_vars):
    """Test pipeline error handling."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish:
        
        from shared.errors import PipelineError
        
        # Mock database
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=MagicMock())
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.update = MagicMock(return_value=mock_query)
        mock_table = MagicMock()
        mock_table.update = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        # Mock Redis client
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.delete = AsyncMock(return_value=1)
        
        error = PipelineError("Test error", code="TEST_ERROR")
        await handle_pipeline_error("test_job_id", error)
        
        # Verify database update was called
        assert mock_table.update.called
        # Verify cache invalidation
        assert mock_redis_client.delete.called
        # Verify error event published
        assert mock_publish.called

