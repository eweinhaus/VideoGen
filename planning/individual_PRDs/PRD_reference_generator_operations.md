# Module 5: Reference Generator - Operations

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation

**Related Documents:**
- `PRD_reference_generator_overview.md` - High-level overview and architecture
- `PRD_reference_generator_requirements.md` - Detailed functional and technical requirements

---

## Error Scenarios & Handling

### ES1: API Rate Limiting
**Scenario:** Replicate API returns 429 Too Many Requests  
**Handling:**
- Retry with exponential backoff (start with 2s, increase if rate limit persists)
- Check for `Retry-After` header if provided by API
- Publish SSE event: `reference_generation_retry`
- Reduce concurrency if persistent (lower semaphore limit from 4 to 2)
- Log rate limit occurrences for monitoring
- **Note:** Adaptive backoff recommended: 2s → 5s → 10s if rate limits continue

### ES2: API Timeout
**Scenario:** Replicate API call exceeds 120s timeout  
**Handling:**
- Mark image as failed after retry
- Continue with other images
- Publish SSE event: `reference_generation_failed`
- Return partial results if threshold met

### ES3: Budget Exceeded
**Scenario:** Cost would exceed budget limit (`duration_minutes × $200`)  
**Handling:**
- **Pre-flight (Orchestrator):** Check before calling Reference Generator, raise `BudgetExceededError` if would exceed
- **During Generation (Reference Generator):** If duration provided, check before each expensive operation
- Abort generation immediately if budget would be exceeded
- Raise `BudgetExceededError`
- Publish SSE event: `error` with budget details
- Return None (fallback to text-only mode)
- **Note:** Budget limit is duration-based, not a fixed per-job amount

### ES4: Storage Upload Failure
**Scenario:** Supabase Storage upload fails  
**Handling:**
- Storage client automatically retries with exponential backoff (3 attempts, built into `upload_file()`)
- If still fails after retries, mark image as failed
- Continue with other images
- Log storage errors for debugging
- **Note:** No additional retry logic needed in Reference Generator module (handled by storage client)

### ES5: Invalid Prompt
**Scenario:** Generated prompt is invalid or too long  
**Handling:**
- Validate prompt before API call
- Truncate if too long (>500 characters)
- Log validation errors
- Skip image generation (non-retryable)

### ES6: Partial Success Below Threshold
**Scenario:** <50% images generated OR <1 scene reference OR <1 character reference  
**Handling:**
- Return `None` (fallback to text-only mode)
- Set status: `"failed"`
- Publish SSE event with failure details
- Log partial results for analysis
- Continue pipeline (Prompt Generator handles None)
- **Note:** All three conditions must pass: ≥50% total, ≥1 scene, ≥1 character

---

## Integration Points

### IP1: Scene Planner (Input)
- **Input:** `ScenePlan` object with scenes, characters, style
- **Validation:** Ensure plan has at least 1 scene and 1 character
- **Error Handling:** Raise `ValidationError` if plan invalid

### IP2: Prompt Generator (Output)
- **Output:** `ReferenceImages` object with scene/character URLs
- **Fallback:** If `None` returned, Prompt Generator uses text-only prompts
- **URL Format:** Signed URLs with 14-day expiration (use `storage.get_signed_url()`)

### IP3: Orchestrator
- **Progress Updates:** Update to 30% when stage starts
- **Budget Check:** Pre-flight check before generation using duration-based budget
  - **Note:** Budget check happens in orchestrator, NOT in Reference Generator module
  - Get audio duration from `audio_data.duration` (available in orchestrator scope after audio_parser stage)
  - Calculate budget limit: `(audio_data.duration / 60.0) × $200`
  - Calculate estimated cost: `(len(plan.scenes) + len(plan.characters)) * 0.005 * 1.2`
  - Check estimated cost against budget limit using `cost_tracker.check_budget()`
- **SSE Events:** Publish all events via `publish_event()`
- **Error Handling:** Catch exceptions and handle gracefully
- **Orchestrator Update Required:** Replace hardcoded `Decimal("50.00")` with dynamic calculation:
  ```python
  # In orchestrator.py, before calling Reference Generator:
  # audio_data is already in scope from audio_parser stage
  duration_minutes = audio_data.duration / 60.0
  budget_limit = Decimal(str(duration_minutes * 200.0))
  estimated_cost = Decimal(str((len(plan.scenes) + len(plan.characters)) * 0.005 * 1.2))
  can_proceed = await cost_tracker.check_budget(
      job_id=UUID(job_id), 
      new_cost=estimated_cost, 
      limit=budget_limit
  )
  if not can_proceed:
      raise BudgetExceededError("Would exceed budget limit before reference generation")
  ```
- **Reference Generator Module:** Does NOT need to check budget (orchestrator handles it)

### IP4: Cost Tracker
- **Track Costs:** Call `track_cost()` for each image as it's generated
- **Budget Enforcement:** 
  - Pre-flight check: Done by orchestrator (see IP3)
  - During generation: Reference Generator should check budget before each expensive operation
  - Budget limit: `duration_minutes × $200` (passed from orchestrator or retrieved from job context)
- **Cost Aggregation:** Update job total_cost atomically
- **Note:** Reference Generator may need to access duration for mid-generation budget checks. Options:
  1. Pass duration as parameter to `process()` function (recommended)
  2. Retrieve from database `jobs.audio_data` if needed
  3. Trust orchestrator pre-flight check (simpler, but less safe)

### IP5: Storage Client
- **Upload:** Use `storage.upload_file()` for each image
- **Bucket:** `reference-images` (private)
- **Retry Logic:** Storage client handles retries internally (3 attempts with exponential backoff)
- **URL Generation:** After upload, use `storage.get_signed_url()` to generate signed URLs (14-day expiration)

---

## Model Management Strategy

### MM1: SDXL Version Selection

**Current Recommendation:**
- **Production:** `stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245` (SDXL v1.0)
- **Rationale:** Stable, well-documented, consistent results
- **Version Strategy:** Pin specific version (see MM2.1), do NOT use `latest` tag

**Version Discovery:**
- Check Replicate API for available SDXL versions
- Use Context7 MCP to find best practices and latest versions
- Document version selection in code comments

### MM2: Model Update Strategy

**MM2.1: Version Pinning**
- Pin specific model version in code (not `latest`)
- Store model version in configuration:
  ```python
  REFERENCE_MODEL_PROD = "stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245"
  REFERENCE_MODEL_DEV = "stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245"  # Same for consistency
  ```

**MM2.2: Update Process**
1. **Research:** Check Replicate for new SDXL versions
2. **Test:** Generate test images with new version
3. **Compare:** A/B test new vs old version (quality, speed, cost)
4. **Deploy:** Update version in config (environment variable)
5. **Monitor:** Track success rate, cost, quality metrics
6. **Rollback:** Keep old version available for quick rollback

**MM2.3: Feature Flagging**
- Use environment variable for model selection
- Allow gradual rollout: 10% → 50% → 100% of jobs
- Monitor metrics: success rate, cost, generation time
- Rollback if metrics degrade

**MM2.4: Version Documentation**
- Document model version in code comments
- Track version history in CHANGELOG
- Log model version in generation metadata
- Include version in ReferenceImages.metadata

---

## Implementation Checklist

### Phase 1: Foundation (1-2 hours)
- [ ] Create module structure (`process.py`, `generator.py`, `prompts.py`)
- [ ] Setup Replicate client with API token
- [ ] Review shared components (storage, cost tracking, retry, logging)
- [ ] Create test fixtures (mock ScenePlan data)

### Phase 2: Core Generation (2-3 hours)
- [ ] Implement prompt synthesis (`prompts.py`)
- [ ] Implement SDXL generation (`generator.py`)
- [ ] Implement parallel generation with semaphore
- [ ] Implement retry logic (1 retry per image)
- [ ] Test with single image generation

### Phase 3: Storage & Integration (1-2 hours)
- [ ] Implement storage upload (immediate after generation)
- [ ] Implement main process function (`process.py`)
- [ ] Implement partial success handling
- [ ] Update orchestrator budget check (dynamic calculation)
- [ ] Test with mock ScenePlan

### Phase 4: SSE Events & Progress (1 hour)
- [ ] Implement SSE event publishing for all operations
- [ ] Add progress tracking
- [ ] Test SSE events in integration tests
- [ ] Verify UI receives all events

### Phase 5: Testing & Polish (1-2 hours)
- [ ] Write unit tests (prompt synthesis, generation, retry)
- [ ] Write integration tests (storage, cost tracking)
- [ ] Write end-to-end tests (full pipeline)
- [ ] Test error scenarios
- [ ] Test with real Replicate API (if available)
- [ ] Document module usage

---

## Open Questions & Decisions

### Resolved
- ✅ Scene Planner dependency: Complete
- ✅ Budget: $200 per minute of video (duration-based, not fixed per job)
- ✅ Reference Generator target: <$0.10 per job (guideline, not hard limit)
- ✅ Retry strategy: 1 retry per image maximum
- ✅ Partial success: ≥50% threshold, minimum 1 scene + 1 character
- ✅ SSE events: Send events for all operations
- ✅ Storage: Upload immediately after generation
- ✅ Model selection: SDXL for both dev and prod (consistency)

### Pending
- ⏳ Replicate API token setup (user will configure manually)
- ⏳ Storage bucket configuration (should be configured, verify)
- ⏳ Model version selection (use recommended version, allow override)

---

## Appendix

### A1: Example ReferenceImages Output

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "scene_references": [
    {
      "scene_id": "city_street",
      "character_id": null,
      "image_url": "https://storage.supabase.co/object/sign/reference-images/550e8400-e29b-41d4-a716-446655440000/scene_city_street.png?token=...",
      "prompt_used": "Rain-slicked cyberpunk street with neon signs, Neo-noir cyberpunk aesthetic, #00FFFF #FF00FF #0000FF color scheme, High-contrast neon with deep shadows, Handheld tracking shots, highly detailed, professional quality, 4K",
      "generation_time": 8.5,
      "cost": "0.005"
    }
  ],
  "character_references": [
    {
      "scene_id": null,
      "character_id": "protagonist",
      "image_url": "https://storage.supabase.co/object/sign/reference-images/550e8400-e29b-41d4-a716-446655440000/character_protagonist.png?token=...",
      "prompt_used": "Young woman, 25-30, futuristic jacket, Neo-noir cyberpunk aesthetic, #00FFFF #FF00FF #0000FF color scheme, High-contrast neon with deep shadows, Handheld tracking shots, highly detailed, professional quality, 4K",
      "generation_time": 8.2,
      "cost": "0.005"
    }
  ],
  "total_references": 2,
  "total_generation_time": 16.7,
  "total_cost": "0.010",
  "status": "success",
  "metadata": {
    "dimensions": "1024x1024",
    "format": "PNG",
    "scenes_generated": 1,
    "characters_generated": 1,
    "model_version": "stability-ai/sdxl:39ed52f2-78e6-43c4-bc99-403f850fe245",
    "environment": "production"
  }
}
```

### A2: Budget Calculation Example

**Budget Limit Calculation:**
- 1-minute video: $200 budget
- 3-minute video: $600 budget
- 5-minute video: $1000 budget
- Formula: `duration_minutes × $200`

**Reference Generator Cost Examples:**

**Typical Job (1-minute video):**
- 2 scenes + 2 characters = 4 images
- Cost per image: $0.005
- Total cost: 4 × $0.005 = $0.02
- With 20% buffer: $0.024
- **Well under $0.10 target**
- **Budget available:** $200 (Reference Generator uses <0.05% of budget)

**Large Job (3-minute video):**
- 5 scenes + 3 characters = 8 images
- Cost per image: $0.005
- Total cost: 8 × $0.005 = $0.04
- With 20% buffer: $0.048
- **Still well under $0.10 target**
- **Budget available:** $600 (Reference Generator uses <0.01% of budget)

### A3: SSE Event Flow Example

```
1. stage_update: {stage: "reference_generator", status: "started"}
2. reference_generation_start: {image_type: "scene", image_id: "city_street", current_image: 1, total_images: 4}
3. reference_generation_start: {image_type: "scene", image_id: "interior", current_image: 2, total_images: 4}
4. reference_generation_start: {image_type: "character", image_id: "protagonist", current_image: 3, total_images: 4}
5. reference_generation_start: {image_type: "character", image_id: "antagonist", current_image: 4, total_images: 4}
6. reference_generation_complete: {image_type: "scene", image_id: "city_street", completed_images: 1, cost: 0.005}
7. reference_generation_complete: {image_type: "character", image_id: "protagonist", completed_images: 2, cost: 0.005}
8. reference_generation_retry: {image_type: "scene", image_id: "interior", retry_count: 1, reason: "Rate limit"}
9. reference_generation_complete: {image_type: "scene", image_id: "interior", completed_images: 3, cost: 0.005, retry_count: 1}
10. reference_generation_failed: {image_type: "character", image_id: "antagonist", retry_count: 1, reason: "Timeout"}
11. stage_update: {stage: "reference_generator", status: "completed", successful_images: 3, failed_images: 1, total_cost: 0.015}
```

---

## Document Status

**Status:** Ready for Implementation  
**Next Action:** Begin Phase 1 (Foundation)  
**Estimated Time:** 6-10 hours total implementation  
**Dependencies:** Scene Planner (Module 4) - ✅ Complete

---

**Last Updated:** November 15, 2025  
**Author:** AI Assistant  
**Reviewer:** Pending

