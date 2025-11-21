"""
Validation utilities for character image analysis inputs.
"""

import re
from typing import Tuple


def validate_image_url(url: str) -> bool:
    """Basic URL validation for HTTP/HTTPS and common image extensions."""
    if not url or not isinstance(url, str):
        return False
    if not url.startswith(("http://", "https://")):
        return False
    # Heuristic: allow signed URLs; only check for a plausible extension anywhere
    return bool(re.search(r"\.(png|jpg|jpeg|webp)(\?|$)", url, re.IGNORECASE))


def validate_image_size_bytes(size_bytes: int) -> bool:
    """Validate image payload size (100KB–10MB)."""
    if size_bytes is None:
        return False
    return 100 * 1024 <= int(size_bytes) <= 10 * 1024 * 1024


def validate_image_dimensions(width: int, height: int) -> bool:
    """Validate minimum dimension (shorter side ≥ 256px)."""
    if not width or not height:
        return False
    shorter = min(width, height)
    return shorter >= 256


def select_primary_subject_confidence(
    face_areas: list[Tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> Tuple[int, float]:
    """
    Select subject by largest face area weighted by center proximity.
    
    Returns:
        (selected_index, confidence_score)
    """
    if not face_areas:
        return -1, 0.0
    cx, cy = image_width / 2.0, image_height / 2.0
    best_idx = 0
    best_score = -1.0
    for idx, (x, y, w, h) in enumerate(face_areas):
        area = float(max(1, w) * max(1, h))
        fx, fy = x + w / 2.0, y + h / 2.0
        dist = max(1.0, ((fx - cx) ** 2 + (fy - cy) ** 2) ** 0.5)
        score = area / dist  # larger, more centered → higher
        if score > best_score:
            best_score = score
            best_idx = idx
    # Normalize a rough confidence (heuristic)
    confidence = 0.5 if best_score <= 0 else min(0.95, 0.4 + 0.6)
    return best_idx, confidence


