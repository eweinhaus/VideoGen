# PRD: Cascading Duration Compensation - Part 1: Video Generator Buffer Calculation

**Version:** 1.0  
**Date:** January 2025  
**Status:** Ready for Implementation  
**Dependencies:** PRD_video_generator.md

**Related Documents:**
- `planning/docs/DURATION_COMPENSATION_ANALYSIS.md` - Pros/cons analysis and recommendations
- `planning/docs/DURATION_STRATEGY_REDESIGN.md` - Original strategy redesign document
- `planning/docs/DURATION_COMPENSATION_DECISIONS.md` - Decision analysis
- `PRD_duration_compensation_part2.md` - Part 2: Composer Cascading Compensation
- `PRD_video_generator.md` - Video generator module

---

## Executive Summary

Implement buffer duration calculation in the video generator to request longer durations than targets, ensuring adequate clip length for cascading compensation. This is Part 1 of the cascading duration compensation feature.

**Key Changes:**
1. Request longer durations from video generation models (model-specific strategy)
2. Store original target duration in clip metadata
3. Model-specific logic for discrete vs continuous duration support

**Benefits:**
- Reduces shortfall frequency
- Enables cascading compensation (Part 2)
- Industry-standard approach (10-20% buffer proven effective)

---

## Problem Statement

### Current Issues

1. **No Buffer Strategy**: We request exact durations, leading to frequent shortfalls
2. **Model Constraints**: Discrete models (Kling) only support 5s/10s, can't apply precise percentage buffers
3. **Inconsistent Results**: Duration variance across models causes unpredictable outcomes

### User Impact

- Inconsistent video durations cause audio sync issues
- Higher failure rates due to duration mismatches
- Need for compensation increases (addressed in Part 2)

---

## Goals & Success Criteria

### Primary Goals

1. **Request longer durations** - Model-specific buffer strategy to ensure adequate clip length
2. **Preserve original targets** - Store original target duration for compensation algorithm
3. **Handle model constraints** - Different strategies for discrete vs continuous models

### Success Metrics

- **Buffer Application Rate**: 100% of clips request buffer (where model supports it)
- **Cost Impact**: <20% average increase (accept >20% for discrete models, targets 5.1-7.5s)
- **Model Coverage**: All models have buffer strategy defined

---

## Requirements

### Functional Requirements

#### FR1: Buffer Duration Calculation
- **Priority**: P0 (Must Have)
- **Description**: Request longer durations than target (model-specific strategy)
- **Details**:
  - **Discrete Models (Kling, etc.):** Use "maximum buffer" strategy
    - Targets ≤5s: Request 5s (no buffer possible due to model constraints)
    - Targets >5s: Request 10s (maximum available, may exceed 25% buffer)
    - Documented as "maximum buffer" (not percentage-based)
  - **Continuous Models (Veo 3.1, etc.):** Apply percentage buffer
    - Request `min(target * buffer_multiplier, 10.0)` (default 25% buffer, cap at 10s)
    - Buffer configurable via `VIDEO_GENERATOR_DURATION_BUFFER` env var (default: 1.25)
  - Store original target duration in clip metadata for compensation
- **Acceptance Criteria**:
  - All video generation requests include buffer calculation
  - Model-specific logic correctly handles discrete vs continuous duration support
  - Original target duration preserved for compensation algorithm
  - Cost impact documented (discrete models may have >20% increase for some targets)

### Non-Functional Requirements

#### NFR1: Performance
- Buffer calculation should not add measurable overhead to generation requests

#### NFR2: Maintainability
- Code should be well-documented with clear model-specific logic
- Unit tests should cover all model types and edge cases

---

## Technical Design

### Architecture Overview

```
Video Generator → Buffer Calculation (Model-Specific)
       ↓
Request Longer Duration (25% buffer or maximum)
       ↓
Generate Clips (actual duration may vary)
       ↓
Store Original Target Duration (for Part 2 compensation)
```

### Component Changes

#### 1. Video Generator (`modules/video_generator/generator.py`)

**Changes:**
- Add buffer calculation before requesting duration
- Model-specific logic for discrete vs continuous durations
- Store original target duration in clip metadata

**Code Location:** Lines 259-273

**Implementation:**
```python
# Calculate buffer duration
target_duration = clip_prompt.duration
buffer_multiplier = float(os.getenv("VIDEO_GENERATOR_DURATION_BUFFER", "1.25"))

# Store original target for compensation algorithm
clip_metadata = {"original_target_duration": target_duration}

if selected_model_key == "veo_31":
    # Veo 3.1: Continuous duration support - apply percentage buffer
    requested_duration = min(target_duration * buffer_multiplier, 10.0)
    input_data["duration"] = requested_duration
elif selected_model_key.startswith("kling"):
    # Kling: Discrete duration support - use maximum buffer strategy
    if target_duration <= 5.0:
        input_data["duration"] = 5  # No buffer possible for ≤5s targets
    else:
        input_data["duration"] = 10  # Maximum buffer for >5s targets
else:
    # Other discrete models: Similar to Kling (maximum buffer strategy)
    if target_duration <= 5.0:
        input_data["duration"] = 5
    else:
        input_data["duration"] = 10

# Store metadata for compensation (if model supports it)
# Note: Some models may not support metadata, store in Clip model instead
```

**Storage of Original Target:**
- Store in `Clip` model: Add `original_target_duration` field (optional, defaults to `target_duration`)
- Or: Store in compensation metadata during Part 2 (simpler, no model change)

---

## Configuration

### Environment Variables

```bash
# Duration buffer multiplier (default: 1.25 = 25% buffer)
# Only applies to continuous models (Veo 3.1, etc.)
VIDEO_GENERATOR_DURATION_BUFFER=1.25
```

---

## Implementation Plan

### Phase 1: Buffer Calculation (Week 1)

1. **Update Video Generator**
   - Add buffer calculation logic
   - Model-specific duration handling
   - Store original target duration
   - Test with various targets and models

2. **Update Clip Model** (Optional)
   - Add `original_target_duration` field if storing in model
   - Or: Document that Part 2 will handle storage

3. **Unit Tests**
   - Test buffer calculation for all models
   - Test edge cases (target = 5.0s, target = 10.0s)
   - Test original target preservation

---

## Testing Strategy

### Unit Tests

1. **Buffer Calculation Tests**
   - Kling models (5s/10s discrete)
   - Veo 3.1 (continuous, capped at 10s)
   - Other discrete models
   - Edge cases (target = 5.0s, target = 10.0s, target = 8.0s)

2. **Original Target Storage Tests**
   - Verify original target is preserved
   - Test with all model types

### Integration Tests

1. **Video Generation Tests**
   - Generate clips with buffer calculation
   - Verify requested durations are correct
   - Verify original targets are stored

---

## Edge Cases & Error Handling

### Edge Case 1: Model Duration Constraints

**Scenario:** Model only supports discrete durations (5s/10s)

**Handling:**
- **Discrete Models:** Use "maximum buffer" strategy
  - Targets ≤5s: Request 5s (no buffer possible, log warning)
  - Targets >5s: Request 10s (maximum buffer, may exceed 25%)
- **Continuous Models:** Apply percentage buffer (25% default, capped at 10s)
- Document strategy difference clearly
- Accept higher cost for discrete models (targets 5.1-7.5s)

### Edge Case 2: Target Exactly at Boundary

**Scenario:** Target is exactly 5.0s or 10.0s

**Handling:**
- Target = 5.0s: Request 5s (no buffer, acceptable)
- Target = 10.0s: Request 10s (no buffer, but at maximum)
- Log when buffer cannot be applied

---

## Success Metrics & Monitoring

### Key Metrics

1. **Buffer Application Rate**: % of clips that received buffer
   - Target: 100% (where model supports it)
   - Track: Per model type

2. **Cost Impact**: Increase in generation costs
   - Target: <20% average across all jobs
   - Accept: Discrete models may have >20% increase for targets 5.1-7.5s (requesting 10s instead of 5s)
   - Monitor: Track per model and per target duration range
   - Report: Actual cost increase in metrics

3. **Original Target Preservation**: % of clips with original target stored
   - Target: 100%
   - Critical for Part 2 compensation

### Logging

**Per-Clip Logging:**
```json
{
  "clip_index": 1,
  "original_target_duration": 8.0,
  "requested_duration": 10.0,
  "buffer_strategy": "maximum",
  "model": "kling_v21"
}
```

---

## Risks & Mitigation

### Risk 1: Cost Increase

**Impact:** Medium - Requesting longer durations increases costs

**Mitigation:**
- Start with 25% buffer for continuous models, maximum buffer for discrete models
- Monitor cost impact per model and per target duration range
- Track actual cost increase in metrics
- Accept that discrete models may have >20% increase for some targets (5.1-7.5s)
- Adjust buffer strategy based on data if cost impact is too high
- Document cost trade-offs clearly

### Risk 2: Model Support Unknown

**Impact:** Low - Some models may not support expected durations

**Mitigation:**
- Test Veo 3.1 with various durations to confirm continuous support
- Fallback to discrete strategy if continuous not supported
- Log when buffer cannot be applied

---

## Dependencies

### Code Dependencies
- `modules/video_generator/generator.py` - Duration request logic
- `shared/models/video.py` - Clip model (optional: add original_target_duration field)

### External Dependencies
- Video generation models (Kling, Veo 3.1, etc.)

---

## Open Questions

1. **Veo 3.1 Duration Support**: Does Veo support continuous durations or only discrete values?
   - **Action**: Test Veo 3.1 with various durations
   - **Impact**: Affects buffer calculation logic
   - **Decision**: Treat as continuous until proven otherwise, apply 25% buffer

2. **Original Target Storage**: Store in Clip model or compensation metadata?
   - **Decision**: Store in compensation metadata during Part 2 (simpler, no model change)
   - **Impact**: Part 2 handles storage, Part 1 just preserves value

---

## Approval

**Status:** Ready for Implementation  
**Approved By:** [Pending]  
**Implementation Start Date:** [TBD]  
**Target Completion:** [TBD]

---

## Related Documents

- `PRD_duration_compensation_part2.md` - Part 2: Composer Cascading Compensation
- `planning/docs/DURATION_COMPENSATION_DECISIONS.md` - Decision analysis

