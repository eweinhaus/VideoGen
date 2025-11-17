"""
Scene planning data models.

Defines ScenePlan, Character, Scene, Style, ClipScript, Transition, and ReferenceImages models.
"""

from decimal import Decimal
from typing import Literal, List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


class CharacterFeatures(BaseModel):
    """Structured character features for consistent appearance."""

    hair: str = Field(description="Hair color, length, texture, and style")
    face: str = Field(description="Skin tone, face shape, distinctive features, facial hair")
    eyes: str = Field(description="Eye color and eyebrow description")
    clothing: str = Field(description="Specific clothing items with colors and details")
    accessories: str = Field(description="Accessories like glasses, jewelry, hats, or 'None'")
    build: str = Field(description="Body type, height, and frame description")
    age: str = Field(description="Apparent age (e.g., 'appears mid-20s')")


class Character(BaseModel):
    """Character definition."""

    id: str
    role: str = Field(description="Character role: 'main character', 'love interest', 'background', etc.")

    # Structured features (RECOMMENDED)
    features: Optional[CharacterFeatures] = Field(
        default=None,
        description="Structured character features for consistent appearance"
    )

    # Name extracted from description or ID
    name: Optional[str] = Field(
        default=None,
        description="Character name (e.g., 'John', 'Sarah', 'Bartender')"
    )

    # Deprecated: Pre-formatted text description (kept for backward compatibility)
    description: Optional[str] = Field(
        default=None,
        description="DEPRECATED: Use 'features' instead. Pre-formatted character description."
    )


class Scene(BaseModel):
    """Scene definition."""
    
    id: str
    description: str
    time_of_day: Optional[str] = None


class Style(BaseModel):
    """Visual style definition."""
    
    color_palette: List[str] = Field(description="List of hex color codes")
    visual_style: str
    mood: str
    lighting: str
    cinematography: str


class ClipScript(BaseModel):
    """Clip script with visual description and metadata."""
    
    clip_index: int
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    visual_description: str
    motion: str
    camera_angle: str
    characters: List[str] = Field(description="List of character IDs")
    scenes: List[str] = Field(description="List of scene IDs")
    lyrics_context: Optional[str] = None
    beat_intensity: Literal["low", "medium", "high"]


class Transition(BaseModel):
    """Transition definition between clips."""
    
    from_clip: int
    to_clip: int
    type: Literal["cut", "crossfade", "fade"]
    duration: float = Field(description="Transition duration in seconds")
    rationale: str


class ScenePlan(BaseModel):
    """Complete scene plan for video generation."""
    
    job_id: UUID
    video_summary: str
    characters: List[Character]
    scenes: List[Scene]
    style: Style
    clip_scripts: List[ClipScript]
    transitions: List[Transition]
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)


class ReferenceImage(BaseModel):
    """Reference image for scene or character."""
    
    scene_id: Optional[str] = Field(default=None, description="None if character reference")
    character_id: Optional[str] = Field(default=None, description="None if scene reference")
    image_url: str
    prompt_used: str
    generation_time: float = Field(description="Generation time in seconds")
    cost: Decimal
    
    @field_serializer("cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)


class ReferenceImages(BaseModel):
    """Collection of reference images for a job."""
    
    job_id: UUID
    scene_references: List[ReferenceImage]
    character_references: List[ReferenceImage]
    total_references: int
    total_generation_time: float = Field(description="Total generation time in seconds")
    total_cost: Decimal
    status: Literal["success", "partial", "failed"]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)
    
    @field_serializer("total_cost")
    def serialize_decimal(self, value: Decimal) -> str:
        """Serialize Decimal to string."""
        return str(value)
