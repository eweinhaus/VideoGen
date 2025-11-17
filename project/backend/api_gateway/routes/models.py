"""
Model-related endpoints.

Provides metadata about video generation models.
"""

from fastapi import APIRouter, Path, HTTPException, status
from typing import Dict, Any
from shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Hardcoded aspect ratios to avoid import issues
# This matches the config in modules/video_generator/config.py
MODEL_ASPECT_RATIOS: Dict[str, list] = {
    "kling_v21": ["16:9"],
    "kling_v25_turbo": ["16:9", "9:16", "1:1", "4:3", "3:4"],
    "hailuo_23": ["16:9", "9:16", "1:1"],
    "wan_25_i2v": ["16:9", "1:1", "9:16"],
    "veo_31": ["16:9", "9:16"],  # Veo3 only supports these two aspect ratios
}


@router.get("/models/{model_key}/aspect-ratios")
async def get_model_aspect_ratios_endpoint(
    model_key: str = Path(..., description="Model key (e.g., kling_v21)")
):
    """
    Get supported aspect ratios for a video generation model.
    
    This is a public endpoint (no authentication required) for fetching
    model metadata.
    
    Args:
        model_key: Model identifier (kling_v21, kling_v25_turbo, etc.)
    
    Returns:
        JSON with model_key, aspect_ratios list, and default aspect ratio
    
    Raises:
        404: If model_key not found
    """
    logger.debug(f"Fetching aspect ratios for model: {model_key}")
    
    # Get from hardcoded dict (fast, no import needed)
    if model_key not in MODEL_ASPECT_RATIOS:
        logger.warning(f"Model '{model_key}' not found in aspect ratios")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_key}' not found"
        )
    
    aspect_ratios = MODEL_ASPECT_RATIOS[model_key]
    
    result = {
        "model_key": model_key,
        "aspect_ratios": aspect_ratios,
        "default": "16:9"  # Most common default
    }
    
    logger.debug(f"Returning aspect ratios for {model_key}: {aspect_ratios}")
    return result

