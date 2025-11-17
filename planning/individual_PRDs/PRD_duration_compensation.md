# PRD: Cascading Duration Compensation

**Version:** 1.0  
**Date:** January 2025  
**Status:** Split into Parts 1 & 2  
**Note:** This PRD has been split into two parts for better organization and implementation:

**Part 1:** `PRD_duration_compensation_part1.md` - Video Generator Buffer Calculation  
**Part 2:** `PRD_duration_compensation_part2.md` - Composer Cascading Compensation

**Related Documents:**
- `PRD_duration_compensation_part1.md` - Part 1: Video Generator Buffer Calculation
- `PRD_duration_compensation_part2.md` - Part 2: Composer Cascading Compensation
- `planning/docs/DURATION_COMPENSATION_ANALYSIS.md` - Pros/cons analysis and recommendations
- `planning/docs/DURATION_STRATEGY_REDESIGN.md` - Original strategy redesign document
- `planning/docs/DURATION_COMPENSATION_DECISIONS.md` - Decision analysis
- `PRD_composer_implementation.md` - Composer module implementation
- `PRD_video_generator.md` - Video generator module

---

## Overview

This document serves as an index for the split PRD. See the individual parts for detailed specifications:

- **Part 1** focuses on Video Generator changes (buffer calculation)
- **Part 2** focuses on Composer changes (cascading compensation, remove looping)

Both parts should be implemented sequentially: Part 1 first, then Part 2.

---

## Executive Summary (Combined)

Replace the current clip looping strategy with a **cascading duration compensation** approach that uses longer clips to compensate for shortfalls, ensuring all generated clips are utilized while maintaining perfect audio-video synchronization.

**Key Changes:**
1. Request 25% longer durations from video generation models
2. Remove clip looping logic
3. Implement cascading compensation (next clip extends to cover previous shortfall)
4. Add comprehensive duration tracking and monitoring

**Benefits:**
- No wasted clips (better resource utilization)
- Seamless narrative flow
- Automatic handling of duration variance
- Industry-standard approach (10-20% buffer proven effective)

---

## Problem Statement

### Current Issues

1. **Wasteful Looping**: When clips are shorter than intended, we loop them multiple times, creating repetitive, unnatural content
2. **No Buffer Strategy**: We request exact durations, leading to frequent shortfalls
3. **Poor Resource Utilization**: Looping wastes processing time and creates low-quality output
4. **Inconsistent Results**: Duration variance across models causes unpredictable outcomes

### User Impact

- Videos with repetitive, looped content look unprofessional
- Inconsistent video durations cause audio sync issues
- Higher failure rates due to duration mismatches

---

## Goals & Success Criteria

### Primary Goals

1. **Eliminate clip looping** - Use all clips at their natural duration
2. **Implement cascading compensation** - Next clip extends to cover previous shortfall
3. **Request longer durations** - 25% buffer to ensure adequate clip length
4. **Maintain audio sync** - Final video duration matches audio within ±0.5s

### Success Metrics

- **Compensation Rate**: <5% of clips need compensation (target)
- **Final Shortfall**: <10% of total intended duration (acceptable)
- **Job Success Rate**: Maintain >90% (no degradation)
- **Cost Impact**: <20% increase in generation costs (acceptable)
- **Quality**: No visible quality degradation in extended clips

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

#### FR2: Cascading Compensation Algorithm
- **Priority**: P0 (Must Have)
- **Description**: Each clip compensates for previous clip's shortfall
- **Details**:
  - First clip: Use full actual duration (even if short)
  - Subsequent clips: Extend target by cumulative shortfall
  - If clip is long enough: Trim to extended target, reset shortfall
  - If clip is still short: Use full duration, continue cascading
- **Acceptance Criteria**:
  - Algorithm correctly tracks cumulative shortfall
  - Clips are trimmed to extended targets when possible
  - Shortfall cascades through all clips until covered
  - Final shortfall is tracked and logged

#### FR3: Remove Loop Logic
- **Priority**: P0 (Must Have)
- **Description**: Remove all clip looping code from duration handler
- **Details**:
  - Delete loop implementation from `duration_handler.py`
  - Remove `clips_looped` tracking (keep field for backward compatibility, always 0)
  - Update composer process to use cascading instead
- **Acceptance Criteria**:
  - No looping code remains in codebase
  - All clips use natural duration (trimmed if too long, full if too short)
  - Backward compatibility maintained (clips_looped field exists but always 0)

#### FR4: Duration Tracking & Logging
- **Priority**: P1 (Should Have)
- **Description**: Comprehensive logging of duration statistics
- **Details**:
  - Log actual vs requested durations per clip
  - Track compensation applied per clip
  - Log final shortfall amount and percentage
  - Store metrics in `VideoOutput` model
- **Acceptance Criteria**:
  - All duration mismatches are logged with context
  - Compensation events include clip index, shortfall amount, extended target
  - Final shortfall percentage calculated and logged
  - Metrics available in job metadata

#### FR5: Shortfall Handling
- **Priority**: P1 (Should Have)
- **Description**: Handle cases where shortfall persists after all clips
- **Details**:
  - **Thresholds (configurable via env vars):**
    - `<10%`: Accept it (within audio sync tolerance, `-shortest` flag handles it)
    - `10-20%`: Log warning, accept it (slight quality impact acceptable)
    - `>20%`: Extend last clip using hybrid method:
      - Shortfall <2s: Freeze last frame
      - Shortfall ≥2s: Loop last 1-2 seconds of clip
      - Maximum extension: 5s (fail if more needed)
    - `>50%`: Fail job (indicates likely generation failure)
  - **Rationale for thresholds:**
    - 10%: Based on audio sync tolerance (±0.5s for 5s clip ≈ 10%)
    - 20%: Point where extension becomes necessary for quality (2s for 10s clip)
    - 50%: Indicates likely generation failure (5s shortfall for 10s clip)
  - Percentage calculated as: `(total_shortfall / total_intended_duration) * 100`
- **Acceptance Criteria**:
  - Shortfall thresholds are configurable via env vars
  - Appropriate action taken based on shortfall amount
  - Extension method selected based on shortfall size
  - Maximum extension limit enforced (5s)
  - Clear error messages for job failures
  - Last clip extension works correctly (freeze or loop)

### Non-Functional Requirements

#### NFR1: Performance
- Duration handling should not add >5s to composition time
- Cascading algorithm should be O(n) where n = number of clips

#### NFR2: Reliability
- System should handle edge cases gracefully (all clips short, no shortfalls, etc.)
- No degradation in job success rate

#### NFR3: Maintainability
- Code should be well-documented with clear algorithm explanation
- Unit tests should cover all edge cases

#### NFR4: Monitoring
- Duration statistics should be logged for analysis
- Alerts should trigger if compensation rate >20% or shortfall >10%

---

## Technical Design

### Architecture Overview

```
Video Generator → Request Longer Duration (25% buffer)
       ↓
Generate Clips (actual duration may vary)
       ↓
Composer → Cascading Compensation
       ↓
  Clip 1: Use full actual (track shortfall)
       ↓
  Clip 2: Extend target by shortfall, trim if long enough
       ↓
  Clip 3: Continue cascading...
       ↓
Final Video (duration matches audio ±0.5s)
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

#### 2. Composer Duration Handler (`modules/composer/duration_handler.py`)

**Changes:**
- Remove loop logic (lines 78-113)
- Implement cascading compensation function
- Track cumulative shortfall

**New Functions:**

```python
async def handle_cascading_durations(
    clip_paths: List[Path],
    clips: List[Clip],
    temp_dir: Path,
    job_id: UUID
) -> Tuple[List[Path], Dict[str, Any]]:
    """
    Handle duration mismatches with cascading compensation.
    
    Returns:
        (final_clip_paths, metrics_dict)
    """
    cumulative_shortfall = 0.0
    final_paths = []
    metrics = {
        "clips_trimmed": 0,
        "total_shortfall": 0.0,
        "compensation_applied": []
    }
    
    for i, (clip_path, clip) in enumerate(zip(clip_paths, clips)):
        target = clip.target_duration
        actual = clip.actual_duration
        
        if i == 0:
            # First clip: use full actual duration
            shortfall = max(0, target - actual)
            cumulative_shortfall = shortfall
            final_paths.append(clip_path)
        else:
            # Subsequent clips: compensate for previous shortfalls
            extended_target = target + cumulative_shortfall
            
            if actual >= extended_target:
                # Clip is long enough: trim to extended duration
                output_path = temp_dir / f"clip_{i}_compensated.mp4"
                # FFmpeg trim command (trim from end, use stream copy for speed)
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(clip_path),
                    "-t", str(extended_target),  # Trim to extended target
                    "-c", "copy",  # Stream copy (fast, no re-encoding)
                    "-y",
                    str(output_path)
                ]
                await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
                final_paths.append(output_path)
                metrics["clips_trimmed"] += 1
                metrics["compensation_applied"].append({
                    "clip_index": i,
                    "original_target": target,
                    "extended_target": extended_target,
                    "compensation": cumulative_shortfall
                })
                cumulative_shortfall = 0.0  # Reset
            else:
                # Clip still too short: use full duration, continue cascading
                remaining_shortfall = extended_target - actual
                cumulative_shortfall = remaining_shortfall
                final_paths.append(clip_path)
    
    metrics["total_shortfall"] = cumulative_shortfall
    return final_paths, metrics


async def extend_last_clip(
    clip_path: Path,
    shortfall_seconds: float,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Extend last clip to cover shortfall using hybrid method.
    
    Args:
        clip_path: Path to last clip
        shortfall_seconds: Amount of time to extend (in seconds)
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to extended clip
    """
    max_extension = float(os.getenv("MAX_LAST_CLIP_EXTENSION", "5.0"))
    extension_threshold = float(os.getenv("EXTENSION_METHOD_THRESHOLD", "2.0"))
    
    if shortfall_seconds > max_extension:
        raise CompositionError(
            f"Shortfall {shortfall_seconds:.2f}s exceeds maximum extension {max_extension}s"
        )
    
    output_path = temp_dir / "last_clip_extended.mp4"
    
    if shortfall_seconds < extension_threshold:
        # Freeze last frame
        logger.info(
            f"Extending last clip by {shortfall_seconds:.2f}s using freeze frame",
            extra={"job_id": str(job_id), "extension_method": "freeze"}
        )
        
        # Get last frame and extend it
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(clip_path),
            "-vf", f"tpad=stop_mode=clone:stop_duration={shortfall_seconds}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-y",
            str(output_path)
        ]
    else:
        # Loop last 1-2 seconds
        logger.info(
            f"Extending last clip by {shortfall_seconds:.2f}s using loop",
            extra={"job_id": str(job_id), "extension_method": "loop"}
        )
        
        # Extract last 2 seconds, loop it to fill shortfall
        loop_duration = min(2.0, shortfall_seconds)
        loops_needed = int(shortfall_seconds / loop_duration) + 1
        
        # Create concat file with original clip + looped segment
        concat_file = temp_dir / "last_clip_extend_concat.txt"
        with open(concat_file, "w") as f:
            f.write(f"file '{clip_path.absolute()}'\n")
            # Extract last segment
            last_segment = temp_dir / "last_segment.mp4"
            extract_cmd = [
                "ffmpeg",
                "-sseof", f"-{loop_duration}",
                "-i", str(clip_path),
                "-t", str(loop_duration),
                "-c", "copy",
                "-y",
                str(last_segment)
            ]
            await run_ffmpeg_command(extract_cmd, job_id=job_id, timeout=300)
            
            # Add looped segment multiple times
            for _ in range(loops_needed):
                f.write(f"file '{last_segment.absolute()}'\n")
        
        # Get original clip duration
        original_duration = await get_video_duration(clip_path)
        target_duration = original_duration + shortfall_seconds
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-t", str(target_duration),
            "-c", "copy",
            "-y",
            str(output_path)
        ]
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    return output_path
```

#### 3. Composer Process (`modules/composer/process.py`)

**Changes:**
- Replace duration handling section (lines 254-280)
- Use cascading compensation instead of per-clip handling
- Update metrics tracking

**Implementation:**
```python
# Step 4: Handle duration mismatches with cascading compensation
await publish_progress(job_id_uuid, "Handling duration mismatches...", 91)
step_start = time.time()

final_clip_paths, duration_metrics = await handle_cascading_durations(
    normalized_paths,
    sorted_clips,
    temp_dir,
    job_id_uuid
)

# Check if final shortfall is acceptable
MAX_SHORTFALL_PERCENTAGE = float(os.getenv("MAX_SHORTFALL_PERCENTAGE", "10.0"))
EXTEND_LAST_CLIP_THRESHOLD = float(os.getenv("EXTEND_LAST_CLIP_THRESHOLD", "20.0"))
FAIL_JOB_THRESHOLD = float(os.getenv("FAIL_JOB_THRESHOLD", "50.0"))

total_intended = sum(c.target_duration for c in sorted_clips)
shortfall_pct = (duration_metrics["total_shortfall"] / total_intended) * 100 if total_intended > 0 else 0.0

if shortfall_pct >= FAIL_JOB_THRESHOLD:
    # Shortfall too large - likely generation failure
    raise CompositionError(
        f"Shortfall too large: {duration_metrics['total_shortfall']:.2f}s ({shortfall_pct:.1f}%) - "
        f"exceeds failure threshold ({FAIL_JOB_THRESHOLD}%)"
    )
elif shortfall_pct >= EXTEND_LAST_CLIP_THRESHOLD:
    # Extend last clip to cover shortfall
    logger.warning(
        f"Large shortfall: {duration_metrics['total_shortfall']:.2f}s ({shortfall_pct:.1f}%) - extending last clip",
        extra={"job_id": str(job_id_uuid)}
    )
    final_clip_paths = await extend_last_clip(
        final_clip_paths[-1],
        duration_metrics["total_shortfall"],
        temp_dir,
        job_id_uuid
    )
elif shortfall_pct >= MAX_SHORTFALL_PERCENTAGE:
    # Log warning but accept
    logger.warning(
        f"Shortfall: {duration_metrics['total_shortfall']:.2f}s ({shortfall_pct:.1f}%) - within tolerance",
        extra={"job_id": str(job_id_uuid)}
    )
```

#### 4. Models (`shared/models/video.py`)

**Changes:**
- Add `compensation_applied` field to `VideoOutput`
- Keep `clips_looped` for backward compatibility (always 0)
- Add `total_shortfall` and `shortfall_percentage` fields
- Store original target duration in compensation metadata (don't modify Clip model)

**Implementation:**
```python
class VideoOutput(BaseModel):
    # ... existing fields ...
    clips_trimmed: int
    clips_looped: int = 0  # Always 0, kept for backward compatibility
    compensation_applied: List[Dict[str, Any]] = []  # NEW
    # Format: [{"clip_index": 1, "original_target": 8.0, "extended_target": 9.5, "compensation": 0.5}]
    total_shortfall: float = 0.0  # NEW
    shortfall_percentage: float = 0.0  # NEW
    # Note: Original target durations stored in compensation_applied metadata, not in Clip model
```

---

## Configuration

### Environment Variables

```bash
# Duration buffer multiplier (default: 1.25 = 25% buffer)
VIDEO_GENERATOR_DURATION_BUFFER=1.25

# Maximum acceptable shortfall percentage (default: 10%)
MAX_SHORTFALL_PERCENTAGE=10.0

# Action on large shortfall: "accept", "extend_last", "fail"
SHORTFALL_ACTION=accept

# Shortfall threshold for extending last clip (default: 20%)
EXTEND_LAST_CLIP_THRESHOLD=20.0

# Shortfall threshold for failing job (default: 50%)
FAIL_JOB_THRESHOLD=50.0

# Feature flag to enable/disable cascading compensation (default: true)
USE_CASCADING_COMPENSATION=true

# Maximum extension for last clip in seconds (default: 5.0)
MAX_LAST_CLIP_EXTENSION=5.0

# Extension method threshold: freeze frame if <2s, loop if >=2s (default: 2.0)
EXTENSION_METHOD_THRESHOLD=2.0
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

1. **Remove Loop Logic**
   - Delete loop code from `duration_handler.py`
   - Update function signatures
   - Update tests

2. **Implement Cascading Function**
   - Create `handle_cascading_durations()` function
   - Implement core algorithm
   - Add unit tests

3. **Update Video Generator**
   - Add buffer calculation
   - Model-specific duration logic
   - Test with various targets

4. **Update Composer Process**
   - Replace duration handling section
   - Integrate cascading function
   - Update metrics tracking

### Phase 2: Testing & Monitoring (Week 2)

1. **Unit Tests**
   - Test cascading algorithm with various scenarios
   - Test edge cases (all clips short, no shortfalls, etc.)
   - Test buffer calculation for all models

2. **Integration Tests**
   - Test full pipeline with known shortfalls
   - Verify final video duration matches audio
   - Test compensation metrics

3. **Add Logging**
   - Log duration statistics per clip
   - Log compensation events
   - Log final shortfall

### Phase 3: Data Collection (Week 3)

1. **Deploy to Staging**
   - Monitor compensation rates
   - Collect duration statistics
   - Track shortfall amounts

2. **Analyze Data**
   - Calculate per-model variance
   - Identify optimal buffer sizes
   - Adjust thresholds if needed

### Phase 4: Optimization (Week 4+)

1. **Per-Model Buffers**
   - Configure optimal buffers per model
   - Update buffer calculation logic

2. **Quality Monitoring**
   - Monitor for quality degradation
   - Alert on quality issues

3. **Beat Alignment** (Optional)
   - Implement beat-aware trimming (trim to nearest beat, not exact duration)
   - Or: Recalculate transitions after compensation
   - Improve transition quality and beat alignment

---

## Testing Strategy

### Unit Tests

1. **Cascading Algorithm Tests**
   - Single clip shortfall (compensated by next)
   - Multiple clip shortfall (cascades through multiple clips)
   - No shortfalls (no compensation needed)
   - All clips short (final shortfall tracked)

2. **Buffer Calculation Tests**
   - Kling models (5s/10s discrete)
   - Veo 3.1 (continuous, capped at 10s)
   - Edge cases (target = 5.0s, target = 10.0s)

3. **Shortfall Handling Tests**
   - Shortfall <10% (accept)
   - Shortfall 10-20% (warning)
   - Shortfall >20% (extend last clip)
   - Shortfall >50% (fail job)

### Integration Tests

1. **Full Pipeline Tests**
   - Generate clips with known shortfalls
   - Verify cascading compensation works
   - Verify final video duration matches audio

2. **Edge Case Tests**
   - All clips too short
   - No shortfalls (perfect match)
   - Single clip shortfall
   - Multiple clip shortfall

### Performance Tests

1. **Duration Handling Time**
   - Should not add >5s to composition time
   - Cascading algorithm should be efficient

---

## Edge Cases & Error Handling

### Edge Case 1: All Clips Too Short

**Scenario:** All clips are shorter than intended, cumulative shortfall persists

**Handling:**
- Track final shortfall percentage (of total intended duration)
- If <10%: Accept (audio sync handles with `-shortest` flag)
- If 10-20%: Log warning, accept (slight quality impact)
- If >20%: Extend last clip using hybrid method:
  - Shortfall <2s: Freeze last frame
  - Shortfall ≥2s: Loop last 1-2 seconds
  - Maximum extension: 5s
- If >50%: Fail job (likely generation failure)
- If extension needed but >5s: Fail job (extension limit exceeded)

### Edge Case 2: No Shortfalls

**Scenario:** All clips are exactly the right length or longer

**Handling:**
- No compensation needed
- Trim clips that are too long
- Normal processing continues

### Edge Case 3: Single Clip Shortfall

**Scenario:** Only first clip is short, all others are long enough

**Handling:**
- Second clip extends to cover shortfall
- Compensation stops after second clip
- Normal processing continues

### Edge Case 4: Model Duration Constraints

**Scenario:** Model only supports discrete durations (5s/10s)

**Handling:**
- **Discrete Models:** Use "maximum buffer" strategy
  - Targets ≤5s: Request 5s (no buffer possible, log warning)
  - Targets >5s: Request 10s (maximum buffer, may exceed 25%)
- **Continuous Models:** Apply percentage buffer (25% default, capped at 10s)
- Document strategy difference clearly
- Accept higher cost for discrete models (targets 5.1-7.5s)

### Edge Case 5: Beat Alignment Impact

**Scenario:** Compensation shifts clip durations, affecting transition timing

**Handling:**
- Accept slight beat misalignment (±100ms tolerance)
- Transitions calculated before compensation (may shift slightly)
- Document that compensation may cause minor beat misalignment
- Future enhancement (Phase 4): Beat-aware trimming or transition recalculation

---

## Success Metrics & Monitoring

### Key Metrics

1. **Compensation Rate**: % of clips that needed compensation
   - Target: <5%
   - Alert: >20%

2. **Final Shortfall**: Total shortfall after all clips
   - Target: <10% of total intended duration
   - Alert: >10%

3. **Job Success Rate**: % of jobs that complete successfully
   - Target: Maintain >90%
   - Alert: <85%

4. **Cost Impact**: Increase in generation costs
   - Target: <20% average across all jobs
   - Accept: Discrete models may have >20% increase for targets 5.1-7.5s (requesting 10s instead of 5s)
   - Monitor: Track per model and per target duration range
   - Report: Actual cost increase in metrics

5. **Quality Issues**: Reports of quality degradation
   - Target: 0 user-reported issues
   - Monitor: Frame similarity (detect freeze frames), motion detection (detect static content)
   - Alert: Any user complaints, compensation rate >20%, quality metrics degrade
   - Track: Jobs with compensation flagged for review

### Logging

**Per-Clip Logging:**
```json
{
  "clip_index": 1,
  "target_duration": 8.0,
  "actual_duration": 7.5,
  "shortfall": 0.5,
  "compensation_applied": 0.5,
  "extended_target": 9.5
}
```

**Final Metrics:**
```json
{
  "total_intended_duration": 24.0,
  "total_actual_duration": 24.0,
  "total_shortfall": 0.0,
  "shortfall_percentage": 0.0,
  "clips_trimmed": 2,
  "compensation_applied": [
    {"clip_index": 1, "compensation": 0.5}
  ]
}
```

---

## Risks & Mitigation

### Risk 1: Quality Degradation in Extended Clips

**Impact:** High - Extended clips may show color shifts or proportion changes

**Mitigation:**
- Monitor quality metrics
- Cap buffer at 10s initially (can increase later)
- Alert on quality issues
- Consider per-model quality thresholds

### Risk 2: Cost Increase

**Impact:** Medium - Requesting longer durations increases costs

**Mitigation:**
- Start with 25% buffer for continuous models, maximum buffer for discrete models
- Monitor cost impact per model and per target duration range
- Track actual cost increase in metrics
- Accept that discrete models may have >20% increase for some targets (5.1-7.5s)
- Adjust buffer strategy based on data if cost impact is too high
- Document cost trade-offs clearly

### Risk 3: Complexity Increase

**Impact:** Medium - Cascading algorithm is more complex than looping

**Mitigation:**
- Comprehensive unit tests
- Clear documentation
- Well-commented code
- Phased rollout with testing

### Risk 4: Edge Cases

**Impact:** Low - Edge cases may cause unexpected behavior

**Mitigation:**
- Comprehensive edge case testing
- Clear error handling
- Fallback strategies
- Monitoring and alerts

---

## Dependencies

### Code Dependencies
- `modules/video_generator/generator.py` - Duration request logic
- `modules/composer/duration_handler.py` - Duration handling
- `modules/composer/process.py` - Main composition flow
- `shared/models/video.py` - Data models

### External Dependencies
- FFmpeg (for trimming clips)
- Video generation models (Kling, Veo 3.1, etc.)

---

## Open Questions

1. **Veo 3.1 Duration Support**: Does Veo support continuous durations or only discrete values?
   - **Action**: Test Veo 3.1 with various durations
   - **Impact**: Affects buffer calculation logic
   - **Decision**: Treat as continuous until proven otherwise, apply 25% buffer

2. **Per-Model Buffer Configuration**: Should we have different buffers per model?
   - **Decision**: Hybrid approach - maximum buffer for discrete models, 25% for continuous
   - **Impact**: Different behavior per model type, but optimal for each
   - **Status**: Implemented in FR1

3. **Beat Alignment**: Should extended durations align to beats?
   - **Decision**: Accept slight misalignment (±100ms) for MVP, defer beat-aware trimming to Phase 4
   - **Impact**: Simpler implementation, acceptable quality
   - **Status**: Documented in Edge Case 5

4. **Extension Method**: Freeze frame vs. loop for last clip extension?
   - **Decision**: Hybrid - freeze <2s, loop ≥2s, max 5s extension
   - **Impact**: Best quality for both short and long extensions
   - **Status**: Implemented in FR5

---

## Appendix

### Algorithm Pseudocode

```
cumulative_shortfall = 0.0
final_clips = []

for each clip in clips:
    target = clip.target_duration
    actual = clip.actual_duration
    
    if first_clip:
        used_duration = actual
        shortfall = max(0, target - actual)
        cumulative_shortfall = shortfall
    else:
        extended_target = target + cumulative_shortfall
        
        if actual >= extended_target:
            used_duration = extended_target  # Trim to extended
            cumulative_shortfall = 0.0  # Reset
        else:
            used_duration = actual  # Use full clip
            remaining_shortfall = extended_target - actual
            cumulative_shortfall = remaining_shortfall
    
    final_clips.append(used_duration)

if cumulative_shortfall > threshold:
    handle_large_shortfall()
```

### Example Scenarios

**Scenario 1: Simple Compensation**
```
Clip 1: target=8.0s, actual=7.5s → used=7.5s, shortfall=0.5s
Clip 2: target=9.0s, actual=10.0s → extended=9.5s, used=9.5s, shortfall=0.0s ✅
Clip 3: target=7.0s, actual=8.0s → used=7.0s, shortfall=0.0s ✅
Total: 7.5 + 9.5 + 7.0 = 24.0s (matches intended 24.0s)
```

**Scenario 2: Cascading Through Multiple Clips**
```
Clip 1: target=8.0s, actual=6.0s → used=6.0s, shortfall=2.0s
Clip 2: target=9.0s, actual=9.5s → extended=11.0s, actual=9.5s → used=9.5s, shortfall=1.5s
Clip 3: target=7.0s, actual=10.0s → extended=8.5s, used=8.5s, shortfall=0.0s ✅
Total: 6.0 + 9.5 + 8.5 = 24.0s (matches intended 24.0s)
```

---

## Approval

**Status:** Ready for Implementation  
**Approved By:** [Pending]  
**Implementation Start Date:** [TBD]  
**Target Completion:** [TBD]

---

## Related Decision Analysis

See `planning/docs/DURATION_COMPENSATION_DECISIONS.md` for detailed analysis of:
- Model duration constraints (discrete vs continuous)
- Beat alignment impact and mitigation
- Extension method selection (freeze vs loop)
- Buffer calculation strategy
- Shortfall threshold rationale
- Cost impact analysis
- Quality monitoring approach
- Integration with transitions
- Feature flag and rollback strategy

