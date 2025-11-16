"""
Audio analysis data models.

Defines models for audio analysis results including beats, structure, lyrics, mood, and clip boundaries.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from enum import Enum


class SongStructureType(str, Enum):
    """Song structure section types."""
    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"


class EnergyLevel(str, Enum):
    """Energy level classifications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SongStructure(BaseModel):
    """Song structure section model."""
    type: SongStructureType
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., gt=0, description="End time in seconds")
    energy: EnergyLevel
    beat_intensity: Optional[str] = Field(
        None,
        description="Beat intensity for this segment: 'high', 'medium', or 'low'"
    )


class Lyric(BaseModel):
    """Lyric word model with timestamp."""
    text: str
    timestamp: float = Field(..., ge=0, description="Word start time in seconds")


class Mood(BaseModel):
    """Mood classification model."""
    primary: str = Field(..., description="Primary mood (energetic, calm, dark, bright)")
    secondary: Optional[str] = Field(None, description="Secondary mood if confidence >0.3")
    energy_level: EnergyLevel
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")


class ClipBoundary(BaseModel):
    """Clip boundary model for video segmentation."""
    start: float = Field(..., ge=0, description="Clip start time in seconds")
    end: float = Field(..., gt=0, description="Clip end time in seconds")
    duration: float = Field(..., ge=4, le=25, description="Clip duration in seconds (4-25s, flexible)")


class AudioAnalysis(BaseModel):
    """Complete audio analysis result model."""
    job_id: UUID
    bpm: float = Field(..., ge=60, le=200, description="Beats per minute")
    duration: float = Field(..., gt=0, description="Audio duration in seconds")
    beat_timestamps: List[float] = Field(..., description="Beat timestamps in seconds")
    beat_subdivisions: dict = Field(
        default_factory=lambda: {"eighth_notes": [], "sixteenth_notes": []},
        description="Beat subdivisions (eighth and sixteenth notes)"
    )
    beat_strength: List[str] = Field(
        default_factory=list,
        description="Beat strength classification ('downbeat' or 'upbeat')"
    )
    song_structure: List[SongStructure] = Field(..., min_length=1, description="Song sections")
    lyrics: List[Lyric] = Field(default_factory=list, description="Lyrics with timestamps")
    mood: Mood
    clip_boundaries: List[ClipBoundary] = Field(..., min_length=1, description="Clip boundaries (min 1, typically 3+)")
    metadata: dict = Field(default_factory=dict, description="Processing metadata")

