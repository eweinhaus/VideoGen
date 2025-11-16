"""
Integration tests for time estimation in orchestrator.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api_gateway.orchestrator import update_progress


@pytest.mark.asyncio
async def test_update_progress_includes_estimated_remaining_in_database(mock_database_client, mock_redis_client, test_env_vars):
    """Test that update_progress includes estimated_remaining in database update."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation to return a specific value
        mock_calculate.return_value = 300  # 5 minutes
        
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
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Call update_progress with audio_duration
        await update_progress(
            job_id="test_job_id",
            progress=50,
            stage_name="video_generator",
            audio_duration=180.0,
            num_clips=6
        )
        
        # Verify calculate_estimated_remaining was called
        assert mock_calculate.called
        call_args = mock_calculate.call_args
        assert call_args.kwargs["job_id"] == "test_job_id"
        assert call_args.kwargs["current_stage"] == "video_generator"
        assert call_args.kwargs["progress"] == 50
        assert call_args.kwargs["audio_duration"] == 180.0
        assert call_args.kwargs["num_clips"] == 6
        
        # Verify database update was called with estimated_remaining
        assert mock_table.update.called
        update_call_args = mock_table.update.call_args[0][0]
        assert "estimated_remaining" in update_call_args
        assert update_call_args["estimated_remaining"] == 300
        assert update_call_args["progress"] == 50
        assert update_call_args["current_stage"] == "video_generator"


@pytest.mark.asyncio
async def test_update_progress_progress_event_contains_estimated_remaining(mock_database_client, mock_redis_client, test_env_vars):
    """Test that progress events contain estimated_remaining."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation to return a specific value
        mock_calculate.return_value = 450  # 7.5 minutes
        
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
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Call update_progress
        await update_progress(
            job_id="test_job_id",
            progress=30,
            stage_name="audio_parser",
            audio_duration=120.0
        )
        
        # Verify publish_event was called with estimated_remaining
        assert mock_publish.called
        publish_call_args = mock_publish.call_args
        assert publish_call_args[0][0] == "test_job_id"  # job_id
        assert publish_call_args[0][1] == "progress"  # event_type
        progress_data = publish_call_args[0][2]  # progress_data
        assert "estimated_remaining" in progress_data
        assert progress_data["estimated_remaining"] == 450
        assert progress_data["progress"] == 30
        assert progress_data["stage"] == "audio_parser"
        
        # Verify broadcast_event was also called with estimated_remaining
        assert mock_broadcast.called
        broadcast_call_args = mock_broadcast.call_args
        assert broadcast_call_args[0][0] == "test_job_id"  # job_id
        assert broadcast_call_args[0][1] == "progress"  # event_type
        broadcast_data = broadcast_call_args[0][2]  # progress_data
        assert "estimated_remaining" in broadcast_data
        assert broadcast_data["estimated_remaining"] == 450


@pytest.mark.asyncio
async def test_update_progress_handles_none_gracefully(mock_database_client, mock_redis_client, test_env_vars):
    """Test that update_progress handles None estimated_remaining gracefully."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation to return None (e.g., no audio_duration)
        mock_calculate.return_value = None
        
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
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Call update_progress without audio_duration
        await update_progress(
            job_id="test_job_id",
            progress=25,
            stage_name="scene_planner"
        )
        
        # Verify calculate_estimated_remaining was NOT called (no audio_duration)
        assert not mock_calculate.called
        
        # Verify database update was called but WITHOUT estimated_remaining
        assert mock_table.update.called
        update_call_args = mock_table.update.call_args[0][0]
        assert "estimated_remaining" not in update_call_args
        assert update_call_args["progress"] == 25
        assert update_call_args["current_stage"] == "scene_planner"
        
        # Verify progress events still sent (with None estimated_remaining)
        assert mock_publish.called
        publish_call_args = mock_publish.call_args
        progress_data = publish_call_args[0][2]
        assert "estimated_remaining" in progress_data
        assert progress_data["estimated_remaining"] is None


@pytest.mark.asyncio
async def test_update_progress_retrieves_audio_duration_from_redis(mock_database_client, mock_redis_client, test_env_vars):
    """Test that update_progress retrieves audio_duration from Redis if not provided."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation to return a value
        mock_calculate.return_value = 240  # 4 minutes
        
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
        
        # Mock Redis client to return audio_duration
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_client.delete = AsyncMock(return_value=1)
        mock_redis_wrapper.get = AsyncMock(return_value="200.5")  # Audio duration in seconds
        
        # Call update_progress without audio_duration (should retrieve from Redis)
        await update_progress(
            job_id="test_job_id",
            progress=40,
            stage_name="prompt_generator"
        )
        
        # Verify Redis get was called for audio_duration
        assert mock_redis_wrapper.get.called
        redis_call_args = mock_redis_wrapper.get.call_args[0][0]
        assert redis_call_args == "job:test_job_id:audio_duration"
        
        # Verify calculate_estimated_remaining was called with Redis value
        assert mock_calculate.called
        call_args = mock_calculate.call_args
        assert call_args.kwargs["audio_duration"] == 200.5


@pytest.mark.asyncio
async def test_update_progress_with_num_images(mock_database_client, mock_redis_client, test_env_vars):
    """Test that update_progress passes num_images to estimation function."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation
        mock_calculate.return_value = 180  # 3 minutes
        
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
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Call update_progress with num_images (for reference_generator stage)
        await update_progress(
            job_id="test_job_id",
            progress=27,
            stage_name="reference_generator",
            audio_duration=150.0,
            num_images=4
        )
        
        # Verify calculate_estimated_remaining was called with num_images
        assert mock_calculate.called
        call_args = mock_calculate.call_args
        assert call_args.kwargs["num_images"] == 4
        assert call_args.kwargs["audio_duration"] == 150.0
        assert call_args.kwargs["current_stage"] == "reference_generator"


@pytest.mark.asyncio
async def test_update_progress_sse_broadcast_includes_estimated_remaining(mock_database_client, mock_redis_client, test_env_vars):
    """Test that SSE broadcast events include estimated_remaining."""
    with patch("api_gateway.orchestrator.db_client") as mock_db, \
         patch("api_gateway.orchestrator.redis_client") as mock_redis_wrapper, \
         patch("api_gateway.orchestrator.publish_event") as mock_publish, \
         patch("api_gateway.orchestrator.broadcast_event") as mock_broadcast, \
         patch("api_gateway.orchestrator.calculate_estimated_remaining") as mock_calculate:
        
        # Mock calculation
        mock_calculate.return_value = 600  # 10 minutes
        
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
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Call update_progress
        await update_progress(
            job_id="test_job_id",
            progress=60,
            stage_name="composer",
            audio_duration=240.0
        )
        
        # Verify broadcast_event was called (SSE)
        assert mock_broadcast.called
        broadcast_call_args = mock_broadcast.call_args
        assert broadcast_call_args[0][0] == "test_job_id"  # job_id
        assert broadcast_call_args[0][1] == "progress"  # event_type
        broadcast_data = broadcast_call_args[0][2]  # progress_data
        
        # Verify SSE data includes estimated_remaining
        assert "estimated_remaining" in broadcast_data
        assert broadcast_data["estimated_remaining"] == 600
        assert broadcast_data["progress"] == 60
        assert broadcast_data["stage"] == "composer"

