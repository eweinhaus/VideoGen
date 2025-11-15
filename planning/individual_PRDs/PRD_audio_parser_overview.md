# Module 3: Audio Parser - Overview & Integration

**Version:** 2.0 | **Date:** November 15, 2025  
**Priority:** CRITICAL - Foundation for all downstream creative decisions  
**Budget:** 
- **Production/Final Submission:** $200 per minute of video (e.g., 1 min = $200, 2 min = $400), $2000 per job hard limit (allows up to 10 minutes)
- **Development/Testing:** ~$2-5 per video (using cheaper models, ~$1.50/minute with $2 minimum), $50 per job hard limit

**Related PRDs:**
- [Component Specifications](./PRD_audio_parser_components.md) - Detailed technical specs for each component
- [Implementation Guide](./PRD_audio_parser_implementation.md) - Step-by-step implementation instructions

---

## Executive Summary

The Audio Parser performs comprehensive audio analysis to extract beats (±50ms precision), song structure, lyrics, mood, and clip boundaries. It serves as the creative foundation for all downstream modules (Scene Planner, Composer). The module uses Librosa for beat detection, OpenAI Whisper API for lyrics extraction, and rule-based classification for mood. Results are cached by file hash to optimize performance and reduce costs.

**Timeline:** 14-20 hours (2-3 days)  
**Dependencies:** Shared components (complete), API Gateway orchestrator (complete)  
**Blocks:** Scene Planner (Module 4), Composer (Module 8 - needs beat timestamps)

---

## Purpose

The Audio Parser serves as:

1. **Beat Detection Engine**: Extracts precise beat timestamps (±50ms) for video synchronization
2. **Structure Analyzer**: Identifies song sections (intro/verse/chorus/bridge/outro) for narrative planning
3. **Lyrics Extractor**: Extracts lyrics with word-level timestamps for visual context
4. **Mood Classifier**: Determines emotional tone (energetic, calm, dark, bright) for style decisions
5. **Boundary Generator**: Creates initial clip boundaries (4-8s, minimum 3) aligned to beats
6. **Cost Optimizer**: Caches results by file hash to avoid redundant processing

---

## Architecture Overview

```
API Gateway Orchestrator
    ↓
process_audio_analysis(job_id, audio_url)
    ↓
parse_audio() - Core Orchestration
    ├─ Cache Check (Redis by MD5 hash)
    ├─ Download Audio (if not cached)
    ├─ Beat Detection (librosa) → 2% progress
    ├─ Structure Analysis (clustering) → 4% progress
    ├─ Lyrics Extraction (Whisper API) → 6% progress
    ├─ Mood Classification (rules) → 8% progress
    ├─ Clip Boundaries (beat-aligned) → 9% progress
    ├─ Store Results (database + cache) → 10% progress
    └─ Return AudioAnalysis object
```

**Components:**
- **main.py**: Entry point `process_audio_analysis(job_id, audio_url)` - **EXISTS** (fully implemented)
- **parser.py**: Core orchestration `parse_audio(audio_bytes, job_id)` coordinating all steps - **EXISTS** (fully implemented)
- **beat_detection.py**: Librosa-based beat detection with fallback - **EXISTS** (fully implemented)
- **structure_analysis.py**: Clustering + heuristic classification - **EXISTS** (fully implemented)
- **lyrics_extraction.py**: Whisper API integration with retry logic - **EXISTS** (fully implemented)
- **mood_classifier.py**: Rule-based mood classification - **EXISTS** (fully implemented)
- **boundaries.py**: Beat-aligned clip boundary generation - **EXISTS** (fully implemented)
- **cache.py**: Redis caching helpers - **EXISTS** (fully implemented)
- **utils.py**: Utility functions (download, hash calculation, validation) - **EXISTS** (fully implemented)

**Note**: All components are implemented and tested. This PRD serves as the specification for understanding the module's architecture and integration points. See [Component Specifications](./PRD_audio_parser_components.md) for detailed implementation details.

---

## Input/Output Specification

### Input
```python
job_id: UUID  # UUID object (or string that can be converted)
audio_url: str  # Supabase Storage URL (e.g., "https://...supabase.co/storage/v1/object/...")
```

**Input Validation**:
- **Audio Format**: MP3, WAV, FLAC only (validated by API Gateway before upload)
- **File Size**: ≤10MB (validated by API Gateway before upload)
- **Duration**: 10s - 10min (configurable, default: 10s-10min)
- **Sample Rate**: Any (librosa handles resampling to 22050 Hz internally)

### Output
```python
AudioAnalysis(
    job_id: UUID,
    bpm: float,  # 60-200 range
    duration: float,  # seconds
    beat_timestamps: List[float],  # seconds, ±50ms precision
    song_structure: List[SongStructure],  # intro/verse/chorus/bridge/outro
    lyrics: List[Lyric],  # text + timestamp, empty if instrumental
    mood: Mood,  # primary, secondary, energy_level, confidence
    clip_boundaries: List[ClipBoundary],  # start, end, duration (4-8s, min 3)
    metadata: dict  # processing_time, cache_hit, confidences, fallbacks_used
)
```

**Example Output:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "bpm": 128.5,
  "duration": 185.3,
  "beat_timestamps": [0.5, 1.0, 1.5, 2.0, 2.5, ...],
  "song_structure": [
    {"type": "intro", "start": 0.0, "end": 8.5, "energy": "low"},
    {"type": "verse", "start": 8.5, "end": 30.2, "energy": "medium"},
    {"type": "chorus", "start": 30.2, "end": 50.5, "energy": "high"}
  ],
  "lyrics": [
    {"text": "I see the lights", "timestamp": 10.5},
    {"text": "shining bright", "timestamp": 11.2}
  ],
  "mood": {
    "primary": "energetic",
    "secondary": "uplifting",
    "energy_level": "high",
    "confidence": 0.85
  },
  "clip_boundaries": [
    {"start": 0.0, "end": 5.2, "duration": 5.2},
    {"start": 5.2, "end": 10.5, "duration": 5.3}
  ],
  "metadata": {
    "processing_time": 45.2,
    "cache_hit": false,
    "beat_detection_confidence": 0.92,
    "structure_confidence": 0.78,
    "lyrics_confidence": 0.85,
    "fallbacks_used": []
  }
}
```

---

## Integration Points

### 1. Orchestrator Integration

**Location**: `api_gateway/orchestrator.py` (replace lines 174-205, currently has stub that fails)

**Current State**: Orchestrator has stub that fails with "Audio parser module not implemented"

**Required Implementation**:
```python
# Stage 1: Audio Parser (10% progress)
from uuid import UUID

await publish_event(job_id, "stage_update", {
    "stage": "audio_parser",
    "status": "started"
})

if await check_cancellation(job_id):
    await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
    return

try:
    from modules.audio_parser.main import process_audio_analysis
    
    # Convert job_id from str to UUID (audio parser expects UUID)
    job_uuid = UUID(job_id)
    audio_data = await process_audio_analysis(job_uuid, audio_url)
    
    # Store in database (jobs.audio_data JSONB column)
    # Note: Use model_dump() not model_dump_json() for JSONB column
    await db_client.table("jobs").update({
        "audio_data": audio_data.model_dump(),
        "updated_at": "now()"
    }).eq("id", job_id).execute()
    
    await update_progress(job_id, 10, "audio_parser")
    await publish_event(job_id, "stage_update", {
        "stage": "audio_parser",
        "status": "completed"
    })
except Exception as e:
    await handle_pipeline_error(job_id, e)
    raise
```

**Important Notes**:
- **Type Conversion**: `job_id` is a `str` in orchestrator, but `process_audio_analysis()` expects `UUID`. Convert with `UUID(job_id)`.
- **Progress Updates**: Progress updates (2%, 4%, 6%, etc.) are sent by the **orchestrator**, not by the audio parser module. The parser only processes audio and returns results.
- **Error Handling**: Don't catch exceptions in orchestrator - let them propagate so `handle_pipeline_error()` can handle them.
- **Database Storage**: Use `model_dump()` (returns dict) not `model_dump_json()` (returns string) for JSONB column.

**Integration Points**:
- **Input**: `job_id` (str), `audio_url` (str) from orchestrator
- **Output**: `AudioAnalysis` object (Pydantic model)
- **Database**: Store in `jobs.audio_data` JSONB column
- **Progress**: Update via `update_progress()` and `publish_event()` (orchestrator functions)
- **Error Handling**: Raise exceptions (orchestrator handles via `handle_pipeline_error()`)

### 2. Progress Updates

**Important**: Progress updates are sent by the **orchestrator**, not by the audio parser module itself. The parser only processes audio and returns results.

The orchestrator should send SSE events during processing (via `publish_event`):
- **2%**: Beat detection complete → `message: "Beats detected"`
- **4%**: Structure analysis complete → `message: "Structure analyzed"`
- **6%**: Lyrics extraction complete → `message: "Lyrics extracted"`
- **8%**: Mood classification complete → `message: "Mood classified"`
- **9%**: Clip boundaries generated → `message: "Boundaries generated"`
- **10%**: Complete → `stage_update: "completed"`

**Note**: The audio parser module does NOT have access to `publish_event()` or `update_progress()` - these are orchestrator functions. The parser is a pure processing module that returns results.

**Note**: Progress percentages are cumulative completion markers (not time-weighted). Total adds to 10% because this module represents 10% of total pipeline progress (0-10%).

**Important**: These percentages represent component completion, not processing time. For example:
- Lyrics extraction (6%) may take 30s (Whisper API dependent)
- Mood classification (8%) takes <1s (rule-based, very fast)

The percentages indicate "X% of audio parser stage complete" rather than "X% of total processing time elapsed".

### 3. Database Storage

- **Table**: `jobs`
- **Column**: `audio_data` (JSONB) - exists in schema (`supabase/migrations/20251115013200_add_audio_data.sql`)
- **Store**: `audio_data.model_dump()` as JSON (Pydantic model serialization)
- **When**: After successful processing, before returning to orchestrator
- **Storage Strategy**:
  - Store complete `AudioAnalysis` object only after all components succeed
  - If any component fails (after fallbacks): Store partial results in metadata for debugging
  - Storage is blocking (must succeed for pipeline to continue)
  - If storage fails: Log error but don't fail pipeline (orchestrator will handle)
- **Validation**: Input validation happens in two places:
  1. **API Gateway** (`routes/upload.py`): Validates file format (MP3/WAV/FLAC), size (≤10MB), and duration (10s-10min) before upload
  2. **Audio Parser** (`utils.py`): Validates file size again after download (defense in depth)

### 4. Cost Tracking

- **Track**: Whisper API costs only (main cost driver)
- **Cost Calculation**: 
  - Whisper API: $0.006 per minute of audio
  - Calculate: `cost = (duration_seconds / 60.0) * 0.006`
- **When**: After each Whisper API call (on success only, not on retries)
- **Method**: `CostTracker.track_cost(job_id, "audio_parser", "whisper", cost)`
- **Budget Check Strategy**:
  - **Before Whisper API call**: Check budget to prevent wasted API calls
    - Get current total cost: `current_cost = await cost_tracker.get_total_cost(job_id)`
    - Estimate Whisper cost: `estimated_cost = (duration_seconds / 60.0) * 0.006`
    - Check budget: `can_proceed = await cost_tracker.check_budget(job_id, estimated_cost, limit)`
    - If budget exceeded: Raise `BudgetExceededError` (stops pipeline immediately)
  - **Note**: Budget check happens only before the expensive Whisper API call. Other components (beat detection, structure analysis) are local operations with no API costs, so budget checks are not needed for them.

---

## Error Handling

### Component-Level Failures

Each component has fallback strategy (see [Component Specifications](./PRD_audio_parser_components.md) for details):
- **Beat Detection**: Falls back to tempo-based boundaries
- **Structure Analysis**: Falls back to uniform segmentation
- **Lyrics Extraction**: Falls back to empty array (instrumental)
- **Mood Classification**: Falls back to default mood
- **Clip Boundaries**: Uses fallback beats if available

### Module-Level Failures

Module fails only if:
- **Critical failure**: Both beat detection AND structure analysis fail (after fallbacks)
  - Beat detection fails → Uses tempo-based fallback (always succeeds)
  - Structure analysis fails → Uses uniform segmentation fallback (always succeeds)
  - **Module fails only if**: Both fallbacks also fail (extremely rare, indicates corrupted audio)
- **Budget exceeded**: Cost exceeds limit before Whisper API call (checked pre-flight)
  - Budget check happens before expensive operations only
  - If budget exceeded: Raise `BudgetExceededError` immediately (stops pipeline)
- **Cancellation**: Job cancelled by user (checked by orchestrator before each stage)
- **Storage error**: Cannot download audio file (after retries in `download_audio_file()`)
  - Storage download has its own retry logic
  - If download fails after retries: Module fails with `AudioAnalysisError`

**Error Decision Tree**:
```
Beat Detection:
  - Exception raised → Use fallback (tempo-based beats, always succeeds)
  - Confidence <0.6 → Use fallback (tempo-based beats)
  - No beats found → Use fallback (tempo-based beats)
  - Fallback always succeeds (generates beats from tempo)
  - Module fails only if: Both detection AND fallback fail (corrupted audio)

Structure Analysis:
  - Clustering exception → Use fallback (uniform segmentation, always succeeds)
  - <3 segments after merging → Use fallback (uniform segmentation)
  - Fallback always succeeds (creates 8 equal segments)
  - Module fails only if: Both clustering AND fallback fail (corrupted audio)

Lyrics Extraction:
  - Whisper API exception → Retry 3x (exponential backoff, @retry_with_backoff supports async)
  - After 3 retries → Use fallback (empty lyrics array)
  - Fallback always succeeds (instrumental tracks are valid)
  - Budget exceeded → Raise BudgetExceededError (stops pipeline)

Mood Classification:
  - Feature extraction fails → Use fallback (default mood: "energetic", confidence 0.5)
  - All scores <0.3 → Use fallback (default mood)
  - Fallback always succeeds

Clip Boundaries:
  - Uses beat detection results (or fallback beats from tempo)
  - Always succeeds (minimum 3 clips guaranteed, even for very short songs)
  - Edge cases handled: <12s songs, variable tempo, no beats detected
```

**Error Types**:
- `AudioAnalysisError`: Audio processing failures (add to `shared/errors.py`)
- `BudgetExceededError`: Cost limit exceeded (already exists in `shared/errors.py`)
- `RetryableError`: Whisper API failures (retryable, already exists in `shared/errors.py`)
- `ValidationError`: Input validation errors (already exists in `shared/errors.py`)

---

## Success Criteria

### Functional
✅ Process audio files successfully (MP3/WAV/FLAC)  
✅ Return `AudioAnalysis` object with all required fields  
✅ Results stored in database (`jobs.audio_data`)  
✅ Cache works (check before processing)  
✅ Costs tracked correctly (Whisper API)

### Quality
✅ Beat detection: ±50ms precision, 90%+ accuracy  
✅ BPM: ±2 for 80%+ songs  
✅ Structure: 70%+ accuracy  
✅ Lyrics: >70% accurate (or empty for instrumental)  
✅ Clip boundaries: 4-8s, minimum 3 clips

### Performance
✅ <60s processing time for 3-minute song (with 10-15s buffer for download/cache/overhead)  
✅ Cache hit: <1s  
✅ Memory efficient (no OOM for long songs)
**Breakdown**:
- Beat detection: <10s
- Structure analysis: <15s
- Lyrics extraction: <30s (Whisper API dependent)
- Mood classification: <1s
- Boundaries: <1s
- Download/cache/overhead: ~10-15s
- **Total**: ~57-67s (within 60s target with buffer)

### Integration
✅ Orchestrator calls successfully  
✅ Progress updates visible in frontend  
✅ Errors handled gracefully  
✅ Pipeline continues to Scene Planner

---

## Boundary Ownership Clarification

**Audio Parser Responsibilities**:
- Generate initial clip boundaries (beat-aligned, 4-8s, minimum 3)
- Boundaries are suggestions for Scene Planner
- Boundaries must align to beats (±50ms tolerance)

**Scene Planner Responsibilities**:
- Can refine boundaries ±2s for narrative needs (per main PRD)
- Must stay within ±2s of Audio Parser's beat-aligned boundaries
- Final boundaries used by Composer (not Audio Parser's original)

**Composer Responsibilities**:
- Uses Scene Planner's refined boundaries (not Audio Parser's original)
- Applies transitions at boundary points
- Syncs audio to video using beat timestamps from Audio Parser

---

## Clarifications & Common Questions

### Current Implementation Status

**All components are fully implemented and tested.** The audio parser module exists in `project/backend/modules/audio_parser/` with all components complete. The orchestrator currently has a stub that needs to be replaced with the actual integration code (see [Orchestrator Integration](#1-orchestrator-integration) section).

### Cache-Before-Download Optimization

The cache optimization attempts to extract a file hash from the Supabase Storage URL before downloading. **Note**: Supabase Storage URLs typically don't include file hashes, so `extract_hash_from_url()` will return `None` in most cases. This is expected behavior:
1. Try to extract hash from URL → Usually returns `None`
2. Download audio file
3. Calculate hash from file bytes
4. Check cache with calculated hash
5. Process if cache miss

This optimization saves bandwidth/time only when the hash is available in the URL (rare), but the implementation gracefully handles the common case (hash not in URL).

### Progress Percentages

Progress percentages (2%, 4%, 6%, 8%, 9%, 10%) represent **component completion**, not processing time. For example:
- Lyrics extraction (6%) may take 30 seconds (Whisper API dependent)
- Mood classification (8%) takes <1 second (rule-based, very fast)

These percentages indicate "X% of audio parser stage complete" rather than "X% of total processing time elapsed".

### Budget Check Timing

Budget checks happen **only before expensive operations** (Whisper API call). Local operations (beat detection, structure analysis) don't require budget checks since they have no API costs. If budget is exceeded before the Whisper API call, the pipeline stops immediately with `BudgetExceededError`.

### Module Failure Criteria

The module fails only in extreme cases:
- **Both beat detection AND structure analysis fail** (after fallbacks) - Extremely rare, indicates corrupted audio
- **Budget exceeded** - Checked before Whisper API call
- **Storage download fails** - After retries in `download_audio_file()`
- **Job cancelled** - Checked by orchestrator

All components have fallback strategies that almost always succeed, making module-level failures very rare.

---

**Document Status:** Ready for Implementation  
**Next Steps:** 
1. Review [Component Specifications](./PRD_audio_parser_components.md) for detailed implementation
2. Follow [Implementation Guide](./PRD_audio_parser_implementation.md) for step-by-step instructions
3. Replace orchestrator stub with actual integration code

