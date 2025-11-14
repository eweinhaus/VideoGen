"""
Health check endpoint.

Monitors service health (database, Redis, queue).
"""

import json
from datetime import datetime
from fastapi import APIRouter, Response
from shared.database import DatabaseClient
from shared.redis_client import RedisClient
from shared.logging import get_logger
from api_gateway.services.queue_service import get_queue_size

logger = get_logger(__name__)

router = APIRouter()
db_client = DatabaseClient()
redis_client = RedisClient()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status with service checks
    """
    issues = []
    status_code = 200
    
    # Check database
    db_healthy = await db_client.health_check()
    if not db_healthy:
        issues.append("database connection failed")
        status_code = 503
    
    # Check Redis
    try:
        await redis_client.client.ping()
        redis_healthy = True
    except Exception:
        redis_healthy = False
        issues.append("redis connection failed")
        status_code = 503
    
    # Check queue
    try:
        queue_size = await get_queue_size()
        queue_healthy = True
    except Exception:
        queue_healthy = False
        issues.append("queue connection failed")
        status_code = 503
    
    response = {
        "status": "healthy" if status_code == 200 else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "queue": {
            "size": queue_size if queue_healthy else 0,
            "active_jobs": 0,  # TODO: Track active jobs
            "workers": 2  # TODO: Track actual worker count
        },
        "database": "connected" if db_healthy else "disconnected",
        "redis": "connected" if redis_healthy else "disconnected"
    }
    
    if issues:
        response["issues"] = issues
    
    return Response(
        content=json.dumps(response),
        status_code=status_code,
        media_type="application/json"
    )

