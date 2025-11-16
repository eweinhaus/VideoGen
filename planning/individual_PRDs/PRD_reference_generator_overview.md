# Module 5: Reference Generator - Overview

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** Scene Planner (Module 4) - ✅ Complete

**Related Documents:**
- `PRD_reference_generator_requirements.md` - Detailed functional and technical requirements
- `PRD_reference_generator_operations.md` - Error handling, integration, and implementation

---

## Executive Summary

The Reference Generator module creates high-quality reference images for scenes and characters using Stable Diffusion XL (SDXL) via Replicate. These images ensure visual consistency across all video clips generated downstream. The module prioritizes speed and cost in development, and quality in production, while operating within the overall pipeline budget of $200 per minute of video.

**Key Metrics:**
- **Cost Target:** <$0.10 per job (typically 2-4 images × $0.005 each)
- **Generation Time:** <60s total for all images (parallel generation)
- **Success Rate:** ≥50% images required AND minimum 1 scene + 1 character reference (all conditions must pass)
- **Retry Strategy:** 1 retry per image maximum, then fallback to text-only mode

---

## Objectives

1. **Generate Reference Images:** Create scene and character reference images using SDXL
2. **Ensure Visual Consistency:** Provide visual anchors for downstream video generation
3. **Cost Efficiency:** Target <$0.10 per job while staying within duration-based budget ($200/minute)
4. **Environment Optimization:** Fast/cheap in dev, high-quality in production
5. **User Transparency:** Real-time progress updates via SSE for all operations
6. **Resilient Error Handling:** Graceful degradation with retry logic and fallback modes

---

## System Architecture

### Module Position in Pipeline

```
[3] Audio Parser → [4] Scene Planner → [5] Reference Generator → [6] Prompt Generator
                                                                    ↓
                                                          [7] Video Generator
```

### Data Flow

```
Input: ScenePlan (from Scene Planner)
  ↓
Extract: Unique scenes + characters
  ↓
Generate: All reference images in parallel (controlled concurrency)
  ↓
Upload: Each image to Supabase Storage immediately
  ↓
Output: ReferenceImages (with URLs, costs, metadata)
```

### Key Components

1. **Prompt Synthesis:** Combines scene/character descriptions with style information
2. **SDXL Generation:** Generates images via Replicate API in parallel
3. **Storage Integration:** Uploads images to Supabase Storage immediately
4. **Cost Tracking:** Tracks costs per image and enforces budget limits
5. **SSE Events:** Publishes real-time progress updates for all operations

---

## Success Criteria

### Functional
- ✅ Generates scene references (one per unique scene)
- ✅ Generates character references (one per character)
- ✅ All images generated in parallel (<60s for 4 images)
- ✅ Images stored in Supabase Storage with correct URLs
- ✅ Cost tracked accurately per image
- ✅ SSE events sent for all operations (start, complete, retry, fail)

### Quality
- ✅ 1024×1024 resolution
- ✅ Images match scene/character descriptions
- ✅ Style consistency across images (same color palette, lighting)
- ✅ Professional quality (no artifacts, watermarks, text overlays)

### Performance
- ✅ <60s total generation time (parallel)
- ✅ <$0.01 per image cost
- ✅ Total cost <$0.10 per job (typically 2-4 images)
- ✅ Memory usage <500MB for 4 images

### Reliability
- ✅ 1 retry per image with exponential backoff
- ✅ Partial success handling (≥50% threshold, min 1 scene + 1 character)
- ✅ Graceful fallback to text-only mode
- ✅ Budget enforcement working
- ✅ 90%+ success rate (with retries)

### User Experience
- ✅ Real-time progress updates via SSE
- ✅ Retry information visible in UI
- ✅ Cost breakdown displayed
- ✅ Clear error messages if generation fails

---

## Key Design Decisions

### 1. Model Selection
- **Production & Development:** SDXL (`stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245`)
- **Rationale:** Consistency between environments, high quality, stable API
- **Cost:** ~$0.005 per image

### 2. Parallel Generation Strategy
- **Approach:** Controlled concurrency with `asyncio.Semaphore(4)`
- **Rationale:** Balance between speed and rate limit protection
- **Target:** <60s for 4 images

### 3. Storage Strategy
- **Approach:** Upload immediately after each image generation
- **Rationale:** Releases memory quickly, enables partial progress
- **Retention:** 14 days from job completion

### 4. Retry Strategy
- **Max Retries:** 1 retry per image (2 total attempts)
- **Backoff:** Exponential (2s delay)
- **Rationale:** Balance between resilience and speed

### 5. Partial Success Handling
- **Threshold:** All three conditions must pass:
  1. ≥50% of total images generated
  2. At least 1 scene reference generated
  3. At least 1 character reference generated
- **Fallback:** Return `None` if any condition fails (text-only mode)

### 6. Budget Management
- **Estimated Cost Calculation:** `(scenes + characters) * 0.005 * 1.2` (20% buffer)
- **Budget Limit:** `duration_minutes × $200` (duration-based, not fixed per job)
- **Enforcement:** Pre-flight check against duration-based budget + real-time tracking
- **Target:** Keep Reference Generator costs <$0.10 per job (guideline, not hard limit)

---

## Module Structure

```
project/backend/modules/reference_generator/
├── __init__.py
├── process.py          # Main entry point (process function)
├── generator.py        # SDXL generation logic
├── prompts.py          # Prompt synthesis
└── README.md
```

---

## Dependencies

**Required Modules:**
- Scene Planner (Module 4) - ✅ Complete

**Shared Components:**
- `shared.storage` - Supabase Storage utilities
- `shared.cost_tracking` - Cost tracking and budget enforcement
- `shared.retry` - Retry logic decorator
- `shared.logging` - Structured logging
- `shared.models.scene` - ScenePlan, ReferenceImages models

**External Services:**
- Replicate API (SDXL image generation)
- Supabase Storage (image storage)

**Environment Variables:**
- `REPLICATE_API_TOKEN` - Replicate API token (required)
- `REFERENCE_MODEL_DEV` - Optional dev model override
- `ENVIRONMENT` - "development" | "production"
- `REFERENCE_GEN_CONCURRENCY` - Concurrency limit (default: 4)

---

## Input/Output

### Input
- **Type:** `ScenePlan` (from Scene Planner)
- **Contains:**
  - `scenes`: List of unique scene locations
  - `characters`: List of characters
  - `style`: Visual style information (color palette, lighting, etc.)

### Output
- **Type:** `ReferenceImages` or `None`
- **Contains:**
  - `scene_references`: List of scene reference images with URLs
  - `character_references`: List of character reference images with URLs
  - `total_cost`: Total generation cost
  - `status`: "success" | "partial" | "failed"
- **Fallback:** Returns `None` if partial success threshold not met (text-only mode)
  - Threshold requires: ≥50% images AND ≥1 scene AND ≥1 character

---

## Budget Context

**Overall Budget:** $200 per minute of video (duration-based)
- For a 1-minute video: $200 budget
- For a 3-minute video: $600 budget
- For a 5-minute video: $1000 budget
- Budget is calculated as: `duration_minutes × $200`

**Reference Generator Target Allocation:** <$0.10 per job
- This is a target allocation, not a hard limit
- Actual budget check uses the duration-based calculation above
- Reference Generator costs are typically a small fraction of total pipeline cost

**Typical Costs:**
- 2 scenes + 2 characters = 4 images × $0.005 = $0.02
- With 20% buffer: $0.024
- **Well under $0.10 target**

**Large Job Example:**
- 5 scenes + 3 characters = 8 images × $0.005 = $0.04
- With 20% buffer: $0.048
- **Still well under $0.10 target**

---

## Implementation Timeline

**Estimated Time:** 6-10 hours total

**Phases:**
1. **Foundation** (1-2 hours) - Module structure, Replicate setup
2. **Core Generation** (2-3 hours) - Prompt synthesis, SDXL generation, parallel processing
3. **Storage & Integration** (1-2 hours) - Storage upload, main process function
4. **SSE Events & Progress** (1 hour) - Real-time updates
5. **Testing & Polish** (1-2 hours) - Unit tests, integration tests, documentation

---

## Related Documentation

- **Requirements:** See `PRD_reference_generator_requirements.md` for detailed functional and technical specifications
- **Operations:** See `PRD_reference_generator_operations.md` for error handling, integration points, and implementation details
- **System Architecture:** See `planning/high-level/PRD.md` for overall pipeline architecture
- **Build Order:** See `planning/high-level/BUILD_ORDER.md` for module dependencies

---

## Document Status

**Status:** Ready for Implementation  
**Next Action:** Review requirements document, then begin Phase 1 (Foundation)  
**Dependencies:** Scene Planner (Module 4) - ✅ Complete

---

**Last Updated:** November 15, 2025  
**Author:** AI Assistant  
**Reviewer:** Pending

