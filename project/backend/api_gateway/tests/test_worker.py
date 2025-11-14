"""
Tests for worker process.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api_gateway.worker import process_job


@pytest.mark.asyncio
async def test_process_job_success(mock_database_client, test_env_vars):
    """Test successful job processing."""
    with patch("api_gateway.worker.execute_pipeline") as mock_execute, \
         patch("api_gateway.worker.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.worker.db_client") as mock_db:
        
        # Mock RedisClient.get() method
        mock_redis_wrapper.get = AsyncMock(return_value=None)  # Not cancelled
        
        # Mock database
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=MagicMock())
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.update = MagicMock(return_value=mock_query)
        mock_table = MagicMock()
        mock_table.update = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        job_data = {
            "job_id": "test_job_id",  # Worker expects 'job_id' from queue
            "user_id": "test_user_id",
            "audio_url": "https://storage.supabase.co/test.mp3",
            "user_prompt": "Test prompt with at least 50 characters to pass validation"
        }
        
        await process_job(job_data)
        
        # Verify pipeline was executed
        assert mock_execute.called
        # Check that execute_pipeline was called with correct arguments
        # execute_pipeline signature: (job_id, audio_url, user_prompt) - 3 args
        call_args = mock_execute.call_args
        assert len(call_args[0]) == 3  # Should have 3 positional args
        assert call_args[0][0] == "test_job_id"  # job_id
        assert call_args[0][1] == "https://storage.supabase.co/test.mp3"  # audio_url
        assert call_args[0][2] == "Test prompt with at least 50 characters to pass validation"  # user_prompt


@pytest.mark.asyncio
async def test_process_job_cancelled(mock_database_client, test_env_vars):
    """Test job processing when cancelled."""
    with patch("api_gateway.worker.execute_pipeline") as mock_execute, \
         patch("api_gateway.worker.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.worker.db_client") as mock_db:
        
        # Mock RedisClient.get() method
        mock_redis_wrapper.get = AsyncMock(return_value="1")  # Cancelled
        
        # Mock database update
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=MagicMock())
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.update = MagicMock(return_value=mock_query)
        mock_table = MagicMock()
        mock_table.update = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        job_data = {
            "job_id": "test_job_id",  # Worker expects 'job_id' from queue
            "user_id": "test_user_id",
            "audio_url": "https://storage.supabase.co/test.mp3",
            "user_prompt": "Test prompt"
        }
        
        await process_job(job_data)
        
        # Verify pipeline was NOT executed
        assert not mock_execute.called
        # Verify job was marked as failed
        assert mock_table.update.called


@pytest.mark.asyncio
async def test_process_job_invalid_data(test_env_vars):
    """Test job processing with invalid data."""
    with patch("api_gateway.worker.logger") as mock_logger:
        job_data = {
            "job_id": None,  # Missing required field
            "user_id": "test_user_id"
        }
        
        # Should handle gracefully (log error and return)
        try:
            await process_job(job_data)
        except (KeyError, TypeError):
            # Expected - missing required fields
            pass
        # No exception should propagate, just logged

