# Video Generator Module - Part 2: Generator

**Version:** 1.0 | **Date:** November 2025  
**Module:** Module 7 (Video Generator) - Part 2 of 3  
**Phase:** Phase 3  
**Status:** Implementation-Ready

---

## Executive Summary

This document specifies **Part 2: Generator** of the Video Generator module, which handles Replicate API integration for video clip generation. This component depends on Part 1 (Foundation) for configuration, cost estimation, and image handling.

**Component:**
- `generator.py` - Replicate API integration for single clip generation

**Dependencies:** Part 1 (config.py, cost_estimator.py, image_handler.py)  
**Next Part:** Part 3 (Process) depends on this generator

---

## High-Level Requirements

### Purpose
Generate a single video clip via Replicate API:
1. **API Integration:** Start prediction, poll for completion
2. **Duration Mapping:** Map target duration to model-supported options
3. **Video Storage:** Download generated video, upload to Supabase
4. **Cost Tracking:** Track actual cost per clip
5. **Error Handling:** Classify retryable vs non-retryable errors

### Inputs
- `clip_prompt: ClipPrompt` - Prompt, duration, image URL, etc.
- `image_url: Optional[str]` - Replicate file URL (from Part 1)
- `settings: dict` - Generation settings (from Part 1)
- `job_id: UUID` - Job ID for logging

### Output
- `Clip` model with:
  - `video_url: str` - Supabase Storage URL
  - `actual_duration: float` - Actual clip duration
  - `target_duration: float` - Target duration
  - `cost: Decimal` - Actual cost
  - `status: str` - "success" or "failed"
  - `generation_time: float` - Time taken

### Success Criteria
- ✅ Single clip generated successfully
- ✅ Duration mapped correctly to model options
- ✅ Video stored in Supabase Storage
- ✅ Cost tracked accurately
- ✅ Error handling works (retryable vs non-retryable)

---

## Architecture & Design Decisions

### 1. Replicate API Integration

**Prediction Flow:**
1. Create prediction with input parameters (using `replicate.predictions.create()`)
2. Poll for completion using `prediction.reload()` (fixed 3-second interval)
3. Download video when complete (from `prediction.output`)
4. Upload to Supabase Storage

**API Usage:**
- Use `replicate.predictions.create()` for async predictions
- Model version format: `"owner/model:version"` or `"owner/model"` (string)
- Use `prediction.reload()` to check status updates
- Use `prediction.wait()` as alternative (blocks until complete)
- Handle `replicate.exceptions.ModelError` for prediction failures

**Polling Strategy:**
- Fixed 3-second interval (simple, responsive enough)
- Max wait: 120 seconds per clip (timeout)
- Use `prediction.reload()` to refresh status
- Publish progress updates (optional, for UX)

**Rationale:** Simple polling is sufficient. Adaptive polling adds complexity without significant benefit.

### 2. Duration Mapping

**Model Constraints:**
- SVD typically uses `num_frames` parameter (not fixed durations)
- Calculate: `num_frames = int(duration * fps)`
- Models may have min/max frame limits (verify with actual model)
- Accept ±2s tolerance from model output

**Implementation:**
```python
def calculate_num_frames(target_duration: float, fps: int) -> int:
    """Calculate number of frames for target duration."""
    return int(target_duration * fps)

# Note: SVD may have constraints like:
# - Min frames: 14 (0.5s at 30fps)
# - Max frames: 127 (4.2s at 30fps) or higher
# Verify actual model constraints during implementation
```

**Rationale:** SVD uses frame-based generation, not fixed duration options. Calculate frames from duration and FPS.

### 3. Video Storage

**Flow:**
1. Download video from Replicate (temporary URL)
2. Upload to Supabase Storage (`video-clips` bucket)
3. Return Supabase Storage URL

**Rationale:** Centralized storage, easier to manage, consistent with other modules.

### 4. Cost Tracking

**Actual Cost Calculation:**
- Use actual duration (not estimated) for cost calculation
- Track cost after clip completes successfully
- Update `jobs.total_cost` in database

**Rationale:** More accurate than estimates, enables real-time budget monitoring.

### 5. Error Classification

**Retryable Errors:**
- Rate limits (429)
- Timeout errors
- Network errors
- Model unavailable (try fallback)

**Non-Retryable Errors:**
- Invalid input (bad prompt, image format)
- Authentication errors
- Budget exceeded

---

## File Specification

### `generator.py`

**Purpose:** Replicate API integration for video generation.

**Functions:**
```python
"""
Replicate API integration for video clip generation.
"""
import asyncio
import time
from typing import Optional
from uuid import UUID
from decimal import Decimal
import replicate
import httpx

from shared.models.video import Clip, ClipPrompt
from shared.storage import StorageClient
from shared.cost_tracking import cost_tracker
from shared.errors import RetryableError, GenerationError, TimeoutError
from shared.logging import get_logger
from modules.video_generator.config import SVD_MODEL, COGVIDEOX_MODEL, get_generation_settings
from modules.video_generator.cost_estimator import estimate_clip_cost
from replicate.exceptions import ModelError

logger = get_logger("video_generator.generator")

def parse_retry_after_header(headers: dict) -> Optional[float]:
    """
    Parse Retry-After header from API response.
    
    Args:
        headers: Response headers dict
        
    Returns:
        Seconds to wait, or None if not present
    """
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if not retry_after:
        return None
    
    try:
        # Retry-After can be seconds (int) or HTTP date
        return float(retry_after)
    except ValueError:
        # Try parsing as HTTP date
        from email.utils import parsedate_to_datetime
        from datetime import datetime
        try:
            retry_date = parsedate_to_datetime(retry_after)
            wait_seconds = (retry_date - datetime.now()).total_seconds()
            return max(0, wait_seconds)
        except:
            return None

def get_prediction_cost(prediction) -> Optional[Decimal]:
    """
    Extract actual cost from Replicate prediction.
    
    Args:
        prediction: Replicate prediction object
        
    Returns:
        Actual cost as Decimal, or None if not available
    """
    # Replicate may include cost in different places - check common locations
    cost = None
    
    # Check prediction.metrics
    if hasattr(prediction, 'metrics') and isinstance(prediction.metrics, dict):
        cost = prediction.metrics.get('cost')
    
    # Check prediction object directly
    if cost is None and hasattr(prediction, 'cost'):
        cost = prediction.cost
    
    # Check prediction response
    if cost is None and hasattr(prediction, 'response'):
        response_data = getattr(prediction.response, 'json', lambda: {})()
        cost = response_data.get('cost') or response_data.get('metrics', {}).get('cost')
    
    if cost is not None:
        try:
            return Decimal(str(cost))
        except (ValueError, TypeError):
            logger.warning(f"Invalid cost value from prediction: {cost}")
            return None
    
    return None

def calculate_num_frames(target_duration: float, fps: int) -> int:
    """
    Calculate number of frames for target duration.
    
    Args:
        target_duration: Target duration in seconds
        fps: Frames per second
        
    Returns:
        Number of frames (int)
    """
    return int(target_duration * fps)

async def download_video_from_url(url: str) -> bytes:
    """
    Download video from URL (Replicate output).
    
    Args:
        url: Video URL
        
    Returns:
        Video bytes
        
    Raises:
        RetryableError: If download fails
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Failed to download video from {url}: {e}")
        raise RetryableError(f"Video download failed: {str(e)}") from e

def get_video_duration(video_bytes: bytes) -> float:
    """
    Get video duration using ffprobe or similar.
    
    Args:
        video_bytes: Video file bytes
        
    Returns:
        Duration in seconds
        
    Note: This is a placeholder. Actual implementation may use:
        - ffprobe (subprocess)
        - moviepy
        - opencv
    """
    # TODO: Implement actual duration extraction
    # For now, return a placeholder
    # In production, use ffprobe or similar tool
    import subprocess
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    
    try:
        # Use ffprobe to get duration
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                tmp_path
            ],
            capture_output=True,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logger.warning(f"Failed to get video duration: {e}, using estimate")
        # Fallback: estimate based on file size (rough)
        return 5.0  # Default estimate
    finally:
        import os
        os.unlink(tmp_path)

async def generate_video_clip(
    clip_prompt: ClipPrompt,
    image_url: Optional[str],
    settings: dict,
    job_id: UUID,
    environment: str = "production"
) -> Clip:
    """
    Generate single video clip via Replicate.
    
    Args:
        clip_prompt: ClipPrompt with prompt, duration, etc.
        image_url: Replicate file URL (or None for text-only)
        settings: Generation settings (resolution, fps, etc.)
        job_id: Job ID for logging
        environment: "production" or "development"
        
    Returns:
        Clip model with video URL, duration, cost, etc.
        
    Raises:
        RetryableError: If generation fails but is retryable
        GenerationError: If generation fails permanently
        TimeoutError: If generation times out (>120s)
    """
    # Calculate number of frames from target duration
    num_frames = int(clip_prompt.duration * settings["fps"])
    
    # Prepare input
    input_data = {
        "prompt": clip_prompt.prompt,
        "negative_prompt": clip_prompt.negative_prompt,
        "num_frames": num_frames,  # Frame-based generation
        **{k: v for k, v in settings.items() if k not in ["fps", "max_duration"]}  # Exclude fps and max_duration
    }
    
    # Add image if available (can be URL, file object, or file path)
    if image_url:
        input_data["image"] = image_url
    
    # Determine model (try SVD first, fallback to CogVideoX)
    model_version = SVD_MODEL  # Full model version string like "stability-ai/stable-video-diffusion:3f0457f4613a"
    use_fallback = False
    
    try:
        # Start prediction
        logger.info(
            f"Starting video generation for clip {clip_prompt.clip_index}",
            extra={"job_id": str(job_id), "target_duration": clip_prompt.duration, "num_frames": num_frames}
        )
        
        # Create prediction (model_version is string like "stability-ai/stable-video-diffusion:3f0457f4613a")
        prediction = replicate.predictions.create(
            version=model_version,  # Full model version string
            input=input_data
        )
        
        # Poll for completion (fixed 3-second interval)
        start_time = time.time()
        poll_interval = 3  # Fixed 3-second polling
        
        while prediction.status not in ["succeeded", "failed", "canceled"]:
            await asyncio.sleep(poll_interval)
            
            elapsed = time.time() - start_time
            if elapsed > 120:  # 120s timeout
                raise TimeoutError(f"Clip generation timeout after {elapsed:.1f}s")
            
            # Reload to get latest status
            prediction.reload()
            
            # Optional: Publish progress update (for UX)
            # await publish_clip_progress(job_id, clip_prompt.clip_index, elapsed)
        
        # Handle result
        if prediction.status == "succeeded":
            # Get video output from Replicate
            # Output may be FileOutput object, URL string, or list
            output = prediction.output
            
            # Handle different output formats
            if isinstance(output, list):
                # Multiple outputs - take first video
                video_output = output[0]
            else:
                video_output = output
            
            # FileOutput objects have .read() method, URLs are strings
            if hasattr(video_output, 'read'):
                # FileOutput object - read bytes directly
                logger.info(
                    f"Reading video from Replicate FileOutput",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
                video_bytes = video_output.read()
            elif isinstance(video_output, str):
                # URL string - download from URL
                logger.info(
                    f"Downloading video from Replicate URL",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index, "url": video_output}
                )
                video_bytes = await download_video_from_url(video_output)
            else:
                raise GenerationError(f"Unexpected output format: {type(video_output)}")
            
            # Get actual duration
            actual_duration = get_video_duration(video_bytes)
            
            # Upload to Supabase Storage
            storage = StorageClient()
            clip_path = f"{job_id}/clip_{clip_prompt.clip_index}.mp4"
            
            logger.info(
                f"Uploading video to Supabase Storage",
                extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
            )
            final_url = await storage.upload_file(
                bucket="video-clips",
                path=clip_path,
                file_data=video_bytes,
                content_type="video/mp4"
            )
            
            # Get actual cost from Replicate prediction (if available)
            actual_cost = get_prediction_cost(prediction)
            if actual_cost is None:
                # Fallback to estimate if cost not available
                logger.warning(
                    f"Cost not available in prediction, using estimate",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
                cost = estimate_clip_cost(actual_duration, environment)
            else:
                cost = actual_cost
                logger.info(
                    f"Using actual cost from Replicate: {cost}",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
            
            # Track cost
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="video_generator",
                api_name="svd" if not use_fallback else "cogvideox",
                cost=cost
            )
            
            generation_time = time.time() - start_time
            
            logger.info(
                f"Clip {clip_prompt.clip_index} generated successfully",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_prompt.clip_index,
                    "duration": actual_duration,
                    "cost": float(cost),
                    "generation_time": generation_time
                }
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
                generation_time=generation_time
            )
        else:
            # Check if we should try fallback model
            if not use_fallback and "unavailable" in str(prediction.error).lower():
                logger.warning(
                    f"SVD unavailable, trying fallback model",
                    extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                )
                use_fallback = True
                model_version = COGVIDEOX_MODEL
                # Retry with fallback (would need to be called from retry logic)
                raise RetryableError(f"Model unavailable, try fallback: {prediction.error}")
            
            raise GenerationError(f"Clip generation failed: {prediction.error}")
            
    except TimeoutError:
        raise
    except RetryableError:
        raise
    except replicate.exceptions.ModelError as e:
        # Replicate-specific model error
        error_str = str(e).lower()
        error_logs = getattr(e.prediction, 'logs', '') if hasattr(e, 'prediction') else ''
        
        # Check for retryable conditions
        if "rate limit" in error_str or "429" in error_str or "429" in error_logs:
            # Parse Retry-After header if available
            retry_after = None
            if hasattr(e, 'prediction') and hasattr(e.prediction, 'response'):
                headers = getattr(e.prediction.response, 'headers', {})
                retry_after = parse_retry_after_header(headers)
            
            if retry_after:
                logger.info(f"Rate limit hit, waiting {retry_after}s from Retry-After header")
                raise RetryableError(f"Rate limit error (retry after {retry_after}s): {str(e)}") from e
            else:
                raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str or "timed out" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "unavailable" in error_str or "unavailable" in error_logs:
            # Model unavailable - try fallback
            raise RetryableError(f"Model unavailable, try fallback: {str(e)}") from e
        else:
            # Non-retryable model error
            raise GenerationError(f"Model error: {str(e)}") from e
    except Exception as e:
        # Classify other errors
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str or "timed out" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "network" in error_str or "connection" in error_str:
            raise RetryableError(f"Network error: {str(e)}") from e
        else:
            raise GenerationError(f"Generation error: {str(e)}") from e
```

---

## Error Handling

**Retryable Errors:** Rate limits (429), timeouts, network errors, model unavailable (try fallback)  
**Non-Retryable Errors:** Invalid input, authentication errors, generation failures

Error classification is handled in `generator.py` - errors are raised as `RetryableError` or `GenerationError` based on error type.

---

## Testing Strategy

### Unit Tests

**`test_generator.py`:**
- Test duration mapping (various target durations)
- Test Replicate API integration (mocked)
- Test polling logic (status transitions)
- Test video download/upload
- Test cost tracking
- Test error classification
- Test timeout handling
- Test fallback model logic

### Integration Tests
- Test with real Replicate API (development mode)
- Test with real Supabase Storage
- Verify video duration extraction and cost accuracy

---

## Dependencies

### Internal Dependencies
- `modules.video_generator.config` - Model versions, settings
- `modules.video_generator.cost_estimator` - Cost calculation
- `shared.storage.StorageClient` - Video upload
- `shared.cost_tracking.CostTracker` - Cost tracking
- `shared.errors` - Exception hierarchy
- `shared.logging.get_logger` - Logging

### External Dependencies
- `replicate>=0.20.0` - Replicate API client
- `httpx>=0.24.0` - HTTP client for downloads
- `ffprobe` - Video duration extraction (system dependency, or use `moviepy`/`opencv-python` as fallback)

---

## Performance Targets

- **Generation Time:** <120 seconds per clip (timeout)
- **Success Rate:** ≥90% of clips generated successfully
- **Cost Accuracy:** Actual costs within ±20% of estimates

---

## Known Limitations

1. **Duration Extraction:** Requires ffprobe (system dependency) or fallback library (moviepy/opencv)
2. **Model Availability:** Depends on Replicate service
3. **Polling Interval:** Fixed 3s (may be too frequent for some use cases)
4. **Model Parameters:** SVD actual parameters need verification (num_frames constraints, input format)
   - **Action Required:** Verify model schema via Replicate API before implementation
   - **See:** `PRD_video_generator_weaknesses_analysis.md` for verification strategy
5. **File Input Format:** Need to verify if SVD accepts URLs, file objects, or both for image input
   - **Action Required:** Test both formats during implementation
   - **Fallback:** Current strategy tries URL first, then file object
6. **Cost Tracking:** Actual cost may not be available in prediction object
   - **Fallback:** Uses estimate if actual cost unavailable
   - **Future:** Implement cost calibration system (see weaknesses analysis)

---

## Next Steps

After completing Part 2:
1. ✅ Single clip generation works
2. ✅ Error handling tested
3. ✅ Ready for Part 3 (Process) integration

**Part 3 Dependencies:**
- `generator.py` - For parallel clip generation

---

**Document Status:** Ready for Implementation  
**Next Action:** Implement `generator.py` with comprehensive error handling and testing

