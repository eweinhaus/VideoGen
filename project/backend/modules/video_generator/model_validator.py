"""
Model validation and version retrieval for video generation models.

Validates model configurations and dynamically retrieves latest version hashes from Replicate.
"""
import asyncio
import time
from typing import Optional, Dict, Any, Tuple
from shared.config import settings
from shared.logging import get_logger
import replicate
from replicate.exceptions import ModelError

logger = get_logger("video_generator.model_validator")

# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client for validation: {str(e)}")
    client = None

# Model validation cache (TTL: 5 minutes)
_validation_cache: Dict[str, Tuple[bool, Optional[str], float]] = {}
_cache_ttl = 300  # 5 minutes

# Version hash cache (TTL: 1 hour) - for get_latest_version_hash()
_version_hash_cache: Dict[str, Tuple[str, float]] = {}  # {model_string: (hash, timestamp)}
VERSION_CACHE_TTL = 3600  # 1 hour in seconds


async def get_latest_version_hash(replicate_string: str) -> Optional[str]:
    """
    Dynamically retrieve the latest version hash for a model from Replicate API.
    
    Args:
        replicate_string: Model string (e.g., "kwaivgi/kling-v2.1", "minimax/hailuo-2.3")
        
    Returns:
        Latest version hash string, or None if not found/error
    """
    if not client:
        logger.warning("Replicate client not available for version retrieval")
        return None
    
    try:
        # Parse owner/model from replicate_string
        parts = replicate_string.split("/")
        if len(parts) != 2:
            logger.error(f"Invalid replicate_string format: {replicate_string}")
            return None
        
        owner, model_name = parts
        
        # Get model from Replicate
        model = client.models.get(owner=owner, name=model_name)
        
        # Get latest version
        if model and model.latest_version:
            version_hash = model.latest_version.id
            logger.info(
                f"Retrieved latest version hash for {replicate_string}: {version_hash}",
                extra={"model": replicate_string, "version_hash": version_hash}
            )
            return version_hash
        else:
            logger.warning(f"No latest version found for {replicate_string}")
            return None
            
    except ModelError as e:
        logger.error(
            f"Model not found or permission denied for {replicate_string}: {str(e)}",
            extra={"model": replicate_string, "error": str(e)}
        )
        return None
    except Exception as e:
        logger.error(
            f"Failed to retrieve latest version for {replicate_string}: {str(e)}",
            extra={"model": replicate_string, "error": str(e)}
        )
        return None


async def validate_model_config(model_key: str, model_config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate that a model configuration is working.
    
    Checks:
    1. Model exists on Replicate
    2. Version hash is valid (if pinned) or can retrieve latest (if "latest")
    3. Can access the model (permission check)
    
    Uses caching to avoid repeated API calls (5 minute TTL).
    
    Args:
        model_key: Model key (e.g., "kling_v21", "hailuo_23")
        model_config: Model configuration dict
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if model is valid and accessible
        - error_message: Error message if invalid, None if valid
    """
    if not client:
        return False, "Replicate client not initialized"
    
    # Check cache first
    cache_key = f"{model_key}:{model_config.get('replicate_string')}:{model_config.get('version')}"
    current_time = time.time()
    
    if cache_key in _validation_cache:
        is_valid, error_msg, cached_time = _validation_cache[cache_key]
        if current_time - cached_time < _cache_ttl:
            logger.debug(
                f"Using cached validation result for {model_key}",
                extra={"model_key": model_key, "cached": True}
            )
            return is_valid, error_msg
        else:
            # Cache expired, remove it
            del _validation_cache[cache_key]
    
    replicate_string = model_config.get("replicate_string")
    version = model_config.get("version")
    
    if not replicate_string:
        return False, f"Missing replicate_string in model config for {model_key}"
    
    try:
        # Parse owner/model
        parts = replicate_string.split("/")
        if len(parts) != 2:
            return False, f"Invalid replicate_string format: {replicate_string}"
        
        owner, model_name = parts
        
        # Check if model exists
        try:
            model = client.models.get(owner=owner, name=model_name)
            if not model:
                return False, f"Model {replicate_string} not found on Replicate"
        except ModelError as e:
            return False, f"Model {replicate_string} not accessible: {str(e)}"
        
        # If version is "latest", try to retrieve it
        if version == "latest":
            latest_hash = await get_latest_version_hash(replicate_string)
            if not latest_hash:
                return False, f"Could not retrieve latest version hash for {replicate_string}"
            logger.info(
                f"Model {model_key} validated: using latest version {latest_hash}",
                extra={"model_key": model_key, "version_hash": latest_hash}
            )
        else:
            # For pinned versions, try to verify the version exists
            try:
                # Try to get the version
                version_obj = client.versions.get(version)
                if not version_obj:
                    return False, f"Version hash {version} not found for {replicate_string}"
                logger.info(
                    f"Model {model_key} validated: using pinned version {version}",
                    extra={"model_key": model_key, "version_hash": version}
                )
            except Exception as e:
                return False, f"Version hash {version} invalid for {replicate_string}: {str(e)}"
        
        result = (True, None)
        # Cache successful validation
        _validation_cache[cache_key] = (True, None, current_time)
        return result
        
    except Exception as e:
        logger.error(
            f"Error validating model {model_key}: {str(e)}",
            extra={"model_key": model_key, "error": str(e)}
        )
        error_msg = f"Validation error: {str(e)}"
        # Cache failed validation (shorter TTL for failures - 1 minute)
        _validation_cache[cache_key] = (False, error_msg, current_time)
        return False, error_msg


