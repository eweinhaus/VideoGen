# Video Generator Module - Implementation PRD

**Version:** 2.0 | **Date:** November 2025  
**Module:** Module 7 (Video Generator)  
**Phase:** Phase 3  
**Status:** Split into 3 Parts

---

## ⚠️ This PRD has been split into 3 parts for better organization:

1. **[Part 1: Foundation](PRD_video_generator_part1_foundation.md)** - `config.py`, `cost_estimator.py`, `image_handler.py`
2. **[Part 2: Generator](PRD_video_generator_part2_generator.md)** - `generator.py` (Replicate API integration)
3. **[Part 3: Process](PRD_video_generator_part3_process.md)** - `process.py` (parallel orchestration)

**Please refer to the individual PRDs above for implementation details.**

---

## Executive Summary (Legacy - See Parts 1-3 Above)

This document specified the Video Generator module, which generates video clips in parallel using text-to-video models (Stable Video Diffusion via Replicate). The module takes `ClipPrompts` (from Module 6) and produces `Clips` (video files) that will be composed into the final music video.

**Role in Pipeline:**
- **Upstream inputs:** `ClipPrompts` (optimized prompts with reference image URLs)
- **Downstream consumer:** `Composer` (Module 8), which stitches clips together
- **Orchestrator stage:** `video_generator` at **50-85% progress** (after Prompt Generator, before Composer)

**Key Simplifications Made:**
1. **Image Handling:** Always download from Supabase (simpler, more reliable than hybrid approach)
2. **Polling:** Fixed 3-second interval (simpler than adaptive polling)
3. **Duration:** Request target duration, accept ±2s tolerance, let Composer normalize to exact
4. **Cost Estimation:** Simple formula: `base_cost + (duration * per_second_rate)` per clip
5. **Budget Enforcement:** Check before starting, abort immediately if exceeded (no "finish batch" complexity)
6. **Retry Strategy:** Clear boundaries - retry individual clips, accept ≥3 successful total

---

## High-Level Requirements

### Inputs
- `job_id: UUID` (pipeline job identifier)
- `clip_prompts: ClipPrompts` (from `shared.models.video`)

### Output
- `Clips` (from `shared.models.video`) containing:
  - `clips: List[Clip]` - At least 3 successful clips
  - `total_clips: int` - Total number of clip prompts
  - `successful_clips: int` - Number of successfully generated clips
  - `failed_clips: int` - Number of failed clips
  - `total_cost: Decimal` - Total cost for all clips
  - `total_generation_time: float` - Total wall-clock time

### Success Criteria
- ✅ **Minimum 3 clips generated successfully** (job fails if <3)
- ✅ **Parallel generation works** (5 concurrent clips by default)
- ✅ **Duration tolerance** (±2s acceptable, Composer normalizes to exact)
- ✅ **Retry logic works** (3 attempts per clip with exponential backoff)
- ✅ **Cost tracking accurate** (per-clip cost tracked in real-time)
- ✅ **Total time <180s** for 6 clips (parallel generation)
- ✅ **Budget enforcement** (abort if budget exceeded before starting)

---

## Architecture & Design Decisions

### 1. Model Selection

**Primary Model:** Stable Video Diffusion (SVD)
- **Version:** Pin specific version for stability: `stability-ai/stable-video-diffusion:3f0457f4613a`
- **Rationale:** Predictable behavior, consistent costs, easier debugging
- **Fallback Model:** `THUDM/cogvideox:latest` (use latest for fallback since rarely used)

**Configuration:**
- Store model versions in `config.py` as constants
- Make versions configurable via env vars for easy updates:
  - `SVD_MODEL_VERSION` (default: `3f0457f4613a`)
  - `COGVIDEOX_MODEL_VERSION` (default: `latest`)

### 2. Image + Text Input Strategy

**MVP Approach:** Scene reference image + text descriptions
- Use `scene_reference_url` as primary image input to model
- Include character descriptions in text prompt (not as images)
- Store `character_reference_urls` in metadata for future use (post-MVP)

**Image Handling:**
- **Always download from Supabase** (simpler, more reliable than hybrid URL approach)
- Download image bytes, upload to Replicate (Replicate accepts file uploads)
- Rationale: Avoids URL expiration issues, works consistently, simpler code path

**Future Enhancement (Post-MVP):**
- Test if models support multiple image inputs
- If not, implement image compositing (combine scene + character references)

### 3. Duration Handling Strategy

**Three-Layer Approach:**

1. **Video Generator:** Request target duration from model
   - Models may have fixed duration options (4s, 5s, 6s, 8s)
   - Map target duration to closest supported option
   - Accept ±2s tolerance from model output
   - Track both `target_duration` and `actual_duration` in `Clip` model

2. **Composer Normalization:** Exact duration matching
   - Composer receives clips with `actual_duration` and `target_duration`
   - Normalizes all clips to exact `target_duration` before stitching:
     - **Too long:** Trim from end (stay on beat boundaries)
     - **Too short:** Loop entire clip until target reached
     - **Close (±0.1s):** Speed up/slow down by ±5% using FFmpeg

**Rationale:** Models are unreliable for exact durations, but Composer can normalize precisely.

### 4. Parallel Concurrency

**Configuration:**
- **Default:** 5 concurrent clips (as per PRD)
- **Configurable:** `VIDEO_GENERATOR_CONCURRENCY` env var
- **Development:** 3 concurrent (safer, lower cost spikes)
- **Production:** 5 concurrent (optimal for speed)

**Implementation:**
- Use `asyncio.Semaphore(concurrency)` for concurrency control
- Generate all clips in parallel using `asyncio.gather()`
- Track individual clip status (success/failure)

### 5. Cost Estimation

**Simple Formula:**
```python
cost_per_clip = base_cost + (duration_seconds * per_second_rate)
```

**Cost Lookup Table:**
```python
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
```

**Estimation:**
- Estimate total cost before starting: `sum(estimate_clip_cost(cp.duration) for cp in clip_prompts)`
- Check budget before starting generation
- Track actual cost per clip as they complete

**Rationale:** Simple, accurate enough, easy to maintain.

### 6. Image Handling Implementation

**Simplified Approach:** Always download from Supabase
- Download image bytes from Supabase Storage using `shared.storage.StorageClient`
- Upload image bytes to Replicate (Replicate Python SDK handles uploads)
- No URL expiration issues, no hybrid logic complexity

**Flow:**
1. Download `scene_reference_url` from Supabase Storage
2. Upload image bytes to Replicate (get Replicate file URL)
3. Pass Replicate file URL to model API call

**Error Handling:**
- Retry download on failure (3 attempts with exponential backoff)
- If download fails after retries, proceed with text-only (no image)

### 7. Polling Strategy

**Fixed Interval:** 3 seconds
- Poll Replicate API every 3 seconds for job status
- Simple, predictable, responsive enough for UX
- Max wait: 120 seconds per clip (timeout)

**Rationale:** Adaptive polling adds complexity without significant benefit. 3s is responsive enough.

**Implementation:**
```python
while prediction.status not in ["succeeded", "failed", "canceled"]:
    await asyncio.sleep(3)  # Fixed 3-second interval
    prediction.reload()
    
    # Check timeout
    if elapsed_time > 120:
        raise TimeoutError("Clip generation timeout")
```

### 8. Retry Strategy

**Clear Boundaries:**
- **Retry individual clips** (not batches)
- **3 attempts per clip** with exponential backoff (2s, 4s, 8s)
- **Accept partial success:** Job succeeds if ≥3 clips successful total
- **Fail job if <3 successful clips** after all retries

**Retryable Errors:**
- Rate limits (429)
- Timeout errors
- Network errors
- Model unavailable (try fallback)

**Non-Retryable Errors:**
- Invalid input (bad prompt, image format)
- Budget exceeded
- Authentication errors

**Implementation:**
```python
async def generate_clip_with_retry(clip_prompt: ClipPrompt) -> Optional[Clip]:
    for attempt in range(3):
        try:
            return await generate_video_clip(clip_prompt)
        except RetryableError as e:
            if attempt < 2:
                delay = 2 * (2 ** attempt)  # 2s, 4s, 8s
                await asyncio.sleep(delay)
                continue
            else:
                logger.error(f"Clip {clip_prompt.clip_index} failed after 3 retries")
                return None
        except Exception as e:
            # Non-retryable
            logger.error(f"Clip {clip_prompt.clip_index} failed: {e}")
            return None
    return None
```

### 9. Budget Enforcement

**Simplified Approach:** Check before starting, abort immediately if exceeded
- Estimate total cost before starting generation
- Check if `current_cost + estimated_cost > budget_limit`
- If exceeded: Raise `BudgetExceededError` immediately (don't start generation)
- If within budget: Start generation, track costs as clips complete

**Rationale:** "Finish current batch" adds complexity. Better to check upfront and abort cleanly.

**Implementation:**
```python
# Before starting generation
estimated_cost = estimate_total_cost(clip_prompts, environment)
current_cost = await cost_tracker.get_total_cost(job_id)
budget_limit = get_budget_limit(environment)

if current_cost + estimated_cost > budget_limit:
    raise BudgetExceededError(
        f"Estimated cost {estimated_cost} would exceed budget {budget_limit}"
    )

# Start generation (costs tracked as clips complete)
```

### 10. Development vs Production Settings

**Environment-Aware Configuration:**

**Production Settings:**
```python
{
    "resolution": "1024x576",      # 16:9 aspect ratio
    "fps": 30,                      # 30 FPS
    "motion_bucket_id": 127,        # Medium motion
    "steps": 25,                    # Quality steps
    "max_duration": 8.0,            # Up to 8 seconds
}
```

**Development Settings:**
```python
{
    "resolution": "768x432",        # Lower resolution (faster, cheaper)
    "fps": 24,                      # 24 FPS (standard)
    "motion_bucket_id": 100,        # Less motion (faster)
    "steps": 20,                    # Fewer steps (faster)
    "max_duration": 4.0,            # Shorter clips (faster, cheaper)
}
```

**Implementation:**
- Check `ENVIRONMENT` env var
- Load appropriate settings from `config.py`
- Use cheaper settings in development to save costs during testing

---

## Directory Structure

```text
backend/modules/video_generator/
├── __init__.py                 # Module exports
├── process.py                  # Main entry point: process(job_id, clip_prompts) -> Clips
├── generator.py                # Replicate API integration: generate_video_clip()
├── image_handler.py            # Image download/upload: download_and_upload_image()
├── cost_estimator.py           # Cost estimation: estimate_clip_cost(), estimate_total_cost()
├── config.py                   # Model versions, generation settings, cost lookup
├── tests/
│   ├── __init__.py
│   ├── test_process.py          # End-to-end module tests
│   ├── test_generator.py        # Replicate API integration tests
│   ├── test_image_handler.py    # Image download/upload tests
│   ├── test_cost_estimator.py   # Cost estimation tests
│   ├── conftest.py              # Test fixtures and mocks
│   └── fixtures/
│       └── sample_clip_prompts.json
└── README.md                    # Module documentation
```

---

## File Specifications

### `__init__.py`

**Purpose:** Define module's public API.

**Exports:**
- `process` (main high-level function from `process.py`)

**Code:**
```python
from modules.video_generator.process import process

__all__ = ["process"]
```

---

### `config.py`

**Purpose:** Centralized configuration for models, settings, and costs.

**Contents:**
```python
from decimal import Decimal
import os

# Model versions (pinned for stability)
SVD_MODEL = f"stability-ai/stable-video-diffusion:{os.getenv('SVD_MODEL_VERSION', '3f0457f4613a')}"
COGVIDEOX_MODEL = f"THUDM/cogvideox:{os.getenv('COGVIDEOX_MODEL_VERSION', 'latest')}"

# Generation settings by environment
PRODUCTION_SETTINGS = {
    "resolution": "1024x576",
    "fps": 30,
    "motion_bucket_id": 127,
    "steps": 25,
    "max_duration": 8.0,
}

DEVELOPMENT_SETTINGS = {
    "resolution": "768x432",
    "fps": 24,
    "motion_bucket_id": 100,
    "steps": 20,
    "max_duration": 4.0,
}

# Cost lookup table
COST_PER_CLIP = {
    "production": {
        "base_cost": Decimal("0.10"),
        "per_second": Decimal("0.033"),
    },
    "development": {
        "base_cost": Decimal("0.005"),
        "per_second": Decimal("0.002"),
    }
}

def get_generation_settings(environment: str) -> dict:
    """Get generation settings for environment."""
    if environment in ["production", "staging"]:
        return PRODUCTION_SETTINGS.copy()
    return DEVELOPMENT_SETTINGS.copy()
```

---

### `cost_estimator.py`

**Purpose:** Cost estimation for clips.

**Functions:**
```python
def estimate_clip_cost(duration: float, environment: str) -> Decimal:
    """
    Estimate cost for single clip.
    
    Args:
        duration: Clip duration in seconds
        environment: "production" or "development"
        
    Returns:
        Estimated cost as Decimal
    """
    costs = COST_PER_CLIP[environment]
    return costs["base_cost"] + (costs["per_second"] * Decimal(str(duration)))

def estimate_total_cost(clip_prompts: ClipPrompts, environment: str) -> Decimal:
    """
    Estimate total cost for all clips.
    
    Args:
        clip_prompts: ClipPrompts model
        environment: "production" or "development"
        
    Returns:
        Total estimated cost as Decimal
    """
    total = Decimal("0.00")
    for cp in clip_prompts.clip_prompts:
        total += estimate_clip_cost(cp.duration, environment)
    return total
```

---

### `image_handler.py`

**Purpose:** Download images from Supabase and upload to Replicate.

**Functions:**
```python
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
        Replicate file URL, or None if download fails
    """
    from shared.storage import StorageClient
    import replicate
    
    storage = StorageClient()
    
    try:
        # Extract bucket and path from URL
        bucket, path = parse_supabase_url(image_url)
        
        # Download from Supabase
        image_bytes = await storage.download_file(bucket, path)
        
        # Upload to Replicate (Replicate SDK handles uploads)
        # Note: Replicate accepts file-like objects or URLs
        # We'll use a temporary file or in-memory upload
        replicate_file = replicate.files.upload(image_bytes)
        
        return replicate_file.url
        
    except Exception as e:
        logger.error(f"Failed to download/upload image: {e}", extra={"job_id": str(job_id)})
        return None  # Proceed with text-only
```

---

### `generator.py`

**Purpose:** Replicate API integration for video generation.

**Functions:**
```python
async def generate_video_clip(
    clip_prompt: ClipPrompt,
    image_url: Optional[str],
    settings: dict,
    job_id: UUID
) -> Clip:
    """
    Generate single video clip via Replicate.
    
    Args:
        clip_prompt: ClipPrompt with prompt, duration, etc.
        image_url: Replicate file URL (or None for text-only)
        settings: Generation settings (resolution, fps, etc.)
        job_id: Job ID for logging
        
    Returns:
        Clip model with video URL, duration, cost, etc.
        
    Raises:
        RetryableError: If generation fails but is retryable
        GenerationError: If generation fails permanently
    """
    import replicate
    from shared.config import settings
    from shared.cost_tracking import cost_tracker
    import time
    
    # Map target duration to model-supported duration
    model_duration = map_duration_to_model(clip_prompt.duration)
    
    # Prepare input
    input_data = {
        "prompt": clip_prompt.prompt,
        "negative_prompt": clip_prompt.negative_prompt,
        "duration": model_duration,
        **settings
    }
    
    if image_url:
        input_data["image"] = image_url
    
    # Start prediction
    prediction = replicate.predictions.create(
        version=SVD_MODEL,
        input=input_data
    )
    
    # Poll for completion (fixed 3-second interval)
    start_time = time.time()
    while prediction.status not in ["succeeded", "failed", "canceled"]:
        await asyncio.sleep(3)  # Fixed 3-second polling
        
        elapsed = time.time() - start_time
        if elapsed > 120:  # 120s timeout
            raise TimeoutError("Clip generation timeout")
        
        prediction.reload()
        
        # Publish progress update (optional, for UX)
        await publish_clip_progress(job_id, clip_prompt.clip_index, elapsed)
    
    # Handle result
    if prediction.status == "succeeded":
        # Get video URL from Replicate
        video_url = prediction.output[0]
        
        # Download and upload to Supabase Storage
        from shared.storage import StorageClient
        storage = StorageClient()
        
        # Download from Replicate
        video_bytes = await download_from_url(video_url)
        
        # Upload to Supabase
        clip_path = f"{job_id}/clip_{clip_prompt.clip_index}.mp4"
        final_url = await storage.upload_file(
            bucket="video-clips",
            path=clip_path,
            file_data=video_bytes,
            content_type="video/mp4"
        )
        
        # Calculate actual duration (may differ from target)
        actual_duration = get_video_duration(video_bytes)  # Use ffprobe or similar
        
        # Calculate cost (use actual duration)
        cost = estimate_clip_cost(actual_duration, settings["environment"])
        
        # Track cost
        await cost_tracker.track_cost(
            job_id=job_id,
            stage_name="video_generator",
            api_name="svd",
            cost=cost
        )
        
        return Clip(
            clip_index=clip_prompt.clip_index,
            video_url=final_url,
            actual_duration=actual_duration,
            target_duration=clip_prompt.duration,
            duration_diff=actual_duration - clip_prompt.duration,
            status="success",
            cost=cost,
            retry_count=0,
            generation_time=elapsed
        )
    else:
        raise GenerationError(f"Clip generation failed: {prediction.error}")

def map_duration_to_model(target_duration: float) -> float:
    """
    Map target duration to model-supported duration.
    
    Models may support: 4s, 5s, 6s, 8s
    Return closest supported duration.
    """
    supported = [4.0, 5.0, 6.0, 8.0]
    return min(supported, key=lambda x: abs(x - target_duration))
```

---

### `process.py`

**Purpose:** Main entry point for video generation.

**Function:**
```python
async def process(
    job_id: UUID,
    clip_prompts: ClipPrompts
) -> Clips:
    """
    Generate all video clips in parallel.
    
    Args:
        job_id: Job ID
        clip_prompts: ClipPrompts from Prompt Generator
        
    Returns:
        Clips model with all generated clips
        
    Raises:
        BudgetExceededError: If budget would be exceeded
        PipelineError: If <3 clips generated successfully
    """
    from shared.config import settings
    from shared.cost_tracking import cost_tracker
    from api_gateway.services.budget_helpers import get_budget_limit
    from modules.video_generator.cost_estimator import estimate_total_cost
    from modules.video_generator.generator import generate_video_clip
    from modules.video_generator.image_handler import download_and_upload_image
    from modules.video_generator.config import get_generation_settings
    import asyncio
    import time
    
    environment = settings.environment
    settings_dict = get_generation_settings(environment)
    
    # Budget check before starting
    estimated_cost = estimate_total_cost(clip_prompts, environment)
    current_cost = await cost_tracker.get_total_cost(job_id)
    budget_limit = get_budget_limit(environment)
    
    if current_cost + estimated_cost > budget_limit:
        raise BudgetExceededError(
            f"Estimated cost {estimated_cost} would exceed budget {budget_limit}"
        )
    
    # Get generation settings
    concurrency = int(os.getenv("VIDEO_GENERATOR_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)
    
    async def generate_with_retry(clip_prompt: ClipPrompt) -> Optional[Clip]:
        """Generate clip with retry logic."""
        async with semaphore:
            # Download and upload image if available
            image_url = None
            if clip_prompt.scene_reference_url:
                image_url = await download_and_upload_image(
                    clip_prompt.scene_reference_url,
                    job_id
                )
            
            # Retry logic
            for attempt in range(3):
                try:
                    clip = await generate_video_clip(
                        clip_prompt=clip_prompt,
                        image_url=image_url,
                        settings=settings_dict,
                        job_id=job_id
                    )
                    return clip
                except RetryableError as e:
                    if attempt < 2:
                        delay = 2 * (2 ** attempt)  # 2s, 4s, 8s
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Clip {clip_prompt.clip_index} failed after 3 retries",
                            extra={"job_id": str(job_id)}
                        )
                        return None
                except Exception as e:
                    logger.error(
                        f"Clip {clip_prompt.clip_index} failed: {e}",
                        extra={"job_id": str(job_id)}
                    )
                    return None
            return None
    
    # Generate all clips in parallel
    start_time = time.time()
    tasks = [generate_with_retry(cp) for cp in clip_prompts.clip_prompts]
    results = await asyncio.gather(*tasks)
    
    # Filter successful clips
    successful = [r for r in results if r is not None]
    failed = len(results) - len(successful)
    
    # Validate minimum clips
    if len(successful) < 3:
        raise PipelineError(
            f"Insufficient clips generated: {len(successful)} < 3 (minimum required)"
        )
    
    total_generation_time = time.time() - start_time
    total_cost = sum(c.cost for c in successful)
    
    return Clips(
        job_id=job_id,
        clips=successful,
        total_clips=len(clip_prompts.clip_prompts),
        successful_clips=len(successful),
        failed_clips=failed,
        total_cost=total_cost,
        total_generation_time=total_generation_time
    )
```

---

## Error Handling

### Retryable Errors
- **Rate limits (429):** Retry with exponential backoff
- **Timeout errors:** Retry with same parameters
- **Network errors:** Retry (connection issues)
- **Model unavailable:** Try fallback model (CogVideoX)

### Non-Retryable Errors
- **Invalid input:** Bad prompt format, unsupported image format
- **Budget exceeded:** Abort immediately
- **Authentication errors:** Invalid API token

### Error Classification
```python
def is_retryable_error(error: Exception) -> bool:
    """Check if error is retryable."""
    if isinstance(error, RetryableError):
        return True
    if isinstance(error, TimeoutError):
        return True
    if "rate limit" in str(error).lower():
        return True
    if "network" in str(error).lower() or "connection" in str(error).lower():
        return True
    return False
```

---

## Cost Tracking

### Per-Clip Cost Tracking
- Track cost after each clip completes successfully
- Use actual duration (not estimated) for cost calculation
- Update `jobs.total_cost` field in database

### Budget Enforcement
- Check budget **before starting generation** (pre-flight check)
- If budget would be exceeded: Raise `BudgetExceededError` immediately
- Track costs as clips complete (for monitoring, not enforcement)

---

## Testing Strategy

### Unit Tests
1. **`test_generator.py`:**
   - Replicate API integration (mocked)
   - Polling logic
   - Duration mapping
   - Error handling

2. **`test_image_handler.py`:**
   - Image download from Supabase
   - Image upload to Replicate
   - Error handling (download failures)

3. **`test_cost_estimator.py`:**
   - Cost estimation accuracy
   - Environment-specific costs

4. **`test_process.py`:**
   - Parallel generation flow
   - Retry logic
   - Partial success handling
   - Budget enforcement

### Integration Tests
- End-to-end with mock Replicate API
- Test with real Supabase Storage (development)
- Test cost tracking integration

### E2E Tests
- Generate real clips (development mode, cheaper settings)
- Verify duration handling
- Verify cost tracking accuracy

---

## Performance Targets

- **Generation Time:** <180 seconds for 6 clips (parallel, 5 concurrent)
- **Cost per Clip:** 
  - Production: ~$0.20 per 6s clip
  - Development: ~$0.01 per 6s clip
- **Success Rate:** ≥90% of clips generated successfully
- **Minimum Clips:** ≥3 successful clips required (job fails if <3)

---

## Dependencies

### External Services
- **Replicate API:** Video generation
- **Supabase Storage:** Image download, video upload

### Internal Dependencies
- `shared.storage.StorageClient` - Image/video file operations
- `shared.cost_tracking.CostTracker` - Cost tracking
- `shared.errors` - Exception hierarchy
- `shared.retry.retry_with_backoff` - Retry decorator
- `shared.logging.get_logger` - Logging
- `api_gateway.services.budget_helpers` - Budget limits

### Python Packages
- `replicate>=0.20.0` - Replicate API client
- `asyncio` - Parallel processing
- `aiohttp` or `httpx` - HTTP requests for downloads

---

## Known Limitations

1. **Duration Accuracy:** Models may not generate exact durations (±2s tolerance)
2. **Image Support:** Only one image per clip (scene reference only)
3. **Model Availability:** Depends on Replicate service availability
4. **Cost Estimation:** Estimates may vary from actual costs

---

## Future Enhancements (Post-MVP)

1. **Multi-Image Support:** Test if models support multiple images, implement compositing if needed
2. **Adaptive Polling:** Implement adaptive polling intervals if needed
3. **Model Selection:** Auto-select best model based on prompt characteristics
4. **Caching:** Cache generated clips for identical prompts
5. **Quality Tiers:** Allow users to select quality vs speed trade-offs

---

## Success Metrics

- **Functional:** ≥3 clips generated per job
- **Performance:** <180s for 6 clips
- **Cost:** Within budget estimates (±20% tolerance)
- **Reliability:** ≥90% success rate
- **Quality:** Clips match prompt descriptions (subjective, manual review)

---

**Document Status:** Ready for Implementation  
**Next Action:** Begin implementation with `config.py` and `cost_estimator.py`, then `image_handler.py`, then `generator.py`, finally `process.py`

