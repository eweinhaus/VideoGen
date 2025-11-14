"""
Tests for cost tracking utilities.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import sys

# Mock supabase and its submodules before importing shared modules
mock_supabase = Mock()
mock_supabase.lib = Mock()
mock_supabase.lib.client_options = Mock()
mock_supabase.lib.client_options.ClientOptions = Mock
sys.modules['supabase'] = mock_supabase
sys.modules['supabase.lib'] = mock_supabase.lib
sys.modules['supabase.lib.client_options'] = mock_supabase.lib.client_options

from shared.cost_tracking import CostTracker
from shared.errors import BudgetExceededError, RetryableError, ValidationError


@pytest.fixture
def mock_db():
    """Create a mock database client."""
    db = Mock()
    db.table = Mock()
    return db


@pytest.fixture
def cost_tracker(mock_db):
    """Create a cost tracker with mocked database."""
    with patch("shared.cost_tracking.db", mock_db):
        tracker = CostTracker()
        return tracker, mock_db


@pytest.mark.asyncio
async def test_track_cost(cost_tracker):
    """Test tracking a cost for a job."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    # Mock database responses - need to properly chain query builder
    mock_insert_result = Mock()
    mock_insert_result.execute = AsyncMock(return_value=Mock())
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 0.0}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_update_result = Mock()
    mock_update_result.execute = AsyncMock(return_value=Mock())
    mock_update_result.eq = Mock(return_value=mock_update_result)
    
    # Setup table mock to return appropriate query builders
    def table_side_effect(table_name):
        table_mock = Mock()
        if table_name == "job_costs":
            table_mock.insert = Mock(return_value=mock_insert_result)
        elif table_name == "jobs":
            table_mock.select = Mock(return_value=mock_select_result)
            table_mock.update = Mock(return_value=mock_update_result)
        return table_mock
    
    mock_db.table = Mock(side_effect=table_side_effect)
    
    await tracker.track_cost(
        job_id=job_id,
        stage_name="video_generation",
        api_name="svd",
        cost=Decimal("0.06")
    )
    
    # Verify cost was inserted
    mock_db.table.assert_any_call("job_costs")
    mock_insert_result.execute.assert_called_once()


@pytest.mark.asyncio
async def test_track_cost_negative_raises_error(cost_tracker):
    """Test that negative cost raises ValidationError."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    with pytest.raises(ValidationError, match="Cost cannot be negative"):
        await tracker.track_cost(
            job_id=job_id,
            stage_name="test",
            api_name="test",
            cost=Decimal("-0.10")
        )


@pytest.mark.asyncio
async def test_get_total_cost(cost_tracker):
    """Test getting total cost for a job."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 1.50}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    total = await tracker.get_total_cost(job_id)
    
    assert total == Decimal("1.50")


@pytest.mark.asyncio
async def test_get_total_cost_no_job(cost_tracker):
    """Test getting total cost for non-existent job."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    total = await tracker.get_total_cost(job_id)
    
    assert total == Decimal("0.00")


@pytest.mark.asyncio
async def test_check_budget_within_limit(cost_tracker):
    """Test that budget check returns True when within limit."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 5.00}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    can_proceed = await tracker.check_budget(
        job_id=job_id,
        new_cost=Decimal("10.00"),
        limit=Decimal("20.00")
    )
    
    assert can_proceed is True  # 5.00 + 10.00 = 15.00 <= 20.00


@pytest.mark.asyncio
async def test_check_budget_exceeds_limit(cost_tracker):
    """Test that budget check returns False when exceeds limit."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 15.00}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    can_proceed = await tracker.check_budget(
        job_id=job_id,
        new_cost=Decimal("10.00"),
        limit=Decimal("20.00")
    )
    
    assert can_proceed is False  # 15.00 + 10.00 = 25.00 > 20.00


@pytest.mark.asyncio
async def test_enforce_budget_limit_within_limit(cost_tracker):
    """Test that enforce_budget_limit doesn't raise when within limit."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 10.00}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    # Should not raise
    await tracker.enforce_budget_limit(job_id, limit=Decimal("20.00"))


@pytest.mark.asyncio
async def test_enforce_budget_limit_exceeds_raises_error(cost_tracker):
    """Test that enforce_budget_limit raises BudgetExceededError when exceeded."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 25.00}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    with pytest.raises(BudgetExceededError, match="Budget limit.*exceeded"):
        await tracker.enforce_budget_limit(job_id, limit=Decimal("20.00"))


@pytest.mark.asyncio
async def test_concurrent_cost_tracking(cost_tracker):
    """Test that concurrent cost tracking uses locks correctly."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    # Mock database responses - need to properly chain query builder
    mock_insert_result = Mock()
    mock_insert_result.execute = AsyncMock(return_value=Mock())
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(return_value=Mock(data=[{"total_cost": 0.0}]))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_update_result = Mock()
    mock_update_result.execute = AsyncMock(return_value=Mock())
    mock_update_result.eq = Mock(return_value=mock_update_result)
    
    # Setup table mock to return appropriate query builders
    def table_side_effect(table_name):
        table_mock = Mock()
        if table_name == "job_costs":
            table_mock.insert = Mock(return_value=mock_insert_result)
        elif table_name == "jobs":
            table_mock.select = Mock(return_value=mock_select_result)
            table_mock.update = Mock(return_value=mock_update_result)
        return table_mock
    
    mock_db.table = Mock(side_effect=table_side_effect)
    
    # Track costs concurrently (simulating 5 parallel video clips)
    tasks = [
        tracker.track_cost(
            job_id=job_id,
            stage_name="video_generation",
            api_name="svd",
            cost=Decimal("0.06")
        )
        for _ in range(5)
    ]
    
    await asyncio.gather(*tasks)
    
    # Verify all costs were tracked (5 calls to insert)
    assert mock_insert_result.execute.call_count == 5


@pytest.mark.asyncio
async def test_track_cost_raises_retryable_error(cost_tracker):
    """Test that track_cost raises RetryableError on database failure."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_insert = Mock()
    mock_db.table.return_value.insert = Mock(return_value=mock_insert)
    mock_insert.execute = AsyncMock(side_effect=Exception("Database error"))
    
    with pytest.raises(RetryableError, match="Failed to track cost"):
        await tracker.track_cost(
            job_id=job_id,
            stage_name="test",
            api_name="test",
            cost=Decimal("0.10")
        )


@pytest.mark.asyncio
async def test_get_total_cost_raises_retryable_error(cost_tracker):
    """Test that get_total_cost raises RetryableError on database failure."""
    tracker, mock_db = cost_tracker
    job_id = uuid4()
    
    mock_select_result = Mock()
    mock_select_result.execute = AsyncMock(side_effect=Exception("Database error"))
    mock_select_result.eq = Mock(return_value=mock_select_result)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_select_result)
    mock_db.table = Mock(return_value=mock_table)
    
    with pytest.raises(RetryableError, match="Failed to get total cost"):
        await tracker.get_total_cost(job_id)

