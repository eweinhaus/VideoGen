"""
Character analysis API routes.
"""

from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from api_gateway.dependencies import get_current_user
from api_gateway.services.rate_limiter import check_rate_limit
from api_gateway.services.character_analysis_service import (
    create_analysis_job,
    get_analysis_job,
)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    image_url: str
    analysis_version: str = Field(default="v1")


@router.post("/upload/character/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_character_image_route(
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Start asynchronous character analysis and return a job id.
    """
    # Rate limit check (reuse existing limiter; can adjust limit later)
    await check_rate_limit(current_user["user_id"])

    job_id = await create_analysis_job(
        user_id=current_user["user_id"],
        image_url=body.image_url,
        analysis_version=body.analysis_version,
        background_tasks=background_tasks,
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/upload/character/analyze/{job_id}")
async def get_character_analysis_result(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Poll for character analysis result.
    """
    job = await get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    # Basic ownership check: match user_id
    if job.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Forbidden")

    status_value = job.get("status")
    if status_value == "completed":
        return job.get("result")
    if status_value == "failed":
        raise HTTPException(status_code=502, detail="Provider failure")
    # processing or queued
    return {"status": "processing"}


