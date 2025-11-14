"""
Tests for SSE manager service.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from api_gateway.services.sse_manager import (
    add_connection,
    remove_connection,
    get_connections,
    broadcast_event,
    get_initial_state,
    MAX_CONNECTIONS_PER_JOB
)


@pytest.mark.asyncio
async def test_add_connection():
    """Test adding SSE connection."""
    from api_gateway.services.sse_manager import connections, connections_lock
    
    # Clear connections
    async with connections_lock:
        connections.clear()
    
    job_id = "test_job_id"
    queue = asyncio.Queue()
    
    await add_connection(job_id, queue)
    
    # Verify connection was added
    conns = await get_connections(job_id)
    assert len(conns) == 1
    assert queue in conns


@pytest.mark.asyncio
async def test_remove_connection():
    """Test removing SSE connection."""
    from api_gateway.services.sse_manager import connections, connections_lock
    
    # Clear and add connection
    async with connections_lock:
        connections.clear()
    
    job_id = "test_job_id"
    queue = asyncio.Queue()
    
    await add_connection(job_id, queue)
    await remove_connection(job_id, queue)
    
    # Verify connection was removed
    conns = await get_connections(job_id)
    assert len(conns) == 0


@pytest.mark.asyncio
async def test_max_connections_per_job():
    """Test maximum connections limit."""
    from api_gateway.services.sse_manager import connections, connections_lock
    
    # Clear connections
    async with connections_lock:
        connections.clear()
    
    job_id = "test_job_id"
    
    # Add max connections
    queues = []
    for i in range(MAX_CONNECTIONS_PER_JOB):
        queue = asyncio.Queue()
        await add_connection(job_id, queue)
        queues.append(queue)
    
    # Try to add one more (should fail)
    extra_queue = asyncio.Queue()
    with pytest.raises(ValueError, match=f"Maximum {MAX_CONNECTIONS_PER_JOB}"):
        await add_connection(job_id, extra_queue)
    
    # Cleanup
    for queue in queues:
        await remove_connection(job_id, queue)


@pytest.mark.asyncio
async def test_broadcast_event():
    """Test event broadcasting to connections."""
    from api_gateway.services.sse_manager import connections, connections_lock
    
    # Clear connections
    async with connections_lock:
        connections.clear()
    
    job_id = "test_job_id"
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()
    
    await add_connection(job_id, queue1)
    await add_connection(job_id, queue2)
    
    # Broadcast event
    await broadcast_event(job_id, "progress", {"progress": 50})
    
    # Verify both queues received the event
    event1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    event2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
    
    assert "event: progress" in event1
    assert "event: progress" in event2
    assert "progress" in event1
    assert "progress" in event2
    
    # Cleanup
    await remove_connection(job_id, queue1)
    await remove_connection(job_id, queue2)


@pytest.mark.asyncio
async def test_broadcast_event_no_connections():
    """Test broadcasting when no connections exist."""
    from api_gateway.services.sse_manager import connections, connections_lock
    
    # Clear connections
    async with connections_lock:
        connections.clear()
    
    job_id = "test_job_id"
    
    # Should not raise error, just return
    await broadcast_event(job_id, "progress", {"progress": 50})


@pytest.mark.asyncio
async def test_get_initial_state(mock_database_client):
    """Test initial state retrieval."""
    with patch("api_gateway.services.sse_manager.db_client") as mock_db:
        mock_db.table = mock_database_client.table
        
        job_id = "test_job_id"
        
        # Mock database result
        mock_result = MagicMock()
        mock_result.data = [{
            "id": job_id,
            "progress": 30,
            "current_stage": "video_generation",
            "status": "processing",
            "total_cost": 150.50
        }]
        mock_db.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(return_value=mock_result)
        
        state = await get_initial_state(job_id)
        
        assert state["progress"] == 30
        assert state["stage"] == "video_generation"
        assert state["status"] == "processing"
        assert state["total_cost"] == 150.50
