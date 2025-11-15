# Video Generator Module - Part 3: Process

**Version:** 1.0 | **Date:** November 2025  
**Module:** Module 7 (Video Generator) - Part 3 of 3  
**Phase:** Phase 3  
**Status:** Implementation-Ready

---

## Executive Summary

This document specifies **Part 3: Process** of the Video Generator module, which orchestrates parallel video clip generation. This component depends on Parts 1 (Foundation) and 2 (Generator) to generate all clips in parallel with retry logic and budget enforcement.

**Component:**
- `process.py` - Main entry point for parallel clip generation

**Dependencies:** Parts 1 & 2 (all foundation and generator components)  
**Integration:** Orchestrator calls this function

---

## High-Level Requirements

### Purpose
Generate all video clips in parallel:
1. **Budget Check:** Pre-flight cost estimation and budget enforcement
2. **Parallel Generation:** Generate clips concurrently (5 by default)
3. **Retry Logic:** Retry failed clips with exponential backoff
4. **Partial Success:** Accept ≥3 successful clips total
5. **Cost Tracking:** Track costs as clips complete

### Inputs
- `job_id: UUID` - Job identifier
- `clip_prompts: ClipPrompts` - All clip prompts from Prompt Generator

### Output
- `Clips` model with:
  - `clips: List[Clip]` - At least 3 successful clips
  - `total_clips: int` - Total number of prompts
  - `successful_clips: int` - Number of successful clips
  - `failed_clips: int` - Number of failed clips
  - `total_cost: Decimal` - Total cost
  - `total_generation_time: float` - Total time

### Success Criteria
- ✅ Minimum 3 clips generated successfully (configurable)
- ✅ Parallel generation works (3 concurrent by default, configurable)
- ✅ Retry logic works (3 attempts per clip)
- ✅ Budget enforcement works (pre-flight + mid-generation checks)
- ✅ Total time <180s for 6 clips (with 3 concurrent)

---

## Architecture & Design Decisions

### 1. Budget Enforcement

**Pre-Flight Check:**
- Estimate total cost before starting
- Check if `current_cost + estimated_cost > budget_limit`
- Abort immediately if exceeded (don't start generation)

**Mid-Generation Check (Optional):**
- After each clip completes, check if total cost exceeds budget
- If exceeded, cancel remaining clips and return partial results
- Log warning but don't fail job (better UX than hard failure)

**Rationale:** Pre-flight check prevents wasted resources. Mid-generation check provides safety net for cost overruns.

### 2. Parallel Generation

**Concurrency Control:**
- Use `asyncio.Semaphore(concurrency)` for concurrency limit
- Default: 3 concurrent clips (configurable via env var `VIDEO_GENERATOR_CONCURRENCY`)
- Production: Can increase to 5 if rate limits allow
- Development: 3 concurrent (safer, lower cost spikes, avoids rate limits)

**Implementation:**
- Generate all clips in parallel using `asyncio.gather()`
- Track individual clip status (success/failure)
- Handle partial failures gracefully

### 3. Retry Strategy

**Clear Boundaries:**
- Retry individual clips (not batches)
- 3 attempts per clip with exponential backoff (2s, 4s, 8s)
- Accept partial success: Job succeeds if ≥3 clips successful total
- Fail job if <3 successful clips after all retries

**Retryable Errors:**
- Rate limits (429)
- Timeout errors
- Network errors
- Model unavailable (try fallback)

**Non-Retryable Errors:**
- Invalid input
- Budget exceeded
- Authentication errors

### 4. Partial Success Handling

**Rules:**
- Accept job if ≥3 clips successful (even if some fail)
- Fail job if <3 clips successful after all retries
- Track failed clips for debugging
- Minimum clips configurable via env var (default: 3)

**Rationale:** Better UX than failing entire job for one bad clip. Configurable threshold allows flexibility.

---

## File Specification

### `process.py`

**Purpose:** Main entry point for parallel video clip generation.

**Function:**
```python
"""
Main entry point for video generation.

Orchestrates parallel clip generation with retry logic and budget enforcement.
"""
import asyncio
import os
import time
from typing import Optional
from uuid import UUID
from decimal import Decimal

from shared.models.video import ClipPrompts, Clips, Clip
from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import BudgetExceededError, PipelineError, RetryableError
from shared.logging import get_logger
from api_gateway.services.budget_helpers import get_budget_limit

from modules.video_generator.config import get_generation_settings
from modules.video_generator.cost_estimator import estimate_total_cost
from modules.video_generator.generator import generate_video_clip
from modules.video_generator.image_handler import download_and_upload_image

logger = get_logger("video_generator.process")

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
    environment = settings.environment
    settings_dict = get_generation_settings(environment)
    
    # Budget check before starting
    logger.info(
        f"Estimating costs for {len(clip_prompts.clip_prompts)} clips",
        extra={"job_id": str(job_id)}
    )
    estimated_cost = estimate_total_cost(clip_prompts, environment)
    current_cost = await cost_tracker.get_total_cost(job_id)
    budget_limit = get_budget_limit(environment)
    
    logger.info(
        f"Budget check: current={current_cost}, estimated={estimated_cost}, limit={budget_limit}",
        extra={"job_id": str(job_id)}
    )
    
    if current_cost + estimated_cost > budget_limit:
        raise BudgetExceededError(
            f"Estimated cost {estimated_cost} would exceed budget {budget_limit}. "
            f"Current cost: {current_cost}"
        )
    
    # Get concurrency limit (default: 3 for safety, avoid rate limits)
    # Replicate allows 600 predictions/min, so 3 concurrent is conservative
    concurrency = int(os.getenv("VIDEO_GENERATOR_CONCURRENCY", "3"))
    semaphore = asyncio.Semaphore(concurrency)
    
    # Optional: Add client-side rate limiter for extra safety
    # See PRD_video_generator_weaknesses_analysis.md for implementation
    
    logger.info(
        f"Starting parallel generation: {len(clip_prompts.clip_prompts)} clips, {concurrency} concurrent",
        extra={"job_id": str(job_id)}
    )
    
    async def generate_with_retry(clip_prompt: ClipPrompt) -> Optional[Clip]:
        """
        Generate clip with retry logic.
        
        Args:
            clip_prompt: ClipPrompt to generate
            
        Returns:
            Clip if successful, None if failed after retries
        """
        async with semaphore:
            # Download and upload image if available
            image_url = None
            if clip_prompt.scene_reference_url:
                logger.debug(
                    f"Preparing image for clip {clip_prompt.clip_index}",
                    extra={"job_id": str(job_id)}
                )
                image_url = await download_and_upload_image(
                    clip_prompt.scene_reference_url,
                    job_id
                )
                if not image_url:
                    logger.warning(
                        f"Image download failed for clip {clip_prompt.clip_index}, proceeding text-only",
                        extra={"job_id": str(job_id)}
                    )
            
            # Retry logic
            for attempt in range(3):
                try:
                    logger.info(
                        f"Generating clip {clip_prompt.clip_index} (attempt {attempt + 1}/3)",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    
                    clip = await generate_video_clip(
                        clip_prompt=clip_prompt,
                        image_url=image_url,
                        settings=settings_dict,
                        job_id=job_id,
                        environment=environment
                    )
                    
                    logger.info(
                        f"Clip {clip_prompt.clip_index} generated successfully",
                        extra={"job_id": str(job_id), "clip_index": clip_prompt.clip_index}
                    )
                    
                    return clip
                    
                except RetryableError as e:
                    if attempt < 2:
                        delay = 2 * (2 ** attempt)  # 2s, 4s, 8s
                        logger.warning(
                            f"Clip {clip_prompt.clip_index} failed (retryable), retrying in {delay}s",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "attempt": attempt + 1,
                                "error": str(e)
                            }
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Clip {clip_prompt.clip_index} failed after 3 retries",
                            extra={
                                "job_id": str(job_id),
                                "clip_index": clip_prompt.clip_index,
                                "error": str(e)
                            }
                        )
                        return None
                except Exception as e:
                    # Non-retryable error
                    logger.error(
                        f"Clip {clip_prompt.clip_index} failed (non-retryable): {e}",
                        extra={
                            "job_id": str(job_id),
                            "clip_index": clip_prompt.clip_index,
                            "error": str(e)
                        }
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
    
    total_generation_time = time.time() - start_time
    
    logger.info(
        f"Generation complete: {len(successful)} successful, {failed} failed",
        extra={
            "job_id": str(job_id),
            "successful": len(successful),
            "failed": failed,
            "total_time": total_generation_time
        }
    )
    
    # Validate minimum clips (configurable)
    min_clips = int(os.getenv("VIDEO_GENERATOR_MIN_CLIPS", "3"))
    if len(successful) < min_clips:
        raise PipelineError(
            f"Insufficient clips generated: {len(successful)} < {min_clips} (minimum required). "
            f"Failed clips: {failed}"
        )
    
    # Calculate total cost and check budget
    total_cost = sum(c.cost for c in successful)
    current_total = await cost_tracker.get_total_cost(job_id)
    budget_limit = get_budget_limit(environment)
    
    # Mid-generation budget check (warn if exceeded, but don't fail)
    if current_total > budget_limit:
        logger.warning(
            f"Budget exceeded during generation: {current_total} > {budget_limit}",
            extra={
                "job_id": str(job_id),
                "current_cost": float(current_total),
                "budget_limit": float(budget_limit)
            }
        )
    
    logger.info(
        f"Video generation complete: {len(successful)} clips, ${total_cost} total cost",
        extra={
            "job_id": str(job_id),
            "total_clips": len(successful),
            "total_cost": float(total_cost),
            "current_total_cost": float(current_total),
            "generation_time": total_generation_time
        }
    )
    
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

### Budget Exceeded
- **Pre-flight check:** Raise `BudgetExceededError` before starting
- **Clear error message:** Include current cost, estimated cost, limit

### Insufficient Clips
- **Validation:** Check if ≥3 clips successful
- **Error message:** Include number of successful/failed clips

### Retry Logic
- **Individual clips:** Retry each clip independently
- **Exponential backoff:** 2s, 4s, 8s delays
- **Max attempts:** 3 per clip

---

## Testing Strategy

### Unit Tests

**`test_process.py`:**
- Test budget enforcement (pre-flight check)
- Test parallel generation (mocked generator)
- Test retry logic (simulate failures)
- Test partial success handling (some clips fail)
- Test insufficient clips error (<3 successful)
- Test concurrency control (semaphore)
- Test cost tracking integration

### Integration Tests
- End-to-end with real components (development mode)
- Test with real Replicate API (cheaper settings)
- Test with real Supabase Storage
- Verify parallel execution
- Verify retry behavior

### E2E Tests
- Generate real clips (development mode)
- Verify all clips generated
- Verify cost tracking
- Verify performance (<180s for 6 clips)

---

## Dependencies

### Internal Dependencies
- `modules.video_generator.config` - Settings
- `modules.video_generator.cost_estimator` - Cost estimation
- `modules.video_generator.image_handler` - Image handling
- `modules.video_generator.generator` - Clip generation
- `shared.cost_tracking.CostTracker` - Cost tracking
- `shared.errors` - Exception hierarchy
- `shared.logging.get_logger` - Logging
- `api_gateway.services.budget_helpers` - Budget limits

### External Dependencies
- `asyncio` - Parallel processing

---

## Performance Targets

- **Generation Time:** <180 seconds for 6 clips (parallel, 3 concurrent)
- **Success Rate:** ≥90% of clips generated successfully
- **Minimum Clips:** ≥3 successful clips required (configurable)
- **Rate Limit Handling:** Graceful handling of 429 errors with retry logic

---

## Known Limitations

1. **Concurrency Limits:** Default 3 concurrent to avoid Replicate rate limits (can increase if needed)
2. **Partial Failures:** Some clips may fail even with retries
3. **Cost Estimation:** Estimates may vary from actual costs (monitor and adjust)
   - **Improvement:** Actual costs tracked when available (see generator.py)
   - **Future:** Cost calibration system (see weaknesses analysis)
4. **Rate Limiting:** Basic retry logic with exponential backoff
   - **Improvement:** Retry-After header parsing added (see generator.py)
   - **Future:** Client-side rate limiter (see weaknesses analysis)
5. **Budget Overruns:** Mid-generation check warns but doesn't stop (may exceed budget slightly)
6. **Model Schema:** Model parameters not verified before use
   - **Action Required:** Verify SVD model schema before implementation
   - **See:** `PRD_video_generator_weaknesses_analysis.md` for verification strategy

---

## Integration with Orchestrator

**Orchestrator Call:**
```python
from modules.video_generator.process import process

clips = await process(job_id, clip_prompts)
```

**Progress Updates:**
- Orchestrator handles progress updates (50-85%)
- This module focuses on generation logic

**Error Propagation:**
- Raise `BudgetExceededError` if budget exceeded
- Raise `PipelineError` if <3 clips generated
- Other errors propagate to orchestrator

---

## Success Metrics

- **Functional:** ≥3 clips generated per job
- **Performance:** <180s for 6 clips
- **Reliability:** ≥90% success rate
- **Cost:** Within budget estimates

---

**Document Status:** Ready for Implementation  
**Next Action:** Implement `process.py` with comprehensive error handling, then integrate with orchestrator

