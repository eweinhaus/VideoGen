"""
Character analysis service.

Creates and processes asynchronous character analysis jobs backed by Redis.
"""

import json
import uuid
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import BackgroundTasks

from shared.logging import get_logger
from shared.database import db
from shared.redis_client import RedisClient

from modules.character_analyzer.vision import analyze_character_image

logger = get_logger(__name__)
redis_client = RedisClient()

REDIS_PREFIX = "character_analysis"


async def create_analysis_job(
    user_id: str,
    image_url: str,
    analysis_version: str = "v1",
    background_tasks: Optional[BackgroundTasks] = None,
) -> str:
    """
    Create an analysis job and schedule background processing.
    Returns analysis job_id.
    """
    job_id = str(uuid.uuid4())
    key = f"{REDIS_PREFIX}:job:{job_id}"
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "image_url": image_url,
        "analysis_version": analysis_version,
        "status": "queued",
    }
    await redis_client.set_json(key, job_data, ttl=1800)  # 30 min TTL

    # Schedule background processing
    if background_tasks is not None:
        background_tasks.add_task(process_analysis_job, job_id)
    else:
        # Fallback (tests) - process inline
        await process_analysis_job(job_id)

    return job_id


async def get_analysis_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Load analysis job status/result from Redis."""
    key = f"{REDIS_PREFIX}:job:{job_id}"
    return await redis_client.get_json(key)


async def process_analysis_job(job_id: str) -> None:
    """
    Background job: perform analysis and persist results.
    """
    key = f"{REDIS_PREFIX}:job:{job_id}"
    job = await redis_client.get_json(key)
    if not job:
        logger.warning("Analysis job not found", extra={"job_id": job_id})
        return

    if job.get("status") in {"completed", "failed"}:
        return

    # Mark processing
    job["status"] = "processing"
    await redis_client.set_json(key, job, ttl=1800)

    try:
        # Perform analysis (mock mode controlled by env)
        result = await analyze_character_image(
            image_url=job["image_url"],
            job_id=UUID(job_id),
            user_id=job.get("user_id"),
            use_mock=None,
        )

        normalized = result.get("analysis") or {}
        warnings = result.get("warnings") or []
        used_cache = bool(result.get("used_cache", False))

        # Persistence handled by analyzer (cache store). We only return Redis result.

        # Save result to Redis for GET endpoint
        job.update(
            {
                "status": "completed",
                "result": {
                    "image_url": job["image_url"],
                    "analysis": normalized,
                    "warnings": warnings,
                    "used_cache": used_cache,
                },
            }
        )
        await redis_client.set_json(key, job, ttl=1800)

    except Exception as e:
        logger.error("Character analysis failed", exc_info=e, extra={"job_id": job_id})
        job["status"] = "failed"
        job["error"] = str(e)
        await redis_client.set_json(key, job, ttl=1800)


