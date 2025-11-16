"""
Video Generator configuration.

Centralized configuration for model versions, generation settings, and cost lookup.
"""
from decimal import Decimal
import os
from shared.config import settings

# Model versions (pinned for stability)
# Using kwaivgi/kling-v2.1 - better prompt adherence, handles character references better
# Kling has better ability to follow prompts and ignore backgrounds from character reference images
# Latest version hash retrieved from Replicate API (Nov 2025): daad218feb714b03e2a1ac445986aebb9d05243cd00da2af17be2e4049f48f69
KLING_MODEL_VERSION = os.getenv("KLING_MODEL_VERSION", "daad218feb714b03e2a1ac445986aebb9d05243cd00da2af17be2e4049f48f69")
SVD_MODEL_VERSION = os.getenv("SVD_MODEL_VERSION", "155d6d446da5e7cd4a2ef72725461ba8687bdf63a2a1fb7bb574f25af24dc7b5")
COGVIDEOX_MODEL_VERSION = os.getenv("COGVIDEOX_MODEL_VERSION", "latest")

KLING_MODEL = f"kwaivgi/kling-v2.1:{KLING_MODEL_VERSION}"
SVD_MODEL = f"bytedance/seedance-1-pro-fast:{SVD_MODEL_VERSION}"
COGVIDEOX_MODEL = f"THUDM/cogvideox:{COGVIDEOX_MODEL_VERSION}"

# Generation settings by environment
# Note: Kling v2.1 uses resolution as "720p" or "1080p", duration as 5 or 10 seconds
PRODUCTION_SETTINGS = {
    "resolution": "1080p",          # 1080p for production quality
    "fps": 24,                      # 24 FPS (Kling standard)
    "max_duration": 10.0,           # Up to 10 seconds (Kling supports 5 or 10s)
}

DEVELOPMENT_SETTINGS = {
    "resolution": "720p",            # 720p for development (faster, cheaper)
    "fps": 24,                      # 24 FPS (standard)
    "max_duration": 5.0,            # 5 seconds (faster, cheaper)
}

# Cost lookup table for Kling v2.1
# Pricing: ~$0.30-0.50 per clip (higher than seedance but better prompt adherence)
# Note: Kling has better ability to follow prompts and ignore backgrounds
COST_PER_CLIP = {
    "production": {
        "base_cost": Decimal("0.30"),      # Base cost per clip (1080p)
        "per_second": Decimal("0.05"),      # Additional per-second cost (~$0.50 per 5s clip, ~$0.80 per 10s clip)
    },
    "development": {
        "base_cost": Decimal("0.20"),       # Base cost per clip (720p)
        "per_second": Decimal("0.03"),      # Additional per-second cost (~$0.35 per 5s clip)
    }
}


def get_generation_settings(environment: str = None) -> dict:
    """
    Get generation settings for environment.
    
    Args:
        environment: "production", "staging", or "development" (defaults to settings.environment)
        
    Returns:
        Dictionary of generation settings
    """
    if environment is None:
        environment = settings.environment
    
    if environment in ["production", "staging"]:
        return PRODUCTION_SETTINGS.copy()
    return DEVELOPMENT_SETTINGS.copy()


def get_model_version(model_name: str = "kling") -> str:
    """
    Get model version string.
    
    Args:
        model_name: "kling", "svd", or "cogvideox"
        
    Returns:
        Full model version string (e.g., "kwaivgi/kling-v2.1:latest")
        
    Raises:
        ValueError: If model_name is invalid
    """
    if model_name == "kling":
        return KLING_MODEL
    elif model_name == "svd":
        return SVD_MODEL
    elif model_name == "cogvideox":
        return COGVIDEOX_MODEL
    else:
        raise ValueError(f"Unknown model: {model_name}")

