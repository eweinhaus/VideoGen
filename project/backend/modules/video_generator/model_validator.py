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

# PHASE 3: Module-level cache for version hashes
# Cache results for 1 hour to avoid excessive API calls
_version_hash_cache: Dict[str, Tuple[str, float]] = {}  # {model_string: (hash, timestamp)}
CACHE_TTL = 3600  # 1 hour in seconds


async def get_latest_version_hash(replicate_string: str) -> Optional[str]:
    """
    Dynamically retrieve the latest version hash for a model from Replicate API.

    PHASE 3: Caches results for 1 hour to avoid excessive API calls.

    Args:
        replicate_string: Model string (e.g., "kwaivgi/kling-v2.1", "minimax/hailuo-2.3")

    Returns:
        Latest version hash string, or None if not found/error
    """
    if not client:
        logger.warning("Replicate client not available for version retrieval")
        return None

    # PHASE 3: Check cache first
    if replicate_string in _version_hash_cache:
        cached_hash, cached_time = _version_hash_cache[replicate_string]
        if time.time() - cached_time < CACHE_TTL:
            logger.debug(
                f"Using cached version hash for {replicate_string}: {cached_hash}",
                extra={"model": replicate_string, "cached_hash": cached_hash}
            )
            return cached_hash

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

            # PHASE 3: Cache the result
            _version_hash_cache[replicate_string] = (version_hash, time.time())

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
        
        return True, None
        
    except Exception as e:
        logger.error(
            f"Error validating model {model_key}: {str(e)}",
            extra={"model_key": model_key, "error": str(e)}
        )
        return False, f"Validation error: {str(e)}"


