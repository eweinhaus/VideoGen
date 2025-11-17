"""
Video Generator configuration.

Centralized configuration for model versions, generation settings, and cost lookup.
Supports multiple video generation models with configurable selection.
"""
from decimal import Decimal
import os
from typing import Dict, Any, Literal
from shared.config import settings
from shared.logging import get_logger

logger = get_logger("video_generator.config")

# Model versions (pinned for stability)
# Using kwaivgi/kling-v2.1 - better prompt adherence, handles character references better
# Kling has better ability to follow prompts and ignore backgrounds from character reference images
# Note: Old pinned version hash was invalid. Using "latest" to dynamically retrieve current version.
KLING_MODEL_VERSION = os.getenv("KLING_MODEL_VERSION", "latest")
SVD_MODEL_VERSION = os.getenv("SVD_MODEL_VERSION", "155d6d446da5e7cd4a2ef72725461ba8687bdf63a2a1fb7bb574f25af24dc7b5")
COGVIDEOX_MODEL_VERSION = os.getenv("COGVIDEOX_MODEL_VERSION", "latest")

# Duration buffer configuration
# Buffer multiplier for continuous models (default: 1.25 = 25% buffer)
# Only applies to models with continuous duration support
# Discrete models (Kling, etc.) use maximum buffer strategy instead
VIDEO_GENERATOR_DURATION_BUFFER = float(os.getenv("VIDEO_GENERATOR_DURATION_BUFFER", "1.25"))

KLING_MODEL = f"kwaivgi/kling-v2.1:{KLING_MODEL_VERSION}"
SVD_MODEL = f"bytedance/seedance-1-pro-fast:{SVD_MODEL_VERSION}"
COGVIDEOX_MODEL = f"THUDM/cogvideox:{COGVIDEOX_MODEL_VERSION}"

# Model Configuration Database
# Contains metadata for all available video generation models
# Use settings.video_model (env: VIDEO_MODEL) to select active model
MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "kling_v21": {
        "replicate_string": "kwaivgi/kling-v2.1",
        "version": "latest",  # Dynamically retrieve latest version
        "full_model": "kwaivgi/kling-v2.1:latest",
        "type": "image-to-video",
        "supports_lip_sync": False,
        "supports_motion_control": False,
        "supports_audio": False,
        "max_duration": 10,
        "duration_support": "discrete",  # Only supports 5s or 10s
        "supported_durations": [5, 10],
        "resolutions": ["720p", "1080p"],
        "fps": 24,
        "estimated_cost_5s": Decimal("0.55"),
        "estimated_cost_10s": Decimal("0.80"),
        "generation_time_avg_seconds": 90,
        "anatomy_score": 6,  # Out of 10 - prone to anatomy errors
        "prompt_adherence_score": 9,  # Out of 10 - excellent prompt following
        "notes": "Current baseline model. Good prompt adherence but anatomy issues (extra limbs). Requires reference images.",
        # PHASE 3: Parameter mapping for Replicate API
        "parameter_names": {
            "prompt": "prompt",
            "image": "start_image",
            "duration": "duration",
            "resolution": "resolution",
        },
        "required_parameters": ["prompt"],
        "optional_parameters": ["start_image", "duration", "resolution"],
        # PHASE 3: Status tracking
        "status": "available",
        "last_verified": "2025-11-16",
        "verified_by": "manual",
        "display_name": "Kling v2.1",
        "description": "Fast and reliable video generation with good prompt adherence",
        "recommended_for": ["general", "characters", "scenes"],
        "not_recommended_for": ["complex_anatomy", "dance"],
    },
    "kling_v25_turbo": {
        "replicate_string": "kwaivgi/kling-v2.5-turbo-pro",
        "version": "latest",  # Needs verification on Replicate
        "full_model": "kwaivgi/kling-v2.5-turbo-pro:latest",
        "type": "text-and-image-to-video",
        "supports_lip_sync": False,
        "supports_motion_control": False,
        "supports_audio": False,
        "max_duration": 10,
        "duration_support": "discrete",  # Only supports 5s or 10s
        "supported_durations": [5, 10],
        "resolutions": ["480p", "720p", "1080p"],
        "fps": 24,
        "estimated_cost_5s": Decimal("0.55"),
        "estimated_cost_10s": Decimal("0.80"),
        "generation_time_avg_seconds": 60,
        "anatomy_score": 8,  # Better than v2.1
        "prompt_adherence_score": 9,
        "notes": "Upgraded Kling with better anatomy. Smooth motion, cinematic depth. Direct upgrade path from v2.1.",
        "parameter_names": {
            "prompt": "prompt",
            "image": "start_image",
            "duration": "duration",
            "resolution": "resolution",
        },
        "required_parameters": ["prompt"],
        "optional_parameters": ["start_image", "duration", "resolution"],
        "status": "testing",
        "last_verified": "2025-11-16",
        "verified_by": "automated",
        "display_name": "Kling v2.5 Turbo",
        "description": "Upgraded Kling with better anatomy and faster generation",
        "recommended_for": ["general", "characters", "anatomy"],
        "not_recommended_for": [],
    },
    "hailuo_23": {
        "replicate_string": "minimax/hailuo-2.3",
        "version": "latest",
        "full_model": "minimax/hailuo-2.3:latest",
        "type": "text-to-video",
        "supports_lip_sync": False,
        "supports_motion_control": False,
        "supports_audio": False,
        "max_duration": 10,
        "duration_support": "discrete",  # Assumed discrete, needs testing
        "supported_durations": [5, 10],  # Assumed, needs verification
        "resolutions": ["variable"],  # Resolution varies
        "fps": 24,
        "estimated_cost_5s": Decimal("0.60"),
        "estimated_cost_10s": Decimal("0.90"),
        "generation_time_avg_seconds": 70,
        "anatomy_score": 9,  # Excellent for human anatomy
        "prompt_adherence_score": 8,
        "notes": "Best for realistic human motion and anatomy. Optimized for dancing/choreography. Physics-realistic.",
        "parameter_names": {
            "prompt": "prompt",
            "duration": "duration",
        },
        "required_parameters": ["prompt"],
        "optional_parameters": ["duration"],
        "status": "testing",
        "last_verified": "2025-11-16",
        "verified_by": "automated",
        "display_name": "Hailuo 2.3",
        "description": "Best for realistic human motion and anatomy, optimized for dance",
        "recommended_for": ["dance", "choreography", "human_anatomy"],
        "not_recommended_for": [],
    },
    "wan_25_i2v": {
        "replicate_string": "wan-video/wan-2.5-i2v",
        "version": "latest",
        "full_model": "wan-video/wan-2.5-i2v:latest",
        "type": "image-to-video",
        "supports_lip_sync": False,
        "supports_motion_control": False,
        "supports_audio": True,  # Background audio
        "max_duration": 10,
        "duration_support": "discrete",  # Assumed discrete, needs testing
        "supported_durations": [5, 10],  # Assumed, needs verification
        "resolutions": ["variable"],
        "fps": 24,
        "estimated_cost_5s": Decimal("0.10"),
        "estimated_cost_10s": Decimal("0.15"),
        "generation_time_avg_seconds": 30,
        "anatomy_score": 6,
        "prompt_adherence_score": 7,
        "notes": "Budget option for testing. Open-source, very cheap. Lower quality than commercial models.",
        "parameter_names": {
            "prompt": "prompt",
            "image": "image",
            "duration": "duration",
        },
        "required_parameters": ["prompt"],
        "optional_parameters": ["image", "duration"],
        "status": "testing",
        "last_verified": "2025-11-16",
        "verified_by": "automated",
        "display_name": "Wan 2.5 I2V",
        "description": "Budget-friendly option for testing, open-source model",
        "recommended_for": ["testing", "prototyping"],
        "not_recommended_for": ["production"],
    },
    "veo_31": {
        "replicate_string": "google/veo-3.1",
        "version": "latest",
        "full_model": "google/veo-3.1:latest",
        "type": "text-and-image-to-video",
        "supports_lip_sync": False,
        "supports_audio": True,  # Context-aware audio
        "supports_motion_control": False,
        "max_duration": 10,
        "duration_support": "continuous",  # Assumed continuous, needs testing
        "supported_durations": None,  # Continuous, any value up to max_duration
        "resolutions": ["1080p"],
        "fps": 24,
        "estimated_cost_5s": Decimal("1.00"),  # Estimated, actual pricing varies
        "estimated_cost_10s": Decimal("1.50"),
        "generation_time_avg_seconds": 60,
        "anatomy_score": 10,  # Highest quality
        "prompt_adherence_score": 10,
        "notes": "Premium Google model. Highest quality, variable pricing. May be expensive.",
        "parameter_names": {
            "prompt": "prompt",
            "image": "image",
            "duration": "duration",
            "resolution": "resolution",
        },
        "required_parameters": ["prompt"],
        "optional_parameters": ["image", "duration", "resolution"],
        "status": "testing",
        "last_verified": "2025-11-16",
        "verified_by": "automated",
        "display_name": "Veo 3.1",
        "description": "Premium Google model with highest quality output",
        "recommended_for": ["premium", "high_quality"],
        "not_recommended_for": ["budget"],
    },
}


def get_selected_model() -> str:
    """
    Get the currently selected video model from settings.
    
    Returns:
        Model key (e.g., "kling_v21", "hailuo_23")
    
    Raises:
        ValueError: If VIDEO_MODEL env var is invalid
    
    Note:
        Changes to VIDEO_MODEL env var require backend/worker restart to take effect.
        Settings are loaded at startup and cached.
    """
    model_key = settings.video_model
    
    logger.info(
        f"Video model selection: VIDEO_MODEL env var = '{model_key}'",
        extra={"requested_model": model_key, "available_models": list(MODEL_CONFIGS.keys())}
    )

    if model_key not in MODEL_CONFIGS:
        logger.warning(
            f"Invalid VIDEO_MODEL '{model_key}', falling back to 'kling_v21'",
            extra={"requested_model": model_key, "available_models": list(MODEL_CONFIGS.keys())}
        )
        return "kling_v21"

    logger.info(
        f"Using video model: {model_key}",
        extra={"model": model_key}
    )
    return model_key


def get_model_config(model_key: str = None) -> Dict[str, Any]:
    """
    Get configuration for a specific model or the currently selected model.

    Args:
        model_key: Model key (e.g., "kling_v21"). If None, uses settings.video_model

    Returns:
        Model configuration dict

    Raises:
        ValueError: If model_key is invalid
    """
    if model_key is None:
        model_key = get_selected_model()

    if model_key not in MODEL_CONFIGS:
        raise ValueError(
            f"Unknown model '{model_key}'. Available models: {list(MODEL_CONFIGS.keys())}"
        )

    return MODEL_CONFIGS[model_key]


def get_model_replicate_string(model_key: str = None) -> str:
    """
    Get full Replicate model string for generation.

    Args:
        model_key: Model key or None for current model

    Returns:
        Full model string (e.g., "kwaivgi/kling-v2.1:version_hash")
    """
    config = get_model_config(model_key)
    return config["full_model"]


def estimate_clip_cost(duration_seconds: float, model_key: str = None) -> Decimal:
    """
    Estimate cost for a single clip based on duration and model.

    Args:
        duration_seconds: Clip duration
        model_key: Model key or None for current model

    Returns:
        Estimated cost in USD
    """
    config = get_model_config(model_key)

    # Use closest duration estimate (5s or 10s)
    if duration_seconds <= 5:
        return config["estimated_cost_5s"]
    else:
        return config["estimated_cost_10s"]

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


def get_duration_buffer_multiplier() -> float:
    """
    Get duration buffer multiplier for continuous models.
    
    Returns:
        Buffer multiplier (default: 1.25 = 25% buffer)
        
    Note:
        This multiplier only applies to models with continuous duration support.
        Discrete models (Kling, etc.) use maximum buffer strategy instead.
    """
    return VIDEO_GENERATOR_DURATION_BUFFER

