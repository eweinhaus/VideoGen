"""
SSE manager service.

Manages SSE connections and broadcasts events from Redis pub/sub.
"""

import json
import asyncio
import time
from typing import Dict, List, Optional
from fastapi.responses import StreamingResponse
from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)

redis_client = RedisClient()
db_client = DatabaseClient()

# Store active connections per job
connections: Dict[str, List[asyncio.Queue]] = {}
connections_lock = asyncio.Lock()

# Track last heartbeat timestamp per connection
connection_timestamps: Dict[str, Dict[asyncio.Queue, float]] = {}

MAX_CONNECTIONS_PER_JOB = 10


async def add_connection(job_id: str, queue: asyncio.Queue) -> None:
    """
    Add an SSE connection for a job.
    
    Args:
        job_id: Job ID
        queue: Queue for sending events to this connection
        
    Raises:
        ValueError: If max connections exceeded
    """
    async with connections_lock:
        if job_id not in connections:
            connections[job_id] = []
        
        if len(connections[job_id]) >= MAX_CONNECTIONS_PER_JOB:
            raise ValueError(f"Maximum {MAX_CONNECTIONS_PER_JOB} connections per job exceeded")
        
        connections[job_id].append(queue)
        
        # Track connection timestamp
        if job_id not in connection_timestamps:
            connection_timestamps[job_id] = {}
        connection_timestamps[job_id][queue] = time.time()
        
        logger.debug("SSE connection added", extra={"job_id": job_id, "total": len(connections[job_id])})


async def remove_connection(job_id: str, queue: asyncio.Queue) -> None:
    """
    Remove an SSE connection for a job.
    
    Args:
        job_id: Job ID
        queue: Queue to remove
    """
    async with connections_lock:
        if job_id in connections:
            try:
                connections[job_id].remove(queue)
                if len(connections[job_id]) == 0:
                    del connections[job_id]
                logger.debug("SSE connection removed", extra={"job_id": job_id})
            except ValueError:
                pass  # Queue not in list
        
        # Remove timestamp
        if job_id in connection_timestamps and queue in connection_timestamps[job_id]:
            del connection_timestamps[job_id][queue]
            if not connection_timestamps[job_id]:
                del connection_timestamps[job_id]


async def get_connections(job_id: str) -> List[asyncio.Queue]:
    """
    Get all connections for a job.
    
    Args:
        job_id: Job ID
        
    Returns:
        List of connection queues
    """
    async with connections_lock:
        return connections.get(job_id, []).copy()


async def broadcast_event(job_id: str, event_type: str, data: dict) -> None:
    """
    Broadcast an event to all connections for a job.
    
    Args:
        job_id: Job ID
        event_type: Event type
        data: Event data
    """
    connections_list = await get_connections(job_id)
    
    if not connections_list:
        return  # No connections, discard event
    
    # Format as SSE message
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    
    # Broadcast to all connections
    for queue in connections_list:
        try:
            await queue.put(message)
        except Exception as e:
            logger.warning("Failed to send event to connection", exc_info=e, extra={"job_id": job_id})


async def get_initial_state(job_id: str) -> dict:
    """
    Get current job state for initial SSE message.
    
    Args:
        job_id: Job ID
        
    Returns:
        Current job state dictionary
    """
    try:
        result = await db_client.table("jobs").select("*").eq("id", job_id).execute()
        if result.data and len(result.data) > 0:
            job = result.data[0]
            return {
                "progress": job.get("progress", 0),
                "stage": job.get("current_stage"),
                "status": job.get("status"),
                "total_cost": job.get("total_cost", 0)
            }
    except Exception as e:
        logger.warning("Failed to get initial state", exc_info=e, extra={"job_id": job_id})
    
    return {"progress": 0, "stage": None, "status": "queued", "total_cost": 0}


async def cleanup_stale_connections(timeout_seconds: int = 60) -> int:
    """
    Remove connections with no heartbeat for >timeout_seconds.
    
    Args:
        timeout_seconds: Seconds of inactivity before considering connection stale
        
    Returns:
        Number of connections removed
    """
    current_time = time.time()
    removed_count = 0
    
    async with connections_lock:
        for job_id, queues in list(connections.items()):
            if job_id not in connection_timestamps:
                continue
                
            timestamps = connection_timestamps[job_id]
            for queue, last_heartbeat in list(timestamps.items()):
                if current_time - last_heartbeat > timeout_seconds:
                    # Remove stale connection
                    try:
                        queues.remove(queue)
                        del timestamps[queue]
                        removed_count += 1
                        logger.info(
                            "Removed stale SSE connection",
                            extra={
                                "job_id": job_id,
                                "inactive_seconds": current_time - last_heartbeat
                            }
                        )
                    except (ValueError, KeyError):
                        pass  # Already removed
                    
            # Clean up empty job entries
            if not queues:
                del connections[job_id]
            if not timestamps:
                del connection_timestamps[job_id]
    
    return removed_count


def update_connection_timestamp(job_id: str, queue: asyncio.Queue) -> None:
    """
    Update heartbeat timestamp for a connection.
    
    Args:
        job_id: Job ID
        queue: Connection queue
    """
    if job_id in connection_timestamps and queue in connection_timestamps[job_id]:
        connection_timestamps[job_id][queue] = time.time()

