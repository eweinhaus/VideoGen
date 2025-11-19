"""
Analytics endpoints.

Part 6: Comparison Tools & Analytics
"""
import csv
import io
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Path, Depends, HTTPException, status, Query
from fastapi.responses import Response

from shared.database import DatabaseClient
from shared.logging import get_logger
from shared.redis_client import RedisClient
from api_gateway.dependencies import get_current_user, verify_job_ownership
from modules.analytics.metrics import calculate_job_metrics, calculate_user_metrics
from modules.analytics.aggregation import get_job_analytics, get_user_analytics

logger = get_logger(__name__)

router = APIRouter()
db_client = DatabaseClient()
redis_client = RedisClient()


@router.get("/jobs/{job_id}/analytics")
async def get_job_analytics_endpoint(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Get regeneration analytics for a job.
    
    Args:
        job_id: Job ID
        current_user: Current authenticated user
        
    Returns:
        JSON response with job analytics metrics
        
    Raises:
        HTTPException: 404 if job not found, 403 if access denied
    """
    try:
        # Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # Get analytics data (with caching for older data)
        analytics_data = await get_job_analytics(UUID(job_id))
        
        # Calculate metrics
        metrics = calculate_job_metrics(analytics_data)
        
        logger.info(
            f"Job analytics retrieved",
            extra={
                "job_id": job_id,
                "total_regenerations": metrics.get("total_regenerations", 0)
            }
        )
        
        return {
            "job_id": job_id,
            **metrics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get job analytics: {e}",
            extra={"job_id": job_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job analytics"
        )


@router.get("/users/{user_id}/analytics")
async def get_user_analytics_endpoint(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Get user-wide analytics across all jobs.
    
    Args:
        user_id: User ID
        current_user: Current authenticated user
        
    Returns:
        JSON response with user analytics metrics
        
    Raises:
        HTTPException: 403 if user_id doesn't match current user
    """
    try:
        # Verify user_id matches current user
        if user_id != current_user.get("user_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's analytics"
            )
        
        # Get analytics data (with caching)
        analytics_data = await get_user_analytics(UUID(user_id))
        
        # Calculate metrics
        metrics = calculate_user_metrics(analytics_data)
        
        logger.info(
            f"User analytics retrieved",
            extra={
                "user_id": user_id,
                "total_regenerations": metrics.get("total_regenerations", 0)
            }
        )
        
        return {
            "user_id": user_id,
            **metrics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get user analytics: {e}",
            extra={"user_id": user_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user analytics"
        )


@router.get("/jobs/{job_id}/analytics/export")
async def export_job_analytics(
    job_id: str = Path(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Export job analytics as CSV.
    
    Args:
        job_id: Job ID
        current_user: Current authenticated user
        
    Returns:
        CSV file with analytics data
        
    Raises:
        HTTPException: 404 if job not found, 403 if access denied
    """
    try:
        # Verify job ownership
        job = await verify_job_ownership(job_id, current_user)
        
        # Query all analytics for job
        result = await db_client.table("regeneration_analytics").select("*").eq(
            "job_id", job_id
        ).order("created_at", desc=False).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analytics data found for this job"
            )
        
        # Format as CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "timestamp",
            "clip_index",
            "instruction",
            "template_id",
            "cost",
            "success"
        ])
        
        # Write data rows
        for record in result.data:
            writer.writerow([
                record.get("created_at", ""),
                record.get("clip_index", ""),
                record.get("instruction", ""),
                record.get("template_id", ""),
                record.get("cost", ""),
                record.get("success", False)
            ])
        
        # Generate filename
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"job_{job_id}_analytics_{date_str}.csv"
        
        logger.info(
            f"Analytics exported to CSV",
            extra={"job_id": job_id, "row_count": len(result.data)}
        )
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to export analytics: {e}",
            extra={"job_id": job_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export analytics"
        )

