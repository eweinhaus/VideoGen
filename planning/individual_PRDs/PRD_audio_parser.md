# Module 3: Audio Parser - Product Requirements Document

**Version:** 2.0 | **Date:** November 15, 2025 | **Updated:** Split into 3 focused PRDs  
**Priority:** CRITICAL - Foundation for all downstream creative decisions  
**Budget:** 
- **Production/Final Submission:** $200 per video, $2000 per job hard limit
- **Development/Testing:** ~$2-5 per video (using cheaper models), $50 per job hard limit

---

## PRD Split Notice

This PRD has been **split into 3 focused documents** for better organization and implementation clarity:

1. **[Overview & Integration](./PRD_audio_parser_overview.md)** (~250 lines)
   - Executive summary, purpose, architecture
   - Input/Output specification
   - Integration points (orchestrator, database, cost tracking, progress updates)
   - Error handling strategy
   - Success criteria
   - Boundary ownership

2. **[Component Specifications](./PRD_audio_parser_components.md)** (~350 lines)
   - Detailed technical specs for all 6 components
   - Algorithm details, fallback strategies, edge cases
   - Code examples and pseudocode
   - Performance targets per component

3. **[Implementation Guide](./PRD_audio_parser_implementation.md)** (~250 lines)
   - Step-by-step implementation phases
   - Testing requirements (unit, integration, E2E, manual)
   - Dependencies and setup
   - Code patterns and examples
   - Implementation checklist

**This document is kept for reference but all active development should use the 3 split PRDs above.**

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
- **main.py**: Entry point `process_audio_analysis(job_id, audio_url)` - **EXISTS** (needs implementation)
- **parser.py**: Core orchestration `parse_audio(audio_bytes, job_id)` coordinating all steps
- **beat_detection.py**: Librosa-based beat detection with fallback
- **structure_analysis.py**: Clustering + heuristic classification - **EXISTS** (needs review/update)
- **lyrics_extraction.py**: Whisper API integration with retry logic
- **mood_classifier.py**: Rule-based mood classification
- **boundaries.py**: Beat-aligned clip boundary generation
- **cache.py**: Redis caching helpers
- **utils.py**: Utility functions (download, hash calculation, validation) - **EXISTS** (needs review/update)

**Note**: Some files exist from previous implementation but need to be reviewed/updated to match this PRD specification.

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

## Component Specifications

### 1. Beat Detection (`beat_detection.py`)

**Purpose**: Extract BPM and precise beat timestamps for video synchronization.

**Algorithm**: Librosa only (simple, reliable for MVP)
- Use `librosa.beat.beat_track()` with default parameters
- Extract tempo using `librosa.beat.tempo()`
- Validate BPM in 60-200 range
- Return beat timestamps as list of floats (seconds)

**Fallback Strategy**:
- If beat detection fails or confidence <0.6:
  - Use tempo-based boundaries (4-beat intervals)
  - Calculate beat interval: `60.0 / bpm`
  - Generate beats: `[0.0, interval, 2*interval, ...]`
  - Set confidence to 0.5
  - Flag in metadata: `fallbacks_used: ["beat_detection"]`

**Output**: `(bpm: float, beat_timestamps: List[float], confidence: float)`

**Performance Target**: <10s for 3-minute song

---

### 2. Structure Analysis (`structure_analysis.py`)

**Purpose**: Identify song sections (intro/verse/chorus/bridge/outro) for narrative planning.

**Algorithm**: Fixed 8 clusters (simple, predictable for MVP)
1. **Extract chroma features** using `librosa.feature.chroma()`:
   - Hop length: 512 samples (default)
   - Sample rate: 22050 Hz (librosa default)
   - 12-dimensional chroma (one per semitone)
2. **Build recurrence matrix** from chroma features:
   - Window size: 30 frames (~1.4s at 22050 Hz)
   - Similarity metric: Cosine similarity
   - Threshold: 0.7 (only strong similarities)
3. **Apply agglomerative clustering** (8 clusters):
   - Linkage: Ward linkage (minimizes variance)
   - Distance metric: Euclidean distance on recurrence matrix
   - Number of clusters: Fixed at 8
4. **Convert frame labels to time segments**:
   - Map cluster labels to time using `librosa.frames_to_time()`
   - Merge adjacent segments with same label
5. **Enforce minimum segment duration** (5 seconds):
   - If segment <5s: Merge with adjacent segment (prefer next)
   - Recalculate boundaries after merging
6. **Classify segments using heuristics**:
   - **Intro**: First segment, energy <0.4
   - **Verse**: Medium energy (0.4-0.7), longer duration (>10s typical)
   - **Chorus**: High energy (>0.7), repeated patterns (similarity >0.8 with other segments)
   - **Bridge**: Middle section (40-60% of song), different energy from surrounding
   - **Outro**: Last segment, decreasing energy (energy <0.5)

**Fallback Strategy**:
- If clustering fails (exception or <3 segments after merging):
  - Use uniform segmentation (divide song into 8 equal parts)
  - Classify as "verse" with medium energy (0.5)
  - Flag in metadata: `fallbacks_used: ["structure_analysis"]`

**Output**: `List[SongStructure]` with type, start, end, energy

**Performance Target**: <15s for 3-minute song

---

### 3. Lyrics Extraction (`lyrics_extraction.py`)

**Purpose**: Extract lyrics with word-level timestamps for visual context.

**Algorithm**: OpenAI Whisper API
- Use `openai.Audio.transcriptions.create()` with:
  - `model="whisper-1"`
  - `response_format="verbose_json"` (for word timestamps)
  - `timestamp_granularities=["word"]`
- Retry logic: 3 attempts with exponential backoff (2s, 4s, 8s)
- Cost tracking: Track Whisper API costs via `CostTracker`
- Budget check: Check budget before API call

**Fallback Strategy**:
- If Whisper API fails after 3 retries:
  - Return empty lyrics array `[]`
  - Set confidence to 0.0
  - Flag in metadata: `fallbacks_used: ["lyrics_extraction"]`
  - Continue processing (instrumental tracks are valid)

**Output**: `List[Lyric]` with text and timestamp

**Performance Target**: <30s for 3-minute song (Whisper API dependent)

**Cost**: ~$0.006 per minute of audio (Whisper API pricing)

---

### 4. Mood Classification (`mood_classifier.py`)

**Purpose**: Determine emotional tone for style decisions.

**Algorithm**: Rule-based (simple, fast for MVP)
- **Inputs**: BPM, energy levels (from structure analysis), spectral features (chroma, spectral centroid, rolloff)
- **Feature Extraction**:
  - Energy: Mean RMS energy from structure analysis segments
  - Spectral Centroid: Mean frequency (brightness indicator)
  - Spectral Rolloff: Frequency below which 85% of energy is contained
  - Chroma: 12-dimensional chroma features (key/mode indicators)

**Rules** (with concrete thresholds):
- **Energetic**: 
  - BPM >120 AND energy_mean >0.6 AND spectral_centroid >3000 Hz
  - Confidence: Weighted average of rule matches (0.0-1.0)
- **Calm**: 
  - BPM <90 AND energy_mean <0.4 AND spectral_rolloff <4000 Hz
  - Confidence: Weighted average of rule matches (0.0-1.0)
- **Dark**: 
  - Energy_mean <0.5 AND spectral_centroid <2500 Hz AND (minor key indicators OR low chroma variance)
  - Confidence: Weighted average of rule matches (0.0-1.0)
- **Bright**: 
  - Energy_mean >0.5 AND spectral_centroid >3500 Hz AND (major key indicators OR high chroma variance)
  - Confidence: Weighted average of rule matches (0.0-1.0)

**Classification Logic**:
1. Calculate all rule match scores (0.0-1.0)
2. Select primary mood (highest score)
3. Select secondary mood (second highest, if score >0.3)
4. Set energy_level: "high" if BPM >120 and energy >0.6, "medium" if 90-120, "low" if <90
5. Confidence = primary mood score

**Fallback Strategy**:
- If feature extraction fails or all scores <0.3:
  - Default to "energetic" with confidence 0.5
  - Set energy_level to "medium"
  - Flag in metadata: `fallbacks_used: ["mood_classification"]`

**Output**: `Mood` object with primary, secondary, energy_level, confidence

**Performance Target**: <1s (rule-based, very fast)

---

### 5. Clip Boundaries (`boundaries.py`)

**Purpose**: Generate initial clip boundaries aligned to beats.

**Algorithm**: Beat-aligned boundaries with edge case handling
1. **Start at first beat** (or 0.0 if no beats detected)
2. **Create boundaries at beat intervals**:
   - Target duration: 6 seconds (middle of 4-8s range)
   - Calculate beats per clip: `beats_per_clip = ceil(6.0 / beat_interval)`
   - Create boundary every N beats (where N = beats_per_clip)
3. **Ensure 4-8s duration per clip**:
   - If clip <4s: Extend to next beat (up to 8s max)
   - If clip >8s: Split at 8s, align to nearest beat
4. **Minimum 3 clips** (even for short songs):
   - If song <12s: Create 3 equal segments (ignore beats)
   - Each segment: `duration / 3`
5. **Maximum configurable** (default: 20 clips):
   - If would exceed max: Stop at max, trim last clip to end

**Edge Cases**:
- **Song <12s**: 3 equal segments (4s each if possible)
- **Beat interval >8s**: Split at 8s, align to nearest beat
- **Variable tempo**: Use average beat interval (may cause slight misalignment)
- **No beats detected**: Use tempo-based fallback (4-beat intervals)

**Rules**:
- Clip duration: 4-8 seconds (prefer 6s)
- Alignment: Start/end on beats (±50ms tolerance)
- Minimum: 3 clips (required by PRD)
- Maximum: Configurable via `max_clips` (default: 20)

**Fallback Strategy**:
- If beat detection failed (using tempo-based fallback):
  - Use tempo-based boundaries (4-beat intervals)
  - Calculate beat interval: `60.0 / bpm`
  - Create boundaries: `[0.0, 4*interval, 8*interval, ...]`
  - Ensure minimum 3 clips

**Output**: `List[ClipBoundary]` with start, end, duration

**Performance Target**: <1s (simple algorithm)

---

### 6. Caching (`cache.py`)

**Purpose**: Cache analysis results by file hash to avoid redundant processing.

**Strategy**: Redis-only for MVP (simple, fast) with cache-before-download optimization
- **Cache Key**: `videogen:cache:audio_cache:{md5_hash}`
- **TTL**: 86400 seconds (24 hours)
- **Value**: JSON-serialized `AudioAnalysis` object

**Cache Flow** (Optimized):
1. **Try to extract hash from URL first** (if Supabase Storage includes hash in metadata/URL)
   - If hash found: Check Redis cache
   - If cache hit: Return immediately (skip download)
2. **Download audio file** (if hash not in URL or cache miss)
3. **Calculate MD5 hash** of file bytes
4. **Check Redis cache again** (in case hash wasn't in URL)
5. **If cached**: Return cached result, set `cache_hit: true`
6. **If not cached**: Process audio, store in cache, set `cache_hit: false`

**Note**: Cache-before-download optimization saves bandwidth and time. If hash extraction from URL fails, fall back to download-then-cache approach.

**Performance Target**: Cache hit <1s, cache miss = full processing time

---

## Integration Points

### 1. Orchestrator Integration

**Location**: `api_gateway/orchestrator.py` (replace lines 174-205, currently has stub that fails)

**Current State**: Orchestrator has stub that fails with "Audio parser module not implemented"

**Required Implementation**:
```python
# Stage 1: Audio Parser (10% progress)
await publish_event(job_id, "stage_update", {
    "stage": "audio_parser",
    "status": "started"
})

if await check_cancellation(job_id):
    await handle_pipeline_error(job_id, PipelineError("Job cancelled by user"))
    return

try:
    from modules.audio_parser.main import process_audio_analysis
    audio_data = await process_audio_analysis(job_id, audio_url)
    
    # Store in database (jobs.audio_data JSONB column)
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

**Integration Points**:
- **Input**: `job_id` (str), `audio_url` (str) from orchestrator
- **Output**: `AudioAnalysis` object (Pydantic model)
- **Database**: Store in `jobs.audio_data` JSONB column
- **Progress**: Update via `update_progress()` and `publish_event()` (orchestrator functions)
- **Error Handling**: Raise exceptions (orchestrator handles via `handle_pipeline_error()`)

### 2. Progress Updates

Send SSE events during processing (via orchestrator's `publish_event`):
- **2%**: Beat detection complete → `message: "Beats detected"`
- **4%**: Structure analysis complete → `message: "Structure analyzed"`
- **6%**: Lyrics extraction complete → `message: "Lyrics extracted"`
- **8%**: Mood classification complete → `message: "Mood classified"`
- **9%**: Clip boundaries generated → `message: "Boundaries generated"`
- **10%**: Complete → `stage_update: "completed"`

**Note**: Progress percentages are cumulative completion markers (not time-weighted). Total adds to 10% because this module represents 10% of total pipeline progress (0-10%).

### 3. Database Storage

- **Table**: `jobs`
- **Column**: `audio_data` (JSONB) - already exists in schema (`supabase/migrations/20251115013200_add_audio_data.sql`)
- **Store**: `audio_data.model_dump()` as JSON (Pydantic model serialization)
- **When**: After successful processing, before returning to orchestrator
- **Storage Strategy**:
  - Store complete `AudioAnalysis` object only after all components succeed
  - If any component fails (after fallbacks): Store partial results in metadata for debugging
  - Storage is blocking (must succeed for pipeline to continue)
  - If storage fails: Log error but don't fail pipeline (orchestrator will handle)

### 4. Cost Tracking

- **Track**: Whisper API costs only (main cost driver)
- **Cost Calculation**: 
  - Whisper API: $0.006 per minute of audio
  - Calculate: `cost = (duration_seconds / 60.0) * 0.006`
- **When**: After each Whisper API call (on success only, not on retries)
- **Method**: `CostTracker.track_cost(job_id, "audio_parser", "whisper", cost)`
- **Budget Check**: Before Whisper API call (prevent wasted calls)
  - Get current total cost: `current_cost = await cost_tracker.get_total_cost(job_id)`
  - Estimate Whisper cost: `estimated_cost = (duration_seconds / 60.0) * 0.006`
  - Check budget: `can_proceed = await cost_tracker.check_budget(job_id, estimated_cost, limit)`
  - If budget exceeded: Raise `BudgetExceededError` (stops pipeline)

---

## Error Handling

### Component-Level Failures

Each component has fallback strategy (see Component Specifications):
- **Beat Detection**: Falls back to tempo-based boundaries
- **Structure Analysis**: Falls back to uniform segmentation
- **Lyrics Extraction**: Falls back to empty array (instrumental)
- **Mood Classification**: Falls back to default mood
- **Clip Boundaries**: Uses fallback beats if available

### Module-Level Failures

Module fails only if:
- **Critical failure**: Both beat detection AND structure analysis fail (after fallbacks)
- **Budget exceeded**: Cost exceeds limit before/during processing
- **Cancellation**: Job cancelled by user (checked by orchestrator)
- **Storage error**: Cannot download audio file (after retries)

**Error Decision Tree**:
```
Beat Detection:
  - Exception raised → Retry 3x (if RetryableError), then fallback
  - Confidence <0.6 → Use fallback (tempo-based beats)
  - No beats found → Use fallback
  - Both retry and fallback fail → Module fails

Structure Analysis:
  - Clustering exception → Use fallback (uniform segmentation)
  - <3 segments after merging → Use fallback
  - Both clustering and fallback fail → Module fails

Lyrics Extraction:
  - Whisper API exception → Retry 3x (exponential backoff)
  - After 3 retries → Use fallback (empty lyrics array)
  - Fallback always succeeds (instrumental tracks valid)

Mood Classification:
  - Feature extraction fails → Use fallback (default mood)
  - Fallback always succeeds

Clip Boundaries:
  - Uses beat detection results (or fallback beats)
  - Always succeeds (minimum 3 clips guaranteed)
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

## Implementation Phases

### Phase 0: Model Creation (Before Phase 1)
1. Create `shared/models/audio.py` with all models:
   - `SongStructure`, `Lyric`, `Mood`, `ClipBoundary`, `AudioAnalysis`
2. Add `AudioAnalysisError` to `shared/errors.py`
3. Update `shared/models/__init__.py` to export audio models
4. Test model creation

### Phase 1: Foundation & Integration (Day 1 - Morning)
1. Create module directory structure
2. Create `__init__.py` and `main.py` with entry point
3. Create `parser.py` skeleton
4. Integrate with orchestrator (replace stub)
5. Test: Verify orchestrator can call module

### Phase 2: Core Components (Day 1 - Afternoon)
1. Implement `beat_detection.py` (Librosa)
2. Implement `structure_analysis.py` (8 clusters)
3. Implement `mood_classifier.py` (rules)
4. Implement `boundaries.py` (beat-aligned)
5. Test: Each component independently

### Phase 3: Lyrics & Caching (Day 2 - Morning)
1. Implement `lyrics_extraction.py` (Whisper API + retry)
2. Implement `cache.py` (Redis helpers)
3. Integrate caching in `parser.py`
4. Test: Lyrics extraction, caching, cost tracking

### Phase 4: Orchestrator Integration (Day 2 - Afternoon)
1. Update orchestrator (replace stub)
2. Add progress updates (SSE events)
3. Add error handling
4. Test: End-to-end via API Gateway

### Phase 5: Testing & Validation (Day 2 - Evening)
1. Unit tests (each component)
2. Integration tests (full flow)
3. E2E tests (via API Gateway)
4. Manual testing (diverse genres)

---

## Testing Requirements

### Unit Tests
- Each component tested independently
- Mock external dependencies (Whisper API, storage)
- Test fallbacks
- Test edge cases (short songs, instrumental, complex rhythms)

### Integration Tests
- Test full `parse_audio()` flow
- Test caching (hit and miss)
- Test database storage
- Test cost tracking

### End-to-End Tests
- Upload audio via API Gateway
- Verify job processing
- Verify results in database
- Verify progress updates in frontend

### Manual Testing
- Test with diverse genres (electronic, rock, jazz, ambient, instrumental)
- Test with different song lengths (30s, 3min, 10min)
- Test error scenarios
- Verify cost tracking

---

## Dependencies

### Python Packages
- `librosa>=0.10.1` - Beat detection, structure analysis
- `soundfile>=0.12.1` - Audio I/O
- `numpy>=1.24.0` - Numerical operations
- `scipy>=1.11.0` - Signal processing
- `scikit-learn>=1.3.0` - Clustering
- `openai>=1.3.0` - Whisper API

### Shared Components (Already Built)
- `shared.config` - Environment variables
- `shared.database` - Database client
- `shared.redis_client` - Redis client
- `shared.storage` - Storage client
- `shared.cost_tracking` - Cost tracker
- `shared.logging` - Structured logging
- `shared.retry` - Retry decorator
- `shared.errors` - Error classes
- `shared.models` - Pydantic models (to be created)

---

## Known Limitations & Future Enhancements

### MVP Limitations
- **Librosa only** (no Aubio merge) - can add later for improved accuracy
- **Fixed 8 clusters** (no dynamic clustering) - can add later based on song complexity
- **Rule-based mood** (no ML) - can add later with ML-based classification
- **Redis-only cache** (no database backup) - can add later for persistence across Redis restarts
- **No parallel processing** - Components run sequentially (can parallelize independent components later)
- **No boundary refinement** - Scene Planner can adjust ±2s, but Audio Parser generates initial boundaries

### Future Enhancements
- Add Aubio for improved beat detection accuracy
- Dynamic clustering based on song complexity
- ML-based mood classification
- Database cache backup for persistence
- Parallel processing of independent components (beat detection + structure analysis can run in parallel)
- Incremental results (return as computed, stream to frontend)
- Boundary refinement feedback loop (Scene Planner adjusts, Audio Parser learns)

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

**Document Status:** Ready for Implementation  
**Next Action:** Create Phase 0 (models), then begin Phase 1 (foundation)

