"""
SSE stream endpoint.

Real-time progress updates via Server-Sent Events.
"""

import asyncio
import json
from fastapi import APIRouter, Path, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from shared.redis_client import RedisClient
from shared.logging import get_logger
from api_gateway.dependencies import get_current_user, verify_job_ownership
from api_gateway.services.sse_manager import (
    add_connection,
    remove_connection,
    get_initial_state,
    get_connections,
    cleanup_stale_connections,
    update_connection_timestamp,
    MAX_CONNECTIONS_PER_JOB
)

logger = get_logger(__name__)

router = APIRouter()
redis_client = RedisClient()


async def event_generator(job_id: str):
    """
    Generate SSE events for a job.
    
    Args:
        job_id: Job ID to stream events for
        
    Yields:
        SSE formatted event strings
    """
    queue = asyncio.Queue()
    pubsub = None
    
    try:
        # Add connection
        await add_connection(job_id, queue)
        
        # Send initial state
        initial_state = await get_initial_state(job_id)
        initial_event = f"event: progress\ndata: {json.dumps(initial_state)}\n\n"
        yield initial_event
        
        # Start background task to subscribe to Redis pub/sub and forward to queue
        pubsub = redis_client.client.pubsub()
        channel = f"job_events:{job_id}"
        await pubsub.subscribe(channel)
        
        # Background task to listen to Redis pub/sub and forward to queue
        async def pubsub_listener():
            try:
                while True:
                    try:
                        message = await pubsub.get_message(timeout=1.0)
                        if message and message.get("type") == "message":
                            # Parse and format event
                            event_data_str = message.get("data")
                            if event_data_str:
                                if isinstance(event_data_str, bytes):
                                    event_data_str = event_data_str.decode("utf-8")
                                event_data = json.loads(event_data_str)
                                event_type = event_data.get("event_type")
                                data = event_data.get("data", {})
                                
                                # Format as SSE and put in queue
                                sse_message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                                await queue.put(sse_message)
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.debug("Pub/sub listener error", exc_info=e)
                        await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
        
        listener_task = asyncio.create_task(pubsub_listener())
        
        # Background cleanup task
        async def cleanup_task():
            try:
                while True:
                    await asyncio.sleep(30)  # Run every 30 seconds
                    removed = await cleanup_stale_connections()
                    if removed > 0:
                        logger.info(f"Cleaned up {removed} stale SSE connections")
            except asyncio.CancelledError:
                pass
        
        cleanup_task_obj = asyncio.create_task(cleanup_task())
        
        logger.info("SSE stream started", extra={"job_id": job_id})
        
        # Heartbeat interval
        heartbeat_interval = 30  # seconds
        last_heartbeat = asyncio.get_event_loop().time()
        
        # Main event loop
        while True:
            try:
                # Calculate timeout for next heartbeat
                current_time = asyncio.get_event_loop().time()
                time_since_heartbeat = current_time - last_heartbeat
                timeout = max(0.1, heartbeat_interval - time_since_heartbeat)
                
                # Wait for event from queue or timeout for heartbeat
                try:
                    event_message = await asyncio.wait_for(queue.get(), timeout=timeout)
                    yield event_message
                except asyncio.TimeoutError:
                    # Send heartbeat
                    from datetime import datetime
                    heartbeat_data = {"timestamp": datetime.utcnow().isoformat()}
                    heartbeat_event = f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
                    yield heartbeat_event
                    last_heartbeat = asyncio.get_event_loop().time()
                    
                    # Update connection timestamp
                    update_connection_timestamp(job_id, queue)
                
            except asyncio.CancelledError:
                logger.info("SSE stream cancelled", extra={"job_id": job_id})
                break
            except Exception as e:
                logger.error("Error in SSE stream", exc_info=e, extra={"job_id": job_id})
                error_event = f"event: error\ndata: {json.dumps({'error': 'Stream error'})}\n\n"
                yield error_event
                break
        
    finally:
        # Cancel background tasks
        if 'listener_task' in locals():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
        
        if 'cleanup_task_obj' in locals():
            cleanup_task_obj.cancel()
            try:
                await cleanup_task_obj
            except asyncio.CancelledError:
                pass
        
        # Cleanup
        await remove_connection(job_id, queue)
        if pubsub:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception as e:
                logger.warning("Failed to cleanup pub/sub", exc_info=e)
        
        logger.info("SSE stream ended", extra={"job_id": job_id})


@router.get("/jobs/{job_id}/stream")
async def stream_progress(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    SSE stream for real-time progress updates.
    
    Args:
        job_id: Job ID to stream events for
        current_user: Current authenticated user
        
    Returns:
        SSE stream response
    """
    # Verify job ownership
    try:
        await verify_job_ownership(job_id, current_user)
    except HTTPException as e:
        raise
    
    # Check connection limit
    connections_list = await get_connections(job_id)
    if len(connections_list) >= MAX_CONNECTIONS_PER_JOB:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Maximum {MAX_CONNECTIONS_PER_JOB} connections per job exceeded"
        )
    
    return StreamingResponse(
        event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )

