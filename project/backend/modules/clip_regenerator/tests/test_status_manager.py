"""
Unit tests for status manager module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from modules.clip_regenerator.status_manager import (
    acquire_job_lock,
    update_job_status,
    release_job_lock
)
from shared.errors import ValidationError


@pytest.fixture
def mock_database_client():
    """Mock database client for testing."""
    mock_client = AsyncMock()
    mock_table = MagicMock()
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.eq = MagicMock(return_value=mock_table)
    mock_table.single = MagicMock(return_value=mock_table)
    mock_table.update = MagicMock(return_value=mock_table)
    mock_client.table = MagicMock(return_value=mock_table)
    return mock_client


@pytest.mark.asyncio
async def test_acquire_job_lock_success(mock_database_client):
    """Test successful lock acquisition."""
    job_id = uuid4()
    
    # Mock job status check - returns "completed"
    mock_result = MagicMock()
    mock_result.data = {"status": "completed"}
    
    # Create proper chain for select().eq().single().execute()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.single.return_value.execute = AsyncMock(return_value=mock_result)
    mock_database_client.table.return_value.select.return_value = mock_select_chain
    
    # Mock status update - succeeds
    mock_update_result = MagicMock()
    mock_update_result.data = [{"status": "regenerating"}]
    mock_update_chain = MagicMock()
    mock_update_chain.eq.return_value.eq.return_value.execute = AsyncMock(return_value=mock_update_result)
    mock_database_client.table.return_value.update.return_value = mock_update_chain
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        result = await acquire_job_lock(job_id)
    
    assert result is True


@pytest.mark.asyncio
async def test_acquire_job_lock_already_locked(mock_database_client):
    """Test lock acquisition when job is already regenerating."""
    job_id = uuid4()
    
    # Mock job status check - returns "regenerating"
    mock_result = MagicMock()
    mock_result.data = {"status": "regenerating"}
    
    # Create proper chain for select().eq().single().execute()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.single.return_value.execute = AsyncMock(return_value=mock_result)
    mock_database_client.table.return_value.select.return_value = mock_select_chain
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        result = await acquire_job_lock(job_id)
    
    assert result is False


@pytest.mark.asyncio
async def test_acquire_job_lock_job_not_found(mock_database_client):
    """Test lock acquisition when job doesn't exist."""
    job_id = uuid4()
    
    # Mock job status check - returns None (job not found)
    mock_result = MagicMock()
    mock_result.data = None
    
    # Create proper chain for select().eq().single().execute()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.single.return_value.execute = AsyncMock(return_value=mock_result)
    mock_database_client.table.return_value.select.return_value = mock_select_chain
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        with pytest.raises(ValidationError):
            await acquire_job_lock(job_id)


@pytest.mark.asyncio
async def test_update_job_status_success(mock_database_client):
    """Test successful job status update."""
    job_id = uuid4()
    
    # Mock current status check
    mock_result = MagicMock()
    mock_result.data = {"status": "regenerating"}
    mock_table = mock_database_client.table.return_value
    mock_table.single.execute = AsyncMock(return_value=mock_result)
    
    # Mock status update
    mock_update_result = MagicMock()
    mock_update_result.data = [{"status": "completed"}]
    mock_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=mock_update_result)
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        await update_job_status(job_id, "completed", video_url="https://example.com/video.mp4")
    
    # Verify update was called
    mock_table.update.assert_called()


@pytest.mark.asyncio
async def test_update_job_status_invalid_transition(mock_database_client):
    """Test status update with invalid transition."""
    job_id = uuid4()
    
    # Mock current status check - returns "completed"
    mock_result = MagicMock()
    mock_result.data = {"status": "completed"}
    
    # Create proper chain for select().eq().single().execute()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.single.return_value.execute = AsyncMock(return_value=mock_result)
    mock_database_client.table.return_value.select.return_value = mock_select_chain
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        # Try to transition from "completed" to "failed" (invalid)
        with pytest.raises(ValidationError):
            await update_job_status(job_id, "failed")


@pytest.mark.asyncio
async def test_release_job_lock(mock_database_client):
    """Test releasing job lock (no-op, mainly for logging)."""
    job_id = uuid4()
    
    with patch("modules.clip_regenerator.status_manager.db_client", mock_database_client):
        # Should not raise any errors
        await release_job_lock(job_id)

