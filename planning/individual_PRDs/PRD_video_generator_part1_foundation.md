# Video Generator Module - Part 1: Foundation

**Version:** 1.0 | **Date:** November 2025  
**Module:** Module 7 (Video Generator) - Part 1 of 3  
**Phase:** Phase 3  
**Status:** Implementation-Ready

---

## Executive Summary

This document specifies **Part 1: Foundation** of the Video Generator module, which includes configuration, cost estimation, and image handling utilities. These components are independent and can be built/tested without Replicate API integration.

**Components:**
- `config.py` - Model versions, generation settings, cost lookup tables
- `cost_estimator.py` - Cost estimation functions
- `image_handler.py` - Image download/upload utilities

**Dependencies:** None (uses shared utilities only)  
**Next Part:** Part 2 (Generator) depends on this foundation

---

## High-Level Requirements

### Purpose
Establish foundational utilities for video generation:
1. **Configuration:** Centralized settings for models, generation parameters, and costs
2. **Cost Estimation:** Calculate estimated costs per clip and total job cost
3. **Image Handling:** Download images from Supabase and upload to Replicate

### Success Criteria
- ✅ Configuration loaded correctly for production/development
- ✅ Cost estimates accurate within ±20% of actual costs
- ✅ Images downloaded and uploaded successfully
- ✅ All components testable in isolation

---

## Architecture & Design Decisions

### 1. Configuration Strategy

**Centralized Configuration:**
- All settings in `config.py` (no scattered env vars)
- Environment-aware (production vs development)
- Sensible defaults with optional overrides

**Model Versions:**
- Pin specific SVD version for stability
- Use latest for fallback model (rarely used)
- Configurable via env vars for easy updates

**Generation Settings:**
- Production: High quality (1024x576, 30 FPS, 25 steps)
- Development: Lower quality (768x432, 24 FPS, 20 steps) for speed/cost

**Cost Lookup:**
- Simple formula: `base_cost + (duration * per_second_rate)`
- Two-tier (production vs development)
- Easy to maintain and update

### 2. Cost Estimation

**Simple Formula:**
```python
cost_per_clip = base_cost + (duration_seconds * per_second_rate)
```

**Rationale:**
- Accurate enough for budget enforcement (±20% tolerance acceptable)
- Easy to maintain (no complex lookup tables)
- Can be adjusted as actual costs are measured

### 3. Image Handling

**Optimized Approach:**
- **First attempt:** Try passing Supabase signed URL directly to Replicate (if supported)
- **Fallback:** Download from Supabase Storage and pass file bytes/object to Replicate
- Replicate accepts file URLs, file objects, or file paths directly in input
- No separate upload API needed (Replicate handles files in input)

**Error Handling:**
- Retry download on failure (3 attempts with exponential backoff)
- Return `None` if all attempts fail (proceed with text-only)

---

## Directory Structure

```text
backend/modules/video_generator/
├── __init__.py                 # Module exports (Part 3)
├── config.py                   # ← Part 1
├── cost_estimator.py           # ← Part 1
├── image_handler.py            # ← Part 1
├── generator.py                # Part 2
├── process.py                  # Part 3
└── tests/
    ├── test_config.py          # ← Part 1 tests
    ├── test_cost_estimator.py  # ← Part 1 tests
    └── test_image_handler.py   # ← Part 1 tests
```

---

## File Specifications

### `config.py`

**Purpose:** Centralized configuration for models, settings, and costs.

**Contents:**
```python
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
    """
    if model_name == "svd":
        return SVD_MODEL
    elif model_name == "cogvideox":
        return COGVIDEOX_MODEL
    else:
        raise ValueError(f"Unknown model: {model_name}")
```

**Testing:**
- Test environment detection
- Test settings loading
- Test model version retrieval
- Test env var overrides

---

### `cost_estimator.py`

**Purpose:** Cost estimation for video clips.

**Functions:**
```python
"""
Cost estimation for video generation.

Simple formula: base_cost + (duration * per_second_rate)
"""
from decimal import Decimal
from typing import TYPE_CHECKING
from modules.video_generator.config import COST_PER_CLIP

if TYPE_CHECKING:
    from shared.models.video import ClipPrompts

def estimate_clip_cost(duration: float, environment: str) -> Decimal:
    """
    Estimate cost for single clip.
    
    Args:
        duration: Clip duration in seconds
        environment: "production" or "development"
        
    Returns:
        Estimated cost as Decimal
        
    Raises:
        ValueError: If environment is invalid
    """
    if environment not in COST_PER_CLIP:
        raise ValueError(f"Invalid environment: {environment}")
    
    costs = COST_PER_CLIP[environment]
    return costs["base_cost"] + (costs["per_second"] * Decimal(str(duration)))

def estimate_total_cost(clip_prompts: "ClipPrompts", environment: str) -> Decimal:
    """
    Estimate total cost for all clips.
    
    Args:
        clip_prompts: ClipPrompts model with list of clip prompts
        environment: "production" or "development"
        
    Returns:
        Total estimated cost as Decimal
    """
    total = Decimal("0.00")
    for cp in clip_prompts.clip_prompts:
        total += estimate_clip_cost(cp.duration, environment)
    return total
```

**Testing:**
- Test cost calculation for single clip
- Test total cost calculation
- Test environment-specific costs
- Test edge cases (zero duration, very long duration)

---

### `image_handler.py`

**Purpose:** Download images from Supabase and upload to Replicate.

**Functions:**
```python
"""
Image handling for video generation.

Downloads images from Supabase Storage and uploads to Replicate.
"""
from typing import Optional
from uuid import UUID
from shared.storage import StorageClient
from shared.retry import retry_with_backoff
from shared.errors import RetryableError
from shared.logging import get_logger
import replicate
import re

logger = get_logger("video_generator.image_handler")

def parse_supabase_url(url: str) -> tuple[str, str]:
    """
    Parse Supabase Storage URL to extract bucket and path.
    
    Args:
        url: Supabase Storage URL (e.g., "https://project.supabase.co/storage/v1/object/public/bucket/path")
        
    Returns:
        Tuple of (bucket, path)
        
    Raises:
        ValueError: If URL format is invalid
    """
    # Supabase Storage URL format:
    # https://{project}.supabase.co/storage/v1/object/public/{bucket}/{path}
    # or
    # https://{project}.supabase.co/storage/v1/object/sign/{bucket}/{path}?token=...
    
    pattern = r"/storage/v1/object/(?:public|sign)/([^/]+)/(.+)"
    match = re.search(pattern, url)
    
    if not match:
        raise ValueError(f"Invalid Supabase Storage URL format: {url}")
    
    bucket = match.group(1)
    path = match.group(2)
    
    # Remove query parameters if present
    if "?" in path:
        path = path.split("?")[0]
    
    return bucket, path

@retry_with_backoff(max_attempts=3, base_delay=2)
async def download_and_upload_image(
    image_url: str,
    job_id: UUID
) -> Optional[str]:
    """
    Download image from Supabase and upload to Replicate.
    
    Args:
        image_url: Supabase Storage URL
        job_id: Job ID for logging
        
    Returns:
        File object, file path, or URL string for Replicate input, or None if all attempts fail
        
    Raises:
        RetryableError: If download fails (will retry)
    """
    storage = StorageClient()
    
    try:
        # Parse Supabase URL
        bucket, path = parse_supabase_url(image_url)
        
        # Download from Supabase
        logger.info(
            f"Downloading image from Supabase: {bucket}/{path}",
            extra={"job_id": str(job_id)}
        )
        image_bytes = await storage.download_file(bucket, path)
        
        # Replicate accepts file URLs, file objects, or file paths directly
        # Strategy: Try Supabase signed URL first, fallback to file object
        # Note: Replicate will handle the file automatically when passed in input
        
        # Option 1: Try using Supabase signed URL directly (if Replicate accepts HTTP URLs)
        # This avoids download/upload overhead
        try:
            signed_url = await storage.get_signed_url(bucket, path, expires_in=3600)
            logger.info(
                f"Using Supabase signed URL for Replicate",
                extra={"job_id": str(job_id)}
            )
            return signed_url
        except Exception as e:
            logger.debug(
                f"Signed URL approach failed, using file object: {e}",
                extra={"job_id": str(job_id)}
            )
        
        # Option 2: Pass file bytes as file object (Replicate accepts this in input)
        # Create a temporary file-like object from bytes
        import io
        file_obj = io.BytesIO(image_bytes)
        file_obj.name = "image.jpg"  # Replicate may need filename
        
        logger.info(
            f"Prepared file object for Replicate input",
            extra={"job_id": str(job_id), "size": len(image_bytes)}
        )
        
        # Return file object - will be passed directly in Replicate input
        # Note: This returns the file object, not a URL
        # The generator will pass this directly in the input dict
        return file_obj
        
    except RetryableError:
        # Re-raise retryable errors (will be retried by decorator)
        raise
    except Exception as e:
        logger.error(
            f"Failed to download/upload image: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        # Return None to proceed with text-only
        return None
```

**Testing:**
- Test URL parsing (various Supabase URL formats)
- Test image download from Supabase
- Test signed URL generation
- Test file object creation from bytes
- Test error handling (download failures, signed URL failures)
- Test retry logic
- Test that returned file object/URL works with Replicate input

---

## Error Handling

### Configuration Errors
- **Invalid environment:** Raise `ValueError` with clear message
- **Missing env vars:** Use sensible defaults, log warning

### Cost Estimation Errors
- **Invalid duration:** Raise `ValueError` if duration < 0
- **Invalid environment:** Raise `ValueError` with valid options

### Image Handling Errors
- **Invalid URL format:** Raise `ValueError` with format example
- **Download failures:** Retry 3 times, return `None` if all fail
- **Upload failures:** Return `None` (proceed with text-only)

---

## Testing Strategy

### Unit Tests

1. **`test_config.py`:**
   - Test environment detection
   - Test settings loading (production vs development)
   - Test model version retrieval
   - Test env var overrides
   - Test cost lookup table access

2. **`test_cost_estimator.py`:**
   - Test single clip cost calculation
   - Test total cost calculation
   - Test environment-specific costs
   - Test edge cases (zero duration, very long duration)
   - Test invalid environment handling

3. **`test_image_handler.py`:**
   - Test URL parsing (various formats)
   - Test image download (mocked Supabase)
   - Test image upload (mocked Replicate)
   - Test error handling
   - Test retry logic

### Integration Tests
- Test with real Supabase Storage (development environment)
- Test with real Replicate API (development, cheaper settings)
- Verify cost estimates against actual costs (within ±20%)

---

## Dependencies

### Internal Dependencies
- `shared.storage.StorageClient` - Image download
- `shared.retry.retry_with_backoff` - Retry decorator
- `shared.errors` - Exception hierarchy
- `shared.logging.get_logger` - Logging
- `shared.config.settings` - Environment detection

### External Dependencies
- `replicate>=0.20.0` - Replicate API client (for file uploads)

---

## Success Metrics

- **Configuration:** All settings load correctly for both environments
- **Cost Estimation:** Estimates within ±20% of actual costs
- **Image Handling:** 95%+ success rate for download/upload
- **Test Coverage:** 90%+ code coverage for all components

---

## Known Limitations

1. **Cost Estimation:** Estimates may vary from actual costs (monitor and adjust)
2. **Image Handling:** Replicate file input format may vary by model (test with actual SVD model)
3. **URL Parsing:** Supabase URL format may vary (test with real URLs)
4. **File Input:** Need to verify if Replicate SVD model accepts URLs, file objects, or both

---

## Next Steps

After completing Part 1:
1. ✅ All tests passing
2. ✅ Components tested in isolation
3. ✅ Ready for Part 2 (Generator) integration

**Part 2 Dependencies:**
- `config.py` - For model versions and settings
- `cost_estimator.py` - For cost calculation
- `image_handler.py` - For image preparation

---

**Document Status:** Ready for Implementation  
**Next Action:** Implement `config.py`, then `cost_estimator.py`, then `image_handler.py`, with tests for each

