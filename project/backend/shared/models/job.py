"""
Job-related data models.

Defines Job, JobStage, and JobCost models for tracking pipeline execution.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


class Job(BaseModel):
    """Job model representing a video generation job."""
    
    id: UUID
    user_id: UUID
    status: Literal["queued", "processing", "completed", "failed", "regenerating"]
    audio_url: str
    user_prompt: str
    current_stage: Optional[str] = None
    stop_at_stage: Optional[str] = Field(default=None, description="Optional stage to stop at for testing")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage 0-100")
    estimated_remaining: Optional[int] = Field(default=None, description="Estimated remaining time in seconds")
    total_cost: Decimal = Field(default=Decimal("0.00"), description="Total cost in USD")
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    @field_serializer("id", "user_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("total_cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)
    
    @field_serializer("created_at", "updated_at", "completed_at")
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        return value.isoformat() if value else None


class JobStage(BaseModel):
    """Job stage model for tracking individual pipeline stages."""
    
    id: UUID
    job_id: UUID
    stage_name: str
    status: Literal["pending", "processing", "completed", "failed"]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    cost: Decimal = Field(default=Decimal("0.00"))
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="JSONB metadata")
    
    @field_serializer("id", "job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)
    
    @field_serializer("started_at", "completed_at")
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        return value.isoformat() if value else None


class JobCost(BaseModel):
    """Job cost model for tracking individual API costs."""
    
    id: UUID
    job_id: UUID
    stage_name: str
    api_name: str = Field(description="API name: 'whisper', 'gpt-4o', 'sdxl', 'svd', etc.")
    cost: Decimal
    timestamp: datetime
    
    @field_serializer("id", "job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)
    
    @field_serializer("timestamp")
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime to ISO format string."""
        return value.isoformat()
