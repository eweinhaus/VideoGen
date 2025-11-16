# Module 8: Composer - Operations

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** PRD_composer_overview.md, PRD_composer_implementation_part1.md, PRD_composer_implementation_part2.md

---

## Operations Overview

This document covers error handling, optimizations, edge cases, and operational considerations for the Composer module.

---

## Error Handling

### Error Types

**1. CompositionError (Permanent Failures)**
- Invalid input (missing clips, invalid URLs)
- FFmpeg errors (codec issues, invalid format)
- Output validation failures (file too small, wrong resolution)
- Minimum clips not met (<3 clips)

**2. RetryableError (Transient Failures)**
- Network errors (download failures)
- FFmpeg timeouts (system load, disk I/O)
- Storage upload failures (temporary service issues)

### Error Handling Pattern

```python
from shared.errors import CompositionError, RetryableError

# Permanent failures (don't retry)
if len(clips.clips) < 3:
    raise CompositionError("Minimum 3 clips required")

# Transient failures (will retry)
try:
    clip_bytes = await storage.download_file(bucket, path)
except Exception as e:
    raise RetryableError(f"Failed to download clip: {e}") from e
```

### FFmpeg Error Handling

**Note:** FFmpeg error handling is implemented in `composer/utils.py` as `run_ffmpeg_command()`. All FFmpeg errors are treated as retryable (system load, disk I/O, timeouts) and will be retried with exponential backoff. After max attempts, a `CompositionError` is raised.

**Simplified Approach:** Instead of trying to classify FFmpeg errors as retryable vs permanent, we treat all FFmpeg errors as retryable. This is simpler and more reliable, as most FFmpeg failures are transient (disk I/O, system load, etc.).

See `PRD_composer_implementation_part2.md` for the complete `run_ffmpeg_command()` implementation.

---

## Fallback Strategies

### 1. Transition Failures

**Scenario:** Transition application fails (e.g., xfade filter error).

**Fallback:** Use simple cut (concatenation without transition).

```python
try:
    # Try to apply crossfade transition
    output_path = await apply_crossfade_transition(...)
except CompositionError:
    logger.warning("Crossfade failed, using simple cut")
    output_path = await apply_simple_cut(...)
```

**MVP Note:** MVP uses cuts only, so this fallback isn't needed initially.

---

### 2. Duration Mismatch >1s

**Scenario:** Video duration doesn't match audio duration by >1s.

**Fallback:** Adjust video speed slightly (±5%).

```python
if abs(video_duration - audio_duration) > 1.0:
    logger.warning(
        f"Large duration mismatch ({abs(video_duration - audio_duration):.2f}s), adjusting speed"
    )
    # Adjust video speed to match audio
    output_path = await adjust_video_speed(video_path, audio_duration, temp_dir)
```

**MVP Note:** MVP uses `-shortest` flag which handles this automatically.

---

### 3. <3 Clips Available

**Scenario:** Less than 3 clips available (some failed during generation).

**Action:** Fail job immediately (no fallback).

```python
if len(clips.clips) < 3:
    raise CompositionError("Minimum 3 clips required for composition")
```

**Rationale:** PRD requirement, no fallback possible.

---

### 4. FFmpeg Errors

**Scenario:** FFmpeg command fails (codec error, invalid format, etc.).

**Fallback:** Retry once, then fail with detailed error message.

```python
@retry_with_backoff(max_attempts=2, base_delay=2)
async def run_ffmpeg_command(...):
    # Retry logic handles transient failures
    # Permanent failures raise CompositionError with detailed message
    pass
```

---

## Optimizations

### 1. Parallel Clip Downloads

**Implementation:** Already covered in Implementation PRD.

**Impact:** 6 clips × 2s = 12s → 2s (10s savings)

---

### 2. Temporary File Cleanup

**Implementation:** Use context manager for guaranteed cleanup.

```python
import tempfile
import shutil
from contextlib import asynccontextmanager

@asynccontextmanager
async def temp_directory(prefix: str):
    """Context manager for temporary directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# Usage
async with temp_directory(f"composer_{job_id}_") as temp_dir:
    # ... work with temp files ...
    pass
# Automatically cleaned up
```

**Impact:** Prevents disk space leaks.

---

### 3. FFmpeg Threading

**Implementation:** Use `-threads` flag for faster processing.

```python
ffmpeg_cmd = [
    "ffmpeg",
    "-threads", "4",  # Use 4 threads
    # ... other args ...
]
```

**Impact:** 20-30% faster encoding on multi-core systems.

---

### 4. Skip Unnecessary Operations

**Implementation:** Check clip properties before normalization.

```python
async def should_normalize_clip(clip_path: Path) -> bool:
    """Check if clip needs normalization."""
    video_info = await get_video_info(clip_path)
    return not (
        video_info["width"] == 1920 and
        video_info["height"] == 1080 and
        video_info["fps"] == 30
    )
```

**Impact:** Saves time if clips are already correct format (unlikely but possible).

**Recommendation:** Keep simple for MVP (always normalize), optimize later.

---

### 5. Progress Tracking

**Implementation:** ✅ Integrated into main process flow in `PRD_composer_implementation_part2.md`.

Progress events are published at each major step:
- "Downloading clips (N clips)..."
- "Normalizing clips to 1080p, 30fps..."
- "Handling duration mismatches..."
- "Applying transitions..."
- "Syncing audio with video..."
- "Encoding final video..."
- "Uploading final video..."

**Impact:** Better UX, transparency during 60-90s composition.

---

### 6. Composition Time Tracking

**Implementation:** Track time for each step.

```python
timings = {
    "download_clips": 0.0,
    "normalize_clips": 0.0,
    "apply_transitions": 0.0,
    "sync_audio": 0.0,
    "upload_final": 0.0,
    "total": 0.0
}

start = time.time()
clip_bytes_list = await download_all_clips(...)
timings["download_clips"] = time.time() - start

# Log timings for optimization
logger.info(
    f"Composition timings: {timings}",
    extra={"job_id": str(job_id), "timings": timings}
)
```

**Impact:** Performance optimization, identify bottlenecks.

---

### 7. FFmpeg Command Logging

**Implementation:** Log FFmpeg commands for debugging.

```python
logger.info(
    f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}",
    extra={"job_id": str(job_id), "command": ffmpeg_cmd}
)
```

**Impact:** Easier debugging, can copy-paste commands to test manually.

---

### 8. Output Validation

**Implementation:** Validate FFmpeg output before uploading.

```python
def validate_output(output_path: Path) -> None:
    """Validate FFmpeg output file."""
    if not output_path.exists():
        raise CompositionError("FFmpeg output file not created")
    
    output_size = output_path.stat().st_size
    if output_size < 1024:  # Less than 1KB is suspicious
        raise CompositionError(f"FFmpeg output file too small: {output_size} bytes")
    
    # Validate video properties
    video_info = await get_video_info(output_path)
    if video_info["width"] != 1920 or video_info["height"] != 1080:
        logger.warning(
            f"Output resolution mismatch: {video_info['width']}x{video_info['height']}",
            extra={"job_id": str(job_id)}
        )
```

**Impact:** Early detection of FFmpeg failures, prevents uploading invalid files.

---

## Edge Cases

### Edge Cases Summary

1. **Empty Clips:** Raise `CompositionError("No clips provided")` (handled in Step 1)
2. **Missing Video URLs:** Validate all clips have `video_url`, raise error if missing (handled in Step 1)
3. **Invalid Audio URL:** Validate format with `parse_supabase_url()`, raise error if invalid (handled in Step 1)
4. **FFmpeg Not Installed:** Check with `check_ffmpeg_available()`, raise error with installation instructions (handled in Step 1)
5. **Non-Sequential Clip Indices:** Validate indices are 0, 1, 2, ..., raise error if gaps (handled in Step 1)
6. **File Size Validation:** Validate downloads are >1KB, warn if >200MB (handled in Step 2)
7. **Disk Space:** Check available space (500MB required), fail fast if insufficient (handled via temp directory context manager)
8. **Large Clips:** Log warning if >50MB, continue processing (handled in Step 2)
9. **Invalid Durations:** Validate duration >0, raise error if invalid (handled in Step 4)
10. **Invalid Transitions:** In MVP, transitions are ignored. Post-MVP: skip transitions with invalid clip indices, log warning
11. **Job ID Type:** Orchestrator passes string, function converts to UUID internally (handled in main function)
12. **Audio Format:** FFmpeg handles multiple formats (MP3, WAV, M4A, etc.), no conversion needed

---

## Testing Considerations

### Unit Tests

1. **Input Validation:**
   - Test minimum clips requirement
   - Test missing video URLs
   - Test invalid audio URL

2. **Duration Handling:**
   - Test trim logic (too long)
   - Test loop logic (too short)
   - Test exact match (no action needed)

3. **Error Handling:**
   - Test FFmpeg failures
   - Test download failures
   - Test upload failures

### Integration Tests
- End-to-end with real clips (3, 6, 10 clips, 30s-5min durations)
- Error scenarios: <3 clips, invalid URLs, FFmpeg unavailable

### Performance Tests
- Timing: <90s for 3-minute video, ~2s for 6 clips (parallel downloads)
- Resources: <500MB memory, ~500MB disk space

---

## Monitoring & Logging

### Key Metrics to Log
- Composition time (total + per-step breakdown)
- File sizes (clips, final video)
- Duration stats (clips trimmed, looped)
- Sync drift measurement
- Error rates (FFmpeg failures, download failures)

**Log Format:** Use structured logging with `job_id`, `composition_time`, `file_size_mb`, `sync_drift`, `clips_trimmed`, `clips_looped` in `extra` dict.

---

## Deployment Considerations

**FFmpeg:** Add to Docker/system packages (production), document installation (dev), verify at startup

**Storage:** Verify buckets exist (`video-clips`, `video-outputs`, `audio-uploads`)

**Resources:** Ensure ~300MB memory, ~500MB disk space for temp files, cleanup after composition

---

## Post-MVP Enhancements

1. **Beat Alignment:** Trim clips to nearest beat timestamp (find_nearest_beat function)
2. **Audio Sync Adjustment:** Adjust video speed if sync drift >100ms (FFmpeg setpts filter)
3. **Seamless Looping:** Detect loop point using frame similarity (FFmpeg/OpenCV)
4. **Crossfade Transitions:** Add xfade filter for smooth transitions
5. **Single FFmpeg Command:** Combine all operations (faster but harder to debug)

---

## Checklist

- [x] Error types defined (`CompositionError` in `shared/errors.py`) ✅ Already exists
- [ ] FFmpeg availability check implemented (Step 1)
- [ ] Shared FFmpeg utility function (`run_ffmpeg_command` in `utils.py`)
- [ ] Input validation implemented (Step 1, includes sequential clip index validation)
- [ ] Parallel downloads implemented (Step 2)
- [ ] Temp directory cleanup implemented (context manager in main process)
- [ ] Progress events implemented (integrated into main flow)
- [ ] FFmpeg command logging implemented (in `run_ffmpeg_command`)
- [ ] Output validation implemented (after each major step)
- [ ] File size validation (downloads, outputs)
- [ ] Edge cases handled
- [ ] Unit tests written
- [ ] Integration tests written
- [ ] Performance tests written
- [ ] Documentation complete

---

**Next Steps:**
1. Review all three PRDs
2. Create error type (`CompositionError`)
3. Start implementation with Phase 1 (Core MVP)
4. Add Phase 2 features if time permits

