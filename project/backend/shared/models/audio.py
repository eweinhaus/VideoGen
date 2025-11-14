"""
Audio analysis data models.

Defines AudioAnalysis and related models for audio processing results.
"""

from decimal import Decimal
from typing import Literal, List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


class SongStructure(BaseModel):
    """Song structure segment (intro, verse, chorus, etc.)."""
    
    type: Literal["intro", "verse", "chorus", "bridge", "outro"]
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    energy: Literal["low", "medium", "high"]


class Lyric(BaseModel):
    """Lyric with timestamp."""
    
    text: str
    timestamp: float = Field(description="Timestamp in seconds")


class Mood(BaseModel):
    """Mood classification for the audio."""
    
    primary: str = Field(description="Primary mood: 'energetic', 'calm', 'dark', 'bright', etc.")
    secondary: Optional[str] = None
    energy_level: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


class ClipBoundary(BaseModel):
    """Clip boundary definition."""
    
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    duration: float = Field(description="Duration in seconds")


class AudioAnalysis(BaseModel):
    """Complete audio analysis result."""
    
    job_id: UUID
    bpm: float = Field(description="Beats per minute")
    duration: float = Field(description="Total duration in seconds")
    beat_timestamps: List[float] = Field(description="List of beat timestamps in seconds")
    song_structure: List[SongStructure]
    lyrics: List[Lyric]
    mood: Mood
    clip_boundaries: List[ClipBoundary]
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processing metadata: processing_time, cache_hit, confidence, etc."
    )
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
