"""
Pydantic models for character analysis requests and responses.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, conlist, confloat


AgeRange = Literal[
    "child", "teen", "early_20s", "mid_20s", "late_20s", "30s", "40s", "50s", "60plus"
]
GenderPresentation = Literal["masculine", "feminine", "androgynous", "unspecified"]
HairColor = Literal[
    "black",
    "dark_brown",
    "brown",
    "light_brown",
    "blonde",
    "red",
    "gray",
    "white",
    "unknown",
]
HairStyle = Literal[
    "buzzed",
    "short_straight",
    "short_wavy",
    "medium_curly",
    "long_straight",
    "long_wavy",
    "bald",
    "shaved",
    "ponytail",
    "afro",
    "locs",
]
EyeColor = Literal["brown", "dark_brown", "hazel", "green", "blue", "gray", "amber", "unknown"]
SkinTone = Literal[
    "very_fair", "fair", "medium", "tan", "brown", "dark_brown", "deep"
]
Build = Literal["slim", "average", "athletic", "muscular", "heavyset", "unspecified"]
HeightBucket = Literal["short", "average", "tall", "unspecified"]
StyleHint = Literal["photo_realistic", "anime", "cartoon", "3d", "illustration", "unknown"]
ConfidenceLabel = Literal["low", "medium", "high"]


class CharacterAnalysis(BaseModel):
    """Normalized character analysis result."""

    age_range: AgeRange
    gender_presentation: GenderPresentation
    hair_color: HairColor
    hair_style: HairStyle
    eye_color: EyeColor
    build: Build
    height_bucket: HeightBucket
    skin_tone: SkinTone
    style: StyleHint
    distinctive_features: List[str] = Field(default_factory=list)
    clothing: Optional[List[str]] = None
    confidence: confloat(ge=0.0, le=1.0) = 0.0  # type: ignore[valid-type]
    confidence_binned: ConfidenceLabel = "low"
    confidence_per_attribute: Dict[str, float] = Field(default_factory=dict)
    analysis_version: str = "v1"


class CharacterAnalysisRequest(BaseModel):
    """Request payload to initiate image analysis."""

    image_url: str
    analysis_version: str = "v1"


class CharacterAnalysisResponse(BaseModel):
    """Response payload when analysis is ready."""

    image_url: str
    analysis: CharacterAnalysis
    warnings: List[str] = Field(default_factory=list)
    used_cache: bool = False


