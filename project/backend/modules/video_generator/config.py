"""
Video Generator configuration.

Centralized configuration for model versions, generation settings, and cost lookup.
"""
from decimal import Decimal
import os
from shared.config import settings

# Model versions (pinned for stability)
SVD_MODEL_VERSION = os.getenv("SVD_MODEL_VERSION", "3f0457f4613a")
COGVIDEOX_MODEL_VERSION = os.getenv("COGVIDEOX_MODEL_VERSION", "latest")

SVD_MODEL = f"stability-ai/stable-video-diffusion:{SVD_MODEL_VERSION}"
COGVIDEOX_MODEL = f"THUDM/cogvideox:{COGVIDEOX_MODEL_VERSION}"

# Generation settings by environment
PRODUCTION_SETTINGS = {
    "resolution": "1024x576",      # 16:9 aspect ratio
    "fps": 30,                      # 30 FPS
    "motion_bucket_id": 127,        # Medium motion
    "steps": 25,                    # Quality steps
    "max_duration": 8.0,            # Up to 8 seconds
}

DEVELOPMENT_SETTINGS = {
    "resolution": "768x432",        # Lower resolution (faster, cheaper)
    "fps": 24,                      # 24 FPS (standard)
    "motion_bucket_id": 100,        # Less motion (faster)
    "steps": 20,                    # Fewer steps (faster)
    "max_duration": 4.0,            # Shorter clips (faster, cheaper)
}

# Cost lookup table
COST_PER_CLIP = {
    "production": {
        "base_cost": Decimal("0.10"),      # Base cost per clip
        "per_second": Decimal("0.033"),    # ~$0.20 per 6s clip
    },
    "development": {
        "base_cost": Decimal("0.005"),     # Base cost per clip
        "per_second": Decimal("0.002"),    # ~$0.01 per 6s clip
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


def get_model_version(model_name: str = "svd") -> str:
    """
    Get model version string.
    
    Args:
        model_name: "svd" or "cogvideox"
        
    Returns:
        Full model version string (e.g., "stability-ai/stable-video-diffusion:3f0457f4613a")
        
    Raises:
        ValueError: If model_name is invalid
    """
    if model_name == "svd":
        return SVD_MODEL
    elif model_name == "cogvideox":
        return COGVIDEOX_MODEL
    else:
        raise ValueError(f"Unknown model: {model_name}")

