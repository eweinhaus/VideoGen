"""
Scene planning data models.

Defines ScenePlan, Character, Scene, Style, ClipScript, Transition, and ReferenceImages models.
"""

from decimal import Decimal
from typing import Literal, List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer, field_validator
import warnings


class FaceFeatures(BaseModel):
    """Detailed face features for consistent facial appearance."""

    shape: str = Field(description="Face shape: oval, heart-shaped, square, round")
    skin_tone: str = Field(description="Skin tone: fair, medium, olive, brown")
    nose: str = Field(description="Nose: button nose, aquiline nose, straight nose")
    mouth: str = Field(description="Mouth/lips: full lips, thin lips, wide smile")
    cheeks: str = Field(description="Cheeks: high cheekbones, rounded cheeks")
    jawline: str = Field(description="Jawline: strong, soft, angular, rounded")
    distinctive_marks: str = Field(
        default="none",
        description="Freckles, mole, scar, or 'none'"
    )


class CharacterFeatures(BaseModel):
    """Structured character features for consistent appearance."""

    hair: str = Field(description="Hair color, length, texture, and style")
    face_features: FaceFeatures = Field(description="Detailed facial features")
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
    time_of_day: str  # PHASE 2.2: Now required for time consistency

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, v: str) -> str:
        """
        Validate time_of_day field.

        PHASE 2.2: Warn if value is not in standard list for consistency.
        """
        standard_times = {
            "dawn", "morning", "midday", "afternoon",
            "dusk", "evening", "night", "midnight"
        }

        if v.lower() not in standard_times:
            warnings.warn(
                f"time_of_day '{v}' is not in standard list: {standard_times}. "
                "This may affect lighting consistency across clips.",
                UserWarning
            )

        return v


class ObjectFeatures(BaseModel):
    """Structured object features for consistent appearance."""

    object_type: str = Field(description="Type of object (guitar, car, phone, necklace, etc.)")
    color: str = Field(description="Primary color(s) with specific shades")
    material: str = Field(description="Material/texture (wood, metal, leather, glass, etc.)")
    distinctive_features: str = Field(description="Unique identifying details (brand, design, wear, etc.)")
    size: str = Field(description="Approximate size or scale description")
    condition: str = Field(description="New, worn, vintage, damaged, etc.")


class Object(BaseModel):
    """Object definition for key props that appear in multiple clips."""

    id: str = Field(description="Object ID (e.g., 'guitar_1', 'vintage_car', 'gold_necklace')")
    name: str = Field(description="Object name (e.g., 'Vintage Guitar', 'Red Sports Car')")
    features: ObjectFeatures
    importance: Literal["primary", "secondary"] = Field(
        default="secondary",
        description="Primary objects are central to story, secondary are supporting props"
    )


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
    objects: List[str] = Field(default_factory=list, description="List of object IDs appearing in this clip")
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
    objects: List[Object] = Field(default_factory=list, description="Key objects/props appearing in multiple clips")
    style: Style
    clip_scripts: List[ClipScript]
    transitions: List[Transition]

    @field_serializer("job_id")
    def serialize_uuid(self, value: UUID) -> str:
        """Serialize UUID to string."""
        return str(value)


class ReferenceImage(BaseModel):
    """Reference image for scene, character, or object."""

    scene_id: Optional[str] = Field(default=None, description="None if character/object reference")
    character_id: Optional[str] = Field(default=None, description="None if scene/object reference")
    object_id: Optional[str] = Field(default=None, description="None if scene/character reference")
    variation_index: int = Field(default=0, description="Variation index (0=base, 1+=variations)")
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
    object_references: List[ReferenceImage] = Field(default_factory=list, description="Object reference images")
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
