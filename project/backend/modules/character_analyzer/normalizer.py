"""
Attribute normalization for character analysis.

Maps free-form/vision outputs to strict enumerations and computes confidences.
"""

from typing import Dict, Tuple

from .models import (
    AgeRange,
    GenderPresentation,
    HairColor,
    HairStyle,
    EyeColor,
    SkinTone,
    Build,
    HeightBucket,
    StyleHint,
    ConfidenceLabel,
)


def _bin_confidence(value: float) -> ConfidenceLabel:
    """Map numeric confidence into binned label."""
    if value >= 0.75:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def normalize_age_range(raw: str) -> Tuple[AgeRange, float]:
    v = (raw or "").strip().lower()
    mapping = {
        "child": "child",
        "kid": "child",
        "teen": "teen",
        "early 20s": "early_20s",
        "mid 20s": "mid_20s",
        "late 20s": "late_20s",
        "30s": "30s",
        "40s": "40s",
        "50s": "50s",
        "60s": "60plus",
        "60+": "60plus",
        "elderly": "60plus",
    }
    norm = mapping.get(v, "mid_20s")  # default reasonable prior
    return norm, 0.6


def normalize_gender_presentation(raw: str) -> Tuple[GenderPresentation, float]:
    v = (raw or "").strip().lower()
    if v in {"masculine", "male", "man"}:
        return "masculine", 0.7
    if v in {"feminine", "female", "woman"}:
        return "feminine", 0.7
    if v in {"androgynous", "nonbinary", "non-binary"}:
        return "androgynous", 0.6
    return "unspecified", 0.4


def normalize_hair_color(raw: str) -> Tuple[HairColor, float]:
    v = (raw or "").strip().lower()
    mapping = {
        "black": "black",
        "dark brown": "dark_brown",
        "brown": "brown",
        "light brown": "light_brown",
        "blonde": "blonde",
        "red": "red",
        "gray": "gray",
        "white": "white",
    }
    norm = mapping.get(v, "unknown")
    return norm, 0.55 if norm != "unknown" else 0.3


def normalize_hair_style(raw: str) -> Tuple[HairStyle, float]:
    v = (raw or "").strip().lower()
    mapping = {
        "buzzed": "buzzed",
        "short straight": "short_straight",
        "short wavy": "short_wavy",
        "medium curly": "medium_curly",
        "long straight": "long_straight",
        "long wavy": "long_wavy",
        "bald": "bald",
        "shaved": "shaved",
        "ponytail": "ponytail",
        "afro": "afro",
        "locs": "locs",
    }
    norm = mapping.get(v, "short_wavy")
    return norm, 0.55


def normalize_eye_color(raw: str) -> Tuple[EyeColor, float]:
    v = (raw or "").strip().lower()
    mapping = {
        "brown": "brown",
        "dark brown": "dark_brown",
        "hazel": "hazel",
        "green": "green",
        "blue": "blue",
        "gray": "gray",
        "amber": "amber",
    }
    norm = mapping.get(v, "unknown")
    return norm, 0.55 if norm != "unknown" else 0.35


def normalize_skin_tone(raw: str) -> Tuple[SkinTone, float]:
    v = (raw or "").strip().lower()
    mapping = {
        "very fair": "very_fair",
        "fair": "fair",
        "medium": "medium",
        "tan": "tan",
        "brown": "brown",
        "dark brown": "dark_brown",
        "deep": "deep",
    }
    norm = mapping.get(v, "medium")
    return norm, 0.55


def normalize_build(raw: str) -> Tuple[Build, float]:
    v = (raw or "").strip().lower()
    if "slim" in v:
        return "slim", 0.55
    if "athletic" in v:
        return "athletic", 0.55
    if "muscular" in v:
        return "muscular", 0.55
    if "heavy" in v or "plus" in v:
        return "heavyset", 0.55
    if "average" in v or not v:
        return "average", 0.5
    return "unspecified", 0.35


def normalize_height_bucket(raw: str) -> Tuple[HeightBucket, float]:
    v = (raw or "").strip().lower()
    if "tall" in v:
        return "tall", 0.5
    if "short" in v:
        return "short", 0.5
    return "average", 0.45


def normalize_style(raw: str) -> Tuple[StyleHint, float]:
    v = (raw or "").strip().lower()
    if any(k in v for k in ("photo", "real", "photoreal")):
        return "photo_realistic", 0.6
    if "anime" in v:
        return "anime", 0.6
    if "cartoon" in v:
        return "cartoon", 0.6
    if "3d" in v:
        return "3d", 0.55
    if "illustration" in v:
        return "illustration", 0.55
    return "unknown", 0.35


def bin_overall_confidence(attr_conf: Dict[str, float]) -> ConfidenceLabel:
    """Compute overall confidence from per-attribute confidences."""
    if not attr_conf:
        return "low"
    avg = sum(attr_conf.values()) / max(1, len(attr_conf))
    return _bin_confidence(avg)


