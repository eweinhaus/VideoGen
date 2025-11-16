# Module 8: Composer - Overview

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** 
- Video Generator (Module 7) - ✅ Complete
- Audio Parser (Module 3) - ✅ Complete
- Scene Planner (Module 4) - ✅ Complete

**Related Documents:**
- `PRD_composer_implementation_part1.md` - Steps 1-4: Validation, download, normalize, duration handling
- `PRD_composer_implementation_part2.md` - Steps 5-8: Transitions, sync, encode, upload, main function
- `PRD_composer_operations.md` - Error handling, optimizations, and edge cases

---

## Executive Summary

The Composer module (Module 8) is the final stage of the video generation pipeline. It stitches video clips together with beat-aligned transitions, syncs the original audio, and produces a professional-quality final MP4 video. The module prioritizes reliability and simplicity for MVP, with optimizations deferred to post-MVP phases.

**Key Metrics:**
- **Composition Time:** <90s for 3-minute video
- **Audio Sync:** ±100ms tolerance
- **Output Quality:** 1080p (1920x1080), 30 FPS, H.264/AAC
- **Success Rate:** 90%+ (with retry logic)
- **Cost:** $0.00 (no API calls, compute only)

---

## Objectives

1. **Stitch Video Clips:** Combine multiple video clips into single cohesive video
2. **Handle Duration Mismatches:** Trim clips if too long, loop if too short
3. **Apply Transitions:** Beat-aligned transitions between clips (cut, crossfade, fade)
4. **Sync Audio:** Perfect audio-video synchronization (±100ms tolerance)
5. **Normalize Quality:** Upscale all clips to 1080p, normalize to 30 FPS
6. **Produce Final Output:** Generate MP4 with H.264 video and AAC audio (5000k bitrate)

---

## System Architecture

### Module Position in Pipeline

```
[3] Audio Parser → [4] Scene Planner → [5] Reference Generator → [6] Prompt Generator
                                                                         ↓
[8] Composer ← [7] Video Generator (clips) ← [6] Prompt Generator
    ↓
Final Video (MP4)
```

### Data Flow

```
Input: Clips (from Video Generator)
  ↓
Download clips and audio from Supabase Storage (parallel)
  ↓
Normalize all clips to 1080p, 30 FPS
  ↓
Handle duration mismatches (trim/loop)
  ↓
Apply transitions at clip boundaries
  ↓
Sync original audio
  ↓
Encode final MP4 (H.264, AAC, 5000k bitrate)
  ↓
Upload to Supabase Storage
  ↓
Output: VideoOutput (final video URL, metadata)
```

### Key Components

1. **File Downloader:** Downloads clips and audio from Supabase Storage (parallel)
2. **Clip Normalizer:** Upscales clips to 1080p, normalizes to 30 FPS
3. **Duration Handler:** Trims clips if too long, loops if too short
4. **Transition Applier:** Applies transitions (cut, crossfade, fade) at clip boundaries
5. **Audio Syncer:** Syncs original audio with video (±100ms tolerance)
6. **Video Encoder:** Encodes final MP4 with H.264/AAC
7. **Storage Uploader:** Uploads final video to Supabase Storage

---

## Inputs

### Function Signature

```python
async def process(
    job_id: str,                               # Job ID (string from orchestrator, converted to UUID internally)
    clips: Clips,                              # From Video Generator
    audio_url: str,                            # Original audio file URL
    transitions: List[Transition],             # From Scene Planner
    beat_timestamps: Optional[List[float]] = None  # From Audio Parser (optional for MVP)
) -> VideoOutput
```

**Note:** The orchestrator passes `job_id` as a string. The function should convert it to UUID internally for type safety and consistency with models.

### Input Details

**1. `job_id: str`**
- Job identifier (string from orchestrator, converted to UUID internally)
- Used for temp directory naming and storage paths
- **Note:** Function accepts string but converts to UUID for internal use

**2. `clips: Clips`**
- Collection of generated video clips from Video Generator
- Structure:
  ```python
  class Clips(BaseModel):
      job_id: UUID
      clips: List[Clip]  # Must have ≥3 clips
      total_clips: int
      successful_clips: int
      failed_clips: int
      total_cost: Decimal
      total_generation_time: float
  ```
- Each `Clip` contains:
  - `clip_index: int` - Order in sequence (0, 1, 2, ...)
  - `video_url: str` - Supabase Storage URL
  - `actual_duration: float` - Actual clip duration in seconds
  - `target_duration: float` - Target duration in seconds
  - `duration_diff: float` - Difference between actual and target
  - `status: Literal["success", "failed"]` - Clip status
  - `cost: Decimal` - Generation cost
  - `generation_time: float` - Generation time

**3. `audio_url: str`**
- Original audio file URL from Supabase Storage
- Format: `https://project.supabase.co/storage/v1/object/public/audio-uploads/{job_id}/audio.mp3`
- Used for final video audio track

**4. `transitions: List[Transition]`**
- Transition definitions from Scene Planner
- Structure:
  ```python
  class Transition(BaseModel):
      from_clip: int      # Source clip index
      to_clip: int        # Destination clip index
      type: Literal["cut", "crossfade", "fade"]
      duration: float     # Transition duration in seconds
      rationale: str        # Why this transition was chosen
  ```
- **MVP Simplification:** In MVP, transitions list is ignored. Clips are simply concatenated in order (cuts only). Transition definitions are validated but not used for actual transitions until post-MVP.

**5. `beat_timestamps: Optional[List[float]]`**
- Beat timestamps from Audio Parser (optional for MVP)
- Format: `[0.5, 1.0, 1.5, 2.0, ...]` (seconds)
- Used for beat-aligned transitions (post-MVP)
- **MVP Simplification:** Not used in MVP. Clips already beat-aligned, transitions at clip boundaries. Pass `None` if unavailable.

---

## Outputs

### VideoOutput Model

```python
class VideoOutput(BaseModel):
    job_id: UUID
    video_url: str                    # Final video URL in Supabase Storage
    duration: float                   # Final video duration in seconds
    audio_duration: float             # Original audio duration in seconds
    sync_drift: float                 # Audio sync drift in seconds (should be <0.1s)
    clips_used: int                   # Number of clips used in final video
    clips_trimmed: int                # Number of clips that were trimmed
    clips_looped: int                 # Number of clips that were looped
    transitions_applied: int          # Number of transitions applied
    file_size_mb: float               # Final file size in megabytes
    composition_time: float           # Total composition time in seconds
    cost: Decimal                     # Always $0.00 (no API calls)
    status: Literal["success", "failed"]
```

### Output Example

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "video_url": "https://project.supabase.co/storage/v1/object/public/video-outputs/550e8400-e29b-41d4-a716-446655440000/final_video.mp4",
  "duration": 185.3,
  "audio_duration": 185.3,
  "sync_drift": 0.05,
  "clips_used": 6,
  "clips_trimmed": 4,
  "clips_looped": 2,
  "transitions_applied": 5,
  "file_size_mb": 45.2,
  "composition_time": 60.5,
  "cost": "0.00",
  "status": "success"
}
```

---

## Success Criteria

### Functional Requirements
- ✅ Stitches all clips into single video
- ✅ Minimum 3 clips required (fail if <3)
- ✅ Handles duration mismatches (trim/loop)
- ✅ Applies transitions at clip boundaries
- ✅ Syncs audio perfectly (±100ms tolerance)
- ✅ Produces valid MP4 output
- ✅ Uploads final video to Supabase Storage

### Quality Requirements
- ✅ 1080p resolution (1920x1080)
- ✅ 30 FPS frame rate
- ✅ H.264 video codec
- ✅ AAC audio codec
- ✅ 5000k video bitrate
- ✅ Audio sync drift <100ms
- ✅ Professional quality (no artifacts, smooth playback)

### Performance Requirements
- ✅ Composition time <90s for 3-minute video
- ✅ Parallel clip downloads (6 clips in ~2s vs 12s sequential)
- ✅ Progress events published during composition
- ✅ Efficient memory usage (<500MB for 6 clips)

### Reliability Requirements
- ✅ 90%+ success rate
- ✅ Retry logic for transient failures (FFmpeg, network)
- ✅ Graceful error handling with clear messages
- ✅ Input validation before expensive operations
- ✅ Output validation before uploading

---

## Dependencies & Prerequisites

### System Dependencies
- **FFmpeg:** Must be installed and available in PATH
  - Check: `ffmpeg -version`
  - Installation:
    - macOS: `brew install ffmpeg`
    - Linux: `apt-get install ffmpeg` or `yum install ffmpeg`
    - Windows: Download from https://ffmpeg.org/

### Python Dependencies
- `shared.storage.StorageClient` - Supabase Storage operations
- `shared.errors.CompositionError` - Error handling ✅ Already exists
- `shared.logging.get_logger` - Structured logging
- `shared.retry.retry_with_backoff` - Retry logic

### Reusable Utilities
- `modules.video_generator.image_handler.parse_supabase_url()` - URL parsing
- `modules.video_generator.generator.get_video_duration()` - Duration extraction (reuse pattern)
- **Note:** Create composer-specific utilities in `composer/utils.py` that reuse these patterns

### Storage Buckets
- `video-clips` - Input clips from Video Generator (read)
- `video-outputs` - Final composed videos (write)
- `audio-uploads` - Original audio files (read)

### Infrastructure
- Supabase Storage configured and accessible
- Sufficient disk space for temp files (~500MB for 3-minute video)
- Network access to Supabase Storage

---

## MVP Simplifications

### Phase 1: Core MVP (Must Have)
1. **Cuts Only:** Start with simple cuts (0s transitions), no crossfades/fades
2. **Exact Duration Trimming:** Trim to exact `target_duration`, ignore beat alignment
3. **Simple Audio Sync:** Use `-shortest` flag, report drift (don't adjust)
4. **Simple Looping:** Repeat entire clip N times (no seamless loop detection)
5. **Multi-Step FFmpeg:** Separate commands for each step (easier debugging)

### Phase 2: Duration Handling (Should Have)
1. Trim clips if too long (exact duration)
2. Loop clips if too short (simple repetition)
3. Validate minimum 3 clips

### Phase 3: Transitions (Nice to Have)
1. Add crossfade transitions
2. Add fade transitions (if time permits)

### Post-MVP Enhancements
1. Beat alignment for trimming
2. Audio sync adjustment (if drift >100ms)
3. Seamless looping
4. Single FFmpeg command optimization
5. Memory optimization

---

## Integration Points

### Orchestrator Integration

**Function Call:**
```python
from modules.composer.process import process as compose_video

video_output = await compose_video(
    job_id=job_id,  # String from orchestrator
    clips=clips,
    audio_url=audio_url,
    transitions=plan.transitions,
    beat_timestamps=audio_data.beat_timestamps if hasattr(audio_data, 'beat_timestamps') else None
)
```

**Note:** The orchestrator passes `job_id` as a string. The composer function converts it to UUID internally. The `beat_timestamps` parameter is optional and may be `None` if not available.

**Progress Updates:**
- Orchestrator handles stage start/complete events
- Composer can publish progress messages:
  - "Downloading clips (3/6)..."
  - "Normalizing clips..."
  - "Applying transitions..."
  - "Syncing audio..."
  - "Uploading final video..."

**Error Handling:**
- Raise `CompositionError` for permanent failures
- Raise `RetryableError` for transient failures (network, FFmpeg)
- Orchestrator handles error propagation and SSE events

**Progress Publishing:**
- Composer publishes progress messages at each major step:
  - "Checking FFmpeg availability..."
  - "Downloading clips (3/6)..."
  - "Normalizing clips..."
  - "Handling duration mismatches..."
  - "Applying transitions..."
  - "Syncing audio..."
  - "Encoding final video..."
  - "Uploading final video..."
- Progress events sent via `api_gateway.services.sse_manager.publish_event()`

---

## Technical Constraints

### Performance Constraints
- **Composition Time:** <90s for 3-minute video
- **Download Time:** <5s for 6 clips (parallel)
- **Normalization Time:** <30s for 6 clips
- **Encoding Time:** <45s for 3-minute video

### Quality Constraints
- **Resolution:** 1080p (1920x1080) minimum
- **Frame Rate:** 30 FPS
- **Audio Sync:** ±100ms tolerance
- **Video Codec:** H.264
- **Audio Codec:** AAC
- **Video Bitrate:** 5000k

### Resource Constraints
- **Memory:** <500MB for 6 clips
- **Disk Space:** ~500MB temp files for 3-minute video
- **Network:** Download 6 clips + 1 audio file (~300MB total)

### Reliability Constraints
- **Success Rate:** 90%+ with retry logic
- **Retry Attempts:** 2 attempts for FFmpeg operations
- **Timeout:** 300s (5 minutes) per FFmpeg command
- **Minimum Clips:** 3 clips required (fail if <3)

---

## Next Steps

1. **Review Implementation PRDs:** 
   - `PRD_composer_implementation_part1.md` (Steps 1-4)
   - `PRD_composer_implementation_part2.md` (Steps 5-8)
2. **Review Operations PRD:** `PRD_composer_operations.md`
3. **Create Error Type:** ✅ `CompositionError` already exists in `shared/errors.py`
4. **Verify Dependencies:** Check FFmpeg installation, storage buckets
5. **Start Implementation:** Begin with Phase 1 (Core MVP)
   - Create shared FFmpeg utility function in `utils.py`
   - Integrate temp directory context manager
   - Add progress publishing to main flow

---

**Document Status:** Ready for Implementation  
**Total Estimated Time:** 8-12 hours for MVP  
**Next Action:** Review Implementation PRD, then begin Phase 1

