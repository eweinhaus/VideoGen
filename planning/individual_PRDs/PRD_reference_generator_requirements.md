# Module 5: Reference Generator - Requirements

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation

**Related Documents:**
- `PRD_reference_generator_overview.md` - High-level overview and architecture
- `PRD_reference_generator_operations.md` - Error handling, integration, and implementation

---

## Functional Requirements

### FR1: Image Generation

**FR1.1: Scene Reference Generation**
- Generate one reference image per unique scene location/setting
- Extract unique scenes from `ScenePlan.scenes` list
- Deduplicate by `scene.id` to avoid redundant generation
- **Output:** List of `ReferenceImage` objects with `scene_id` populated

**FR1.2: Character Reference Generation**
- Generate one reference image per character
- Extract characters from `ScenePlan.characters` list
- Deduplicate by `character.id` to avoid redundant generation
- **Output:** List of `ReferenceImage` objects with `character_id` populated

**FR1.3: Parallel Generation**
- Generate all scene and character references concurrently
- Use `asyncio.Semaphore(4)` to limit concurrent API calls (rate limiting)
- Generate all images in single parallel batch (not sequential batches)
- **Target:** <60s total for 4 images (15s per image average)

### FR2: Prompt Synthesis

**FR2.1: Prompt Template Structure**
```
"{scene/character description}, {visual_style} aesthetic, {color_palette} color scheme, {lighting}, {cinematography}, highly detailed, professional quality, 4K"
```

**FR2.2: Style Integration**
- Combine `ScenePlan.style` information with scene/character descriptions
- Extract: `visual_style`, `color_palette`, `lighting`, `cinematography`
- Format color palette as comma-separated hex codes: `"#00FFFF, #FF00FF, #0000FF"`
- Inject style keywords consistently across all prompts

**FR2.3: Prompt Examples**

**Scene Prompt:**
```
"Rain-slicked cyberpunk street with neon signs, Neo-noir cyberpunk aesthetic, #00FFFF #FF00FF #0000FF color scheme, High-contrast neon with deep shadows, Handheld tracking shots, highly detailed, professional quality, 4K"
```

**Character Prompt:**
```
"Young woman, 25-30, futuristic jacket, Neo-noir cyberpunk aesthetic, #00FFFF #FF00FF #0000FF color scheme, High-contrast neon with deep shadows, Handheld tracking shots, highly detailed, professional quality, 4K"
```

### FR3: Replicate API Integration

**FR3.1: Model Selection**

**Production Environment:**
- **Model:** `stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245` (SDXL v1.0)
- **Rationale:** High quality, stable, well-documented
- **Cost:** ~$0.005 per image
- **Speed:** ~8-10s per image

**Development Environment:**
- **Model:** `stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245` (same as production)
- **Rationale:** Consistency between dev and prod for testing
- **Alternative:** Can use `stability-ai/sdxl:lite` if available (faster/cheaper)
- **Configuration:** Set via `REFERENCE_MODEL_DEV` environment variable (optional)

**FR3.2: Generation Settings**

```python
{
    "prompt": str,  # Synthesized prompt
    "negative_prompt": "blurry, static, low quality, distorted, watermark, text overlay",
    "width": 1024,
    "height": 1024,
    "num_outputs": 1,
    "guidance_scale": 7.5,  # Production: 7-9, Dev: 7.5 (balanced)
    "num_inference_steps": 30,  # Production: 30-40, Dev: 25-30 (faster)
    "scheduler": "K_EULER",
    "seed": None  # Random seed for variety
}
```

**FR3.3: Cost Tracking**
- Track actual cost from Replicate API response
- Use `cost_tracking.track_cost()` with:
  - `stage_name`: "reference_generator"
  - `api_name`: "sdxl" (or model identifier)
  - `cost`: Actual cost from API (typically $0.005)
- Log cost breakdown per image
- **Note:** If Replicate API doesn't return cost, use estimated cost ($0.005 per image) and log fallback usage

### FR4: Storage Integration

**FR4.1: Supabase Storage Upload**
- **Bucket:** `reference-images` (private bucket)
- **Path Format:** `{job_id}/scene_{scene_id}.png` or `{job_id}/character_{character_id}.png`
- **Upload Strategy:** Upload immediately after each image generation (not batch upload)
- **Content Type:** `image/png`
- **Max File Size:** 5MB per image (enforced by storage utility)

**FR4.2: URL Generation**
- Generate signed URLs for downstream use (14-day expiration)
- Store signed URLs in `ReferenceImage.image_url` field
- URLs accessible to Prompt Generator and Video Generator modules
- **Note:** Use `storage.get_signed_url()` with `expires_in=1209600` (14 days in seconds)

**FR4.3: Retention & Cleanup**
- **Retention Period:** 14 days from job completion
- **Cleanup Strategy:** 
  - Delete intermediate files immediately after job completes successfully
  - Failed jobs: Retain for 7 days for debugging
  - Scheduled cleanup: Daily cron job removes files older than retention period
  - **Implementation:** Use Supabase Storage lifecycle policies or scheduled task

### FR5: Error Handling & Retry Logic

**FR5.1: Retry Strategy**
- **Max Retries:** 1 retry per image (2 total attempts)
- **Retry Condition:** Only on `RetryableError` (network errors, rate limits, transient API failures)
- **Backoff:** Exponential backoff (2s initial delay, adaptive: 2s → 5s → 10s if rate limits persist)
- **Non-Retryable:** Validation errors, budget exceeded, invalid prompts

**FR5.2: Partial Success Handling**
- **Success Threshold:** All three conditions must be met:
  1. ≥50% of total images generated successfully
  2. At least 1 scene reference generated
  3. At least 1 character reference generated
- **Fallback Behavior:** If any condition fails, return `None` (text-only mode)
- **Status Codes:**
  - `"success"`: All images generated
  - `"partial"`: ≥50% generated AND minimum requirements met (1 scene + 1 character)
  - `"failed"`: <50% generated OR minimum requirements not met (fallback to text-only)

**FR5.3: Error Propagation**
- Log all errors with job_id context
- Publish SSE events for each failure/retry
- Continue processing other images even if one fails
- Return partial results if threshold met

### FR6: Real-Time Progress Updates (SSE)

**FR6.1: Event Types**

**Stage Start:**
```json
{
  "event_type": "stage_update",
  "data": {
    "stage": "reference_generator",
    "status": "started"
  }
}
```

**Image Generation Start:**
```json
{
  "event_type": "reference_generation_start",
  "data": {
    "image_type": "scene" | "character",
    "image_id": "scene_city_street" | "character_protagonist",
    "total_images": 4,
    "current_image": 1
  }
}
```

**Image Generation Complete:**
```json
{
  "event_type": "reference_generation_complete",
  "data": {
    "image_type": "scene" | "character",
    "image_id": "scene_city_street",
    "image_url": "https://storage.supabase.co/object/sign/reference-images/.../scene_city_street.png?token=...",
    "generation_time": 8.5,
    "cost": 0.005,
    "retry_count": 0,
    "total_images": 4,
    "completed_images": 1
  }
}
```

**Image Generation Retry:**
```json
{
  "event_type": "reference_generation_retry",
  "data": {
    "image_type": "scene" | "character",
    "image_id": "scene_city_street",
    "retry_count": 1,
    "max_retries": 1,
    "reason": "Rate limit exceeded"
  }
}
```

**Image Generation Failed:**
```json
{
  "event_type": "reference_generation_failed",
  "data": {
    "image_type": "scene" | "character",
    "image_id": "scene_city_street",
    "retry_count": 1,
    "reason": "API timeout after retry",
    "will_continue": true
  }
}
```

**Stage Complete:**
```json
{
  "event_type": "stage_update",
  "data": {
    "stage": "reference_generator",
    "status": "completed",
    "total_images": 4,
    "successful_images": 3,
    "failed_images": 1,
    "total_cost": 0.015,
    "total_time": 45.2
  }
}
```

**FR6.2: Progress Tracking**
- Update progress percentage: 30% (reference generator stage)
- Send message events for user-friendly updates
- Track individual image progress (X of Y images)

---

## Technical Requirements

### TR1: Module Structure

```
project/backend/modules/reference_generator/
├── __init__.py
├── process.py          # Main entry point (process function)
├── generator.py        # SDXL generation logic
├── prompts.py          # Prompt synthesis
└── README.md
```

### TR2: Dependencies

**Required:**
- `replicate>=0.20.0` - Replicate API client
- `shared.storage` - Supabase Storage utilities
- `shared.cost_tracking` - Cost tracking
- `shared.retry` - Retry logic decorator
- `shared.logging` - Structured logging
- `shared.models.scene` - ScenePlan, ReferenceImages models

**Environment Variables:**
- `REPLICATE_API_TOKEN` - Replicate API token (required)
- `REFERENCE_MODEL_DEV` - Optional dev model override
- `ENVIRONMENT` - "development" | "production"
- `REFERENCE_GEN_CONCURRENCY` - Concurrency limit (default: 4)

### TR3: Function Signatures

**Main Entry Point:**
```python
async def process(
    job_id: UUID,
    plan: ScenePlan,
    duration_seconds: Optional[float] = None
) -> Optional[ReferenceImages]:
    """
    Generate reference images for scenes and characters.
    
    Args:
        job_id: Job ID
        plan: Scene plan from Scene Planner
        duration_seconds: Optional audio duration in seconds (for budget checks)
                         If None, budget checks may be skipped (orchestrator handles pre-flight)
        
    Returns:
        ReferenceImages object if successful (≥50% threshold AND minimum requirements met),
        None if failed (fallback to text-only mode)
        
    Raises:
        BudgetExceededError: If budget would be exceeded (if duration provided)
        GenerationError: If generation fails critically
    """
```

**Generator Function:**
```python
async def generate_image(
    prompt: str,
    image_type: Literal["scene", "character"],
    image_id: str,
    job_id: UUID,
    settings: Dict[str, Any]
) -> Tuple[bytes, float, Decimal]:
    """
    Generate a single reference image.
    
    Args:
        prompt: Synthesized prompt
        image_type: "scene" or "character"
        image_id: Scene or character ID
        job_id: Job ID for tracking
        settings: Generation settings (steps, guidance, etc.)
        
    Returns:
        Tuple of (image_bytes, generation_time_seconds, cost)
        
    Raises:
        RetryableError: If retryable error occurs
        GenerationError: If generation fails permanently
    """
```

**Prompt Synthesis:**
```python
def synthesize_prompt(
    description: str,
    style: Style,
    image_type: Literal["scene", "character"]
) -> str:
    """
    Synthesize prompt from description and style.
    
    Args:
        description: Scene or character description
        style: Style object from ScenePlan
        image_type: "scene" or "character"
        
    Returns:
        Synthesized prompt string
    """
```

### TR4: Budget Management

**TR4.1: Pre-Flight Budget Check**
- **Location:** Budget check happens in orchestrator, NOT in Reference Generator module
- **Orchestrator Responsibilities:**
  - Calculate estimated cost: `(len(plan.scenes) + len(plan.characters)) * 0.005`
  - Add 20% buffer: `estimated_cost * 1.2`
  - Get budget limit: `(audio_data.duration / 60.0) × $200` (from audio analysis)
  - Check against budget limit using `cost_tracker.check_budget()`
  - Raise `BudgetExceededError` if would exceed limit
- **Reference Generator Responsibilities:**
  - Optionally check budget during generation if duration provided
  - Track actual costs per image using `cost_tracker.track_cost()`
- **Orchestrator Update Required:** Replace hardcoded `Decimal("50.00")` with dynamic calculation based on `audio_data.duration`

**TR4.2: Real-Time Cost Tracking**
- Track actual cost per image as generated
- Update job total_cost atomically
- Enforce budget limit: Abort if would exceed `duration_minutes × $200`
- Log cost breakdown for analysis

**TR4.3: Cost Optimization**
- Use environment-appropriate model (dev vs prod)
- Adjust inference steps based on environment (fewer steps in dev)
- Cache prompts if same scene/character appears multiple times (future optimization)
- Target: Keep Reference Generator costs <$0.10 per job (guideline)

### TR5: Performance Requirements

**TR5.1: Generation Time**
- **Target:** <60s total for 4 images (parallel generation)
- **Per Image:** <15s average (including API call + upload)
- **Timeout:** 120s per image (fail fast if exceeded)

**TR5.2: Concurrency Control**
- Use `asyncio.Semaphore(4)` to limit concurrent Replicate API calls
- Prevents rate limiting and API overload
- Configurable via environment variable: `REFERENCE_GEN_CONCURRENCY` (default: 4)

**TR5.3: Memory Management**
- Stream image downloads (don't load all into memory)
- Upload immediately after generation (releases memory)
- Set memory limits and monitor usage

### TR6: Testing Strategy

**TR6.1: Unit Tests**
- Test prompt synthesis with various style combinations
- Mock Replicate API calls
- Test error handling and retry logic
- Test partial success scenarios

**TR6.2: Integration Tests**
- Test with mock ScenePlan data
- Test storage upload/download
- Test cost tracking
- Test SSE event publishing

**TR6.3: End-to-End Tests**
- Test with real Scene Planner output (when available)
- Test with real Replicate API (requires API token)
- Test full pipeline: Scene Planner → Reference Generator → Prompt Generator
- Test fallback behavior (text-only mode)

**TR6.4: Test Data**
- Create mock ScenePlan fixtures with various styles
- Test edge cases: no scenes, no characters, duplicate IDs
- Test error scenarios: API failures, timeouts, budget exceeded

---

## Validation Rules

### Input Validation
- ScenePlan must have at least 1 scene and 1 character
- Scene IDs must be unique
- Character IDs must be unique
- Style object must have all required fields

### Output Validation
- All generated images must be 1024×1024 PNG format
- Image URLs must be valid Supabase Storage URLs
- Cost must match actual Replicate API costs
- Status must be one of: "success", "partial", "failed"

### Budget Validation
- Estimated cost must be calculated before generation
- Actual cost must be tracked per image
- Total cost must not exceed budget limits
- Budget check must occur before expensive operations

---

## Document Status

**Status:** Ready for Implementation  
**Next Action:** Review operations document for error handling and integration details

---

**Last Updated:** November 15, 2025  
**Author:** AI Assistant  
**Reviewer:** Pending

