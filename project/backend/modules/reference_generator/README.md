# Reference Generator Module (Module 5)

Generates high-quality reference images for scenes and characters using Stable Diffusion XL (SDXL) via Replicate API.

## Overview

The Reference Generator creates visual reference images that ensure consistency across video clips. It generates:
- **Scene references**: One per unique scene location/setting
- **Character references**: One per character

All images are generated in parallel with controlled concurrency (default: 6 concurrent) and uploaded to Supabase Storage immediately after generation.

## Features

- **Parallel Generation**: Generates all images concurrently (6 concurrent by default)
- **Cost Tracking**: Tracks actual costs per image (~$0.005 per image)
- **Partial Success Handling**: Returns results if ≥50% threshold met AND minimum 1 scene + 1 character
- **Retry Logic**: 1 retry per image with exponential backoff
- **Storage Integration**: Uploads to Supabase Storage with 14-day signed URLs

## Usage

```python
from modules.reference_generator import process
from shared.models.scene import ScenePlan
from uuid import UUID

# Generate reference images
references = await process(
    job_id=UUID("..."),
    plan=scene_plan,
    duration_seconds=180.0  # Optional, for budget checks
)

# Check if generation succeeded
if references is None:
    # Fallback to text-only mode
    print("Reference generation failed, using text-only prompts")
else:
    # Use reference images
    for scene_ref in references.scene_references:
        print(f"Scene {scene_ref.scene_id}: {scene_ref.image_url}")
```

## Configuration

### Environment Variables

- `REPLICATE_API_TOKEN` (required): Replicate API token (starts with `r8_`)
- `REFERENCE_MODEL_DEV` (optional): Override model version for development
- `REFERENCE_GEN_CONCURRENCY` (optional): Concurrency limit (default: 6)
- `ENVIRONMENT`: "development" | "production" (affects model selection)

### Model Selection

- **Production & Development**: `stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245` (SDXL v1.0)
- **Rationale**: Consistency between environments, high quality, stable API
- **Cost**: ~$0.005 per image
- **Speed**: ~8-10s per image

## Partial Success Logic

The module returns `None` (fallback to text-only mode) if ANY of these conditions fail:
1. ≥50% of total images generated successfully
2. At least 1 scene reference generated
3. At least 1 character reference generated

If all three conditions pass, returns `ReferenceImages` object with status:
- `"success"`: All images generated
- `"partial"`: Threshold met but some images failed

## Error Handling

- **Retryable Errors**: Network errors, rate limits (429), timeouts
  - Retry: 1 retry per image (2 total attempts)
  - Backoff: Exponential (2s initial delay)
- **Non-Retryable Errors**: Validation errors, invalid prompts, budget exceeded
  - Fail immediately, continue with other images

## Storage

- **Bucket**: `reference-images` (private)
- **Path Format**: `{job_id}/scene_{scene_id}.png` or `{job_id}/character_{character_id}.png`
- **Signed URLs**: 14-day expiration (1209600 seconds)
- **Retention**: 14 days from job completion

## Cost Tracking

- **Cost per Image**: ~$0.005 (actual cost from API or estimate)
- **Target**: <$0.10 per job (typically 2-4 images)
- **Tracking**: Costs tracked immediately after each image generation
- **Budget**: Duration-based (`duration_minutes × $200`)

## Performance

- **Generation Time**: <60s total for 4 images (parallel)
- **Per Image**: <15s average (including API call + upload)
- **Concurrency**: 6 concurrent (configurable via `REFERENCE_GEN_CONCURRENCY`)

## Testing

```bash
# Run unit tests
PYTHONPATH=. pytest modules/reference_generator/tests/ -v

# Run with coverage
PYTHONPATH=. pytest modules/reference_generator/tests/ -v --cov=modules.reference_generator --cov-report=html
```

## Module Structure

```
reference_generator/
├── __init__.py          # Module exports
├── process.py           # Main entry point (process function)
├── generator.py         # SDXL generation logic
├── prompts.py           # Prompt synthesis
├── README.md            # This file
└── tests/               # Test suite
    ├── fixtures.py      # Test fixtures
    ├── test_prompts.py  # Prompt synthesis tests
    ├── test_generator.py # Generation tests
    └── test_integration.py # Integration tests
```

## Integration

The module is called by the orchestrator after Scene Planner:

```python
# In orchestrator.py
from modules.reference_generator.process import process

references = await process(
    job_id=UUID(job_id),
    plan=scene_plan,
    duration_seconds=audio_data.duration
)
```

The orchestrator handles:
- Budget pre-flight checks (duration-based)
- SSE event publishing
- Error handling and fallback

## Dependencies

- `replicate>=0.20.0`: Replicate API client
- `shared.storage`: Supabase Storage utilities
- `shared.cost_tracking`: Cost tracking
- `shared.retry`: Retry logic decorator
- `shared.logging`: Structured logging
- `shared.models.scene`: ScenePlan, ReferenceImages models
