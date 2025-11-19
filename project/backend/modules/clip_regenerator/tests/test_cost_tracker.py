"""
Unit tests for cost tracker module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from decimal import Decimal

from modules.clip_regenerator.cost_tracker import (
    track_regeneration_cost,
    get_regeneration_history
)
from shared.errors import ValidationError


@pytest.fixture
def mock_database_client():
    """Mock database client for testing."""
    mock_client = AsyncMock()
    mock_table = MagicMock()
    mock_table.insert = MagicMock(return_value=mock_table)
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.eq = MagicMock(return_value=mock_table)
    mock_table.single = MagicMock(return_value=mock_table)
    mock_table.update = MagicMock(return_value=mock_table)
    mock_table.order = MagicMock(return_value=mock_table)
    mock_table.execute = AsyncMock()
    mock_client.table = MagicMock(return_value=mock_table)
    return mock_client


@pytest.mark.asyncio
async def test_track_regeneration_cost_success(mock_database_client):
    """Test successful cost tracking."""
    job_id = uuid4()
    
    # Mock job lookup for total_cost update
    mock_job_result = MagicMock()
    mock_job_result.data = {"total_cost": 10.0}
    
    # Create proper chain for select().eq().single().execute()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.single.return_value.execute = AsyncMock(return_value=mock_job_result)
    mock_database_client.table.return_value.select.return_value = mock_select_chain
    
    # Mock insert and update operations
    mock_table = mock_database_client.table.return_value
    mock_table.insert.return_value.execute = AsyncMock()
    mock_update_chain = MagicMock()
    mock_update_chain.eq.return_value.execute = AsyncMock()
    mock_table.update.return_value = mock_update_chain
    
    with patch("modules.clip_regenerator.cost_tracker.db_client", mock_database_client):
        await track_regeneration_cost(
            job_id=job_id,
            clip_index=0,
            original_prompt="Original prompt",
            modified_prompt="Modified prompt",
            user_instruction="make it brighter",
            conversation_history=[],
            cost=Decimal("0.15"),
            status="completed"
        )
    
    # Verify insert was called
    mock_table.insert.assert_called_once()


@pytest.mark.asyncio
async def test_track_regeneration_cost_invalid_status(mock_database_client):
    """Test cost tracking with invalid status."""
    job_id = uuid4()
    
    with patch("modules.clip_regenerator.cost_tracker.db_client", mock_database_client):
        with pytest.raises(ValidationError, match="Invalid status"):
            await track_regeneration_cost(
                job_id=job_id,
                clip_index=0,
                original_prompt="Original",
                modified_prompt="Modified",
                user_instruction="test",
                cost=Decimal("0.15"),
                status="invalid_status"
            )


@pytest.mark.asyncio
async def test_get_regeneration_history(mock_database_client):
    """Test getting regeneration history."""
    job_id = uuid4()
    
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [
        {
            "id": str(uuid4()),
            "job_id": str(job_id),
            "clip_index": 0,
            "cost": 0.15,
            "status": "completed",
            "created_at": "2025-01-17T10:00:00Z"
        }
    ]
    mock_table = mock_database_client.table.return_value
    mock_table.order.return_value.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.cost_tracker.db_client", mock_database_client):
        history = await get_regeneration_history(job_id, clip_index=0)
    
    assert len(history) == 1
    assert history[0]["clip_index"] == 0
    assert history[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_regeneration_history_empty(mock_database_client):
    """Test getting regeneration history when none exists."""
    job_id = uuid4()
    
    # Mock empty database response
    mock_result = MagicMock()
    mock_result.data = None
    mock_table = mock_database_client.table.return_value
    mock_table.order.return_value.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.cost_tracker.db_client", mock_database_client):
        history = await get_regeneration_history(job_id)
    
    assert history == []

