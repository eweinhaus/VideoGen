"""
Video generation data models.

Defines ClipPrompts, Clips, and VideoOutput models for video processing.
"""

from decimal import Decimal
from typing import Literal, List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


class ClipPrompt(BaseModel):
    """Optimized prompt for video clip generation."""
    
    clip_index: int
    prompt: str
    negative_prompt: str
    duration: float = Field(description="Target duration in seconds")
    scene_reference_url: Optional[str] = None
    character_reference_urls: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata: word_count, style_keywords, etc."
    )


class ClipPrompts(BaseModel):
    """Collection of clip prompts for a job."""
    
    job_id: UUID
    clip_prompts: List[ClipPrompt]
    total_clips: int
    generation_time: float = Field(description="Generation time in seconds")
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)


class Clip(BaseModel):
    """Generated video clip."""
    
    clip_index: int
    video_url: str
    actual_duration: float = Field(description="Actual duration in seconds")
    target_duration: float = Field(description="Target duration in seconds")
    original_target_duration: Optional[float] = Field(
        default=None,
        description="Original target duration before buffer (for compensation algorithm)"
    )
    duration_diff: float = Field(description="Duration difference in seconds")
    status: Literal["success", "failed"]
    cost: Decimal
    retry_count: int = Field(default=0, ge=0)
    generation_time: float = Field(description="Generation time in seconds")
    
    def __init__(self, **data):
        """Initialize Clip with default original_target_duration if not provided."""
        # Set original_target_duration default to target_duration if not provided (backward compatibility)
        if "original_target_duration" not in data or data.get("original_target_duration") is None:
            data["original_target_duration"] = data.get("target_duration")
        super().__init__(**data)
    
    @field_serializer("cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)


class Clips(BaseModel):
    """Collection of generated video clips."""
    
    job_id: UUID
    clips: List[Clip]
    total_clips: int
    successful_clips: int
    failed_clips: int
    total_cost: Decimal
    total_generation_time: float = Field(description="Total generation time in seconds")
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("total_cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)


class VideoOutput(BaseModel):
    """Final composed video output."""
    
    job_id: UUID
    video_url: str
    duration: float = Field(description="Final video duration in seconds")
    audio_duration: float = Field(description="Original audio duration in seconds")
    sync_drift: float = Field(description="Audio sync drift in seconds")
    clips_used: int
    clips_trimmed: int
    clips_looped: int = 0  # Always 0 with cascading compensation (kept for backward compatibility)
    compensation_applied: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of compensation events: [{'clip_index': 1, 'original_target': 8.0, 'extended_target': 9.5, 'compensation': 0.5}]"
    )
    total_shortfall: float = Field(default=0.0, description="Total shortfall after all clips (in seconds)")
    shortfall_percentage: float = Field(default=0.0, description="Shortfall as percentage of total intended duration")
    transitions_applied: int
    file_size_mb: float = Field(description="File size in megabytes")
    composition_time: float = Field(description="Composition time in seconds")
    cost: Decimal
    status: Literal["success", "failed"]
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)
