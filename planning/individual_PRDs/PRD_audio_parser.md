# Audio Parser Module - Implementation PRD

**Version:** 1.0 | **Date:** November 14, 2025  
**Module:** Module 3 (Audio Parser)  
**Phase:** Phase 2  
**Status:** Implementation-Ready

---

## Executive Summary

This document provides a complete implementation guide for the Audio Parser module, which performs comprehensive audio analysis to extract beats, tempo, song structure, lyrics, mood, and clip boundaries. The module serves as the foundation for all downstream creative decisions in the music video generation pipeline.

**Timeline:** 6-8 hours  
**Dependencies:** Phase 0 shared components (config, database, redis, storage, models, retry, cost_tracking, logging, errors, validation)  
**Output:** AudioAnalysis Pydantic model conforming to `shared/models/audio.py`

---

## Directory Structure

```
backend/modules/audio_parser/
├── __init__.py                 # Module exports
├── main.py                     # Main entry point, FastAPI router integration
├── parser.py                   # Core audio parsing logic
├── beat_detection.py          # Librosa + Aubio beat detection implementation
├── structure_analysis.py      # Song structure classification
├── mood_classifier.py         # Mood classification logic
├── whisper_client.py          # OpenAI Whisper API integration
├── cache.py                    # Redis caching utilities
├── boundaries.py              # Clip boundary generation
├── utils.py                    # Audio file utilities (download, hash, validation)
├── tests/
│   ├── __init__.py
│   ├── test_parser.py          # Main parser integration tests
│   ├── test_beat_detection.py  # Beat detection unit tests
│   ├── test_structure.py       # Structure analysis tests
│   ├── test_mood.py            # Mood classification tests
│   ├── test_whisper.py         # Whisper API integration tests
│   ├── test_cache.py           # Caching tests
│   ├── test_boundaries.py      # Boundary generation tests
│   └── fixtures/
│       ├── sample_audio.mp3    # Test audio files (various genres)
│       ├── sample_audio.wav
│       └── instrumental.mp3    # Instrumental track for lyrics fallback test
└── README.md                   # Module documentation
```

---

## File Specifications

### `__init__.py`
**Purpose:** Module exports and public API

**Exports:**
- `parse_audio` function (main entry point)
- `AudioParser` class (if using class-based approach)
- All exception classes from this module

**Implementation Notes:**
- Export only public API functions
- Import shared utilities (errors, logging, models) at module level
- Define module-level logger using `get_logger("audio_parser")`

---

### `main.py`
**Purpose:** FastAPI router integration and job processing entry point

**Function: `process_audio_analysis`**
- **Input:** `job_id: UUID`, `audio_url: str`
- **Output:** `AudioAnalysis` Pydantic model
- **Purpose:** Main entry point called by API Gateway orchestrator
- **Logic:**
  1. Validate inputs using shared validation utilities
  2. Check Redis cache using audio file hash (MD5)
  3. If cache hit: Return cached AudioAnalysis, update metadata.cache_hit=True
  4. If cache miss: Download audio file from Supabase Storage
  5. Calculate MD5 hash of audio file bytes
  6. Call `parse_audio` function with audio file bytes
  7. Store result in Redis cache (24h TTL) and database cache table
  8. Track cost using cost_tracker (Whisper API calls)
  9. Return AudioAnalysis model
- **Error Handling:**
  - Raise `ValidationError` for invalid inputs
  - Raise `AudioAnalysisError` for processing failures
  - Wrap external API calls with retry decorator
  - Log all errors with job_id context

**Function: `get_cached_analysis`**
- **Input:** `file_hash: str` | **Output:** `Optional[AudioAnalysis]`
- Check Redis cache: key=`videogen:audio_cache:{file_hash}`, deserialize if found

**Function: `store_cached_analysis`**
- **Input:** `file_hash: str`, `analysis: AudioAnalysis`, `ttl: int = 86400`
- Serialize to JSON, store in Redis (24h TTL) and database cache table

---

### `parser.py`
**Purpose:** Core orchestration of all audio analysis steps

**Function: `parse_audio`**
- **Input:** `audio_bytes: bytes`, `job_id: UUID`
- **Output:** `AudioAnalysis` Pydantic model
- **Purpose:** Coordinate all analysis steps and assemble final result
- **Logic:**
  1. Load audio file into librosa: `y, sr = librosa.load(io.BytesIO(audio_bytes), sr=None)`
  2. Calculate duration: `duration = len(y) / sr`
  3. Extract BPM and beats: Call `detect_beats` function
  4. Classify song structure: Call `analyze_structure` function
  5. Extract lyrics: Call `extract_lyrics` function (async, with retry)
  6. Classify mood: Call `classify_mood` function
  7. Generate clip boundaries: Call `generate_boundaries` function
  8. Assemble AudioAnalysis model with all results
  9. Populate metadata: processing_time, cache_hit=False, confidence scores, fallback_used flags
  10. Return AudioAnalysis

**Error Handling:**
- Catch librosa loading errors → Raise AudioAnalysisError
- If beat detection fails → Use fallback tempo-based boundaries
- If lyrics extraction fails → Return empty lyrics array, set fallback_used=True
- If structure analysis fails → Use simple structure (single segment), set fallback_used=True
- Log all fallback scenarios with warning level

---

### `beat_detection.py`
**Purpose:** Beat detection using Librosa + Aubio with deduplication

**Function: `detect_beats`**
- **Input:** `y: np.ndarray` (audio signal), `sr: int` (sample rate)
- **Output:** `Tuple[float, List[float], float]` (BPM, beat_timestamps, confidence)
- **Purpose:** Extract BPM and beat timestamps with ±50ms precision
- **Logic:**
  1. **Librosa beat tracking:**
     - Call `librosa.beat.beat_track(y=y, sr=sr, units='time')`
     - Extract tempo (BPM) and beat frames
     - Convert beat frames to timestamps: `librosa.frames_to_time(beat_frames, sr=sr)`
  2. **Aubio onset detection:**
     - Create aubio tempo object: `tempo = aubio.tempo("default", 1024, 512, sr)`
     - Process audio in chunks, collect onset timestamps
     - Convert to numpy array of timestamps
  3. **Merge and deduplicate:**
     - Combine librosa and aubio timestamps into single list
     - Sort timestamps
     - Deduplicate: Remove timestamps within 50ms of each other (keep first)
     - Calculate confidence: Compare librosa and aubio results, measure agreement
  4. **Validate BPM:**
     - Clamp BPM to 60-200 range
     - If outside range: Use default 120 BPM, set confidence to 0.5
  5. **Fallback if low confidence:**
     - If confidence < 0.6: Use tempo-based boundaries (4-beat intervals)
     - Calculate beat interval: `60.0 / bpm`
     - Generate timestamps: `[0, interval, 2*interval, ...]` up to duration
  6. Return (BPM, beat_timestamps, confidence)

**Function: `_deduplicate_beats`**
- **Input:** `timestamps: List[float]`, `threshold_ms: float = 50.0` | **Output:** `List[float]`
- **Purpose:** Remove duplicate beats within threshold to ensure ±50ms precision
- **Logic:**
  1. Sort timestamps in ascending order
  2. Initialize result list with first timestamp
  3. Iterate through remaining timestamps:
     - Calculate time difference from last kept timestamp: `diff = timestamp - result[-1]`
     - Convert threshold to seconds: `threshold_sec = threshold_ms / 1000.0`
     - If diff >= threshold_sec: Add timestamp to result
     - If diff < threshold_sec: Skip (duplicate within threshold)
  4. Return deduplicated list

---

### `structure_analysis.py`
**Purpose:** Song structure classification (intro/verse/chorus/bridge/outro)

**Function: `analyze_structure`**
- **Input:** `y: np.ndarray`, `sr: int`, `beat_timestamps: List[float]`, `duration: float`
- **Output:** `List[SongStructure]`
- **Purpose:** Classify song sections with energy levels
- **Logic:**
  1. **Extract chroma features:**
     - Compute chroma: `chroma = librosa.feature.chroma_stft(y=y, sr=sr)`
     - Use hop_length=512 for reasonable resolution
  2. **Build recurrence matrix:**
     - Compute self-similarity matrix from chroma features
     - Use cosine similarity or correlation
  3. **Segment detection:**
     - Apply agglomerative clustering or novelty detection
     - Identify segment boundaries using librosa.segment.agglomerative or similar
  4. **Classify segments:**
     - For each detected segment:
       - Calculate energy: RMS or spectral centroid
       - Classify type using heuristics:
         - First segment → "intro" (if < 15s and low energy)
         - Last segment → "outro" (if < 15s and low energy)
         - High energy segments → "chorus"
         - Medium energy → "verse"
         - Transitional → "bridge"
       - Map energy to level: low/medium/high based on thresholds
  5. **Fallback:**
     - If segmentation fails: Return single segment covering entire duration
     - Type: "verse", Energy: "medium"
  6. Return list of SongStructure objects

**Function: `_calculate_segment_energy`**
- **Input:** `y_segment: np.ndarray`, `sr: int` | **Output:** `float` (0.0-1.0)
- **Purpose:** Calculate energy level for segment classification (low/medium/high)
- **Logic:**
  1. Compute RMS: `rms = librosa.feature.rms(y=y_segment)`, take mean: `rms_mean = np.mean(rms)`
  2. Compute spectral centroid: `centroid = librosa.feature.spectral_centroid(y=y_segment, sr=sr)`, take mean: `centroid_mean = np.mean(centroid)`
  3. Normalize RMS: `rms_norm = rms_mean / max_rms` (use max_rms from full track or 1.0)
  4. Normalize centroid: `centroid_norm = centroid_mean / max_centroid` (use max_centroid from full track or 5000.0)
  5. Combine: `energy = (rms_norm * 0.6) + (centroid_norm * 0.4)` (weighted average)
  6. Clamp to [0.0, 1.0] range
  7. Return energy value

---

### `mood_classifier.py`
**Purpose:** Mood classification using audio features

**Function: `classify_mood`**
- **Input:** `y: np.ndarray`, `sr: int`, `bpm: float`, `structure: List[SongStructure]`
- **Output:** `Mood` Pydantic model
- **Purpose:** Classify mood (energetic/calm/dark/bright) with confidence
- **Logic:**
  1. **Extract features:**
     - Tempo (BPM): Already available
     - Spectral centroid: Brightness indicator
     - Zero crossing rate: Texture indicator
     - Spectral rolloff: High-frequency content
     - Energy: RMS across entire track
  2. **Rule-based classification:**
     - **Primary mood:**
       - If BPM > 130 and energy > 0.7 → "energetic"
       - If BPM < 90 and energy < 0.4 → "calm"
       - If spectral centroid < 2000 Hz → "dark"
       - If spectral centroid > 4000 Hz → "bright"
       - Default: "energetic" if BPM > 100, else "calm"
     - **Secondary mood:**
       - Based on complementary features (e.g., energetic + bright)
     - **Energy level:**
       - Low: energy < 0.4 or BPM < 90
       - High: energy > 0.7 or BPM > 130
       - Medium: otherwise
     - **Confidence:**
       - Calculate based on feature agreement
       - Higher confidence if multiple features agree
       - Range: 0.0-1.0
  3. Return Mood model

---

### `whisper_client.py`
**Purpose:** OpenAI Whisper API integration with retry logic

**Function: `extract_lyrics`**
- **Input:** `audio_bytes: bytes`, `job_id: UUID`
- **Output:** `List[Lyric]`
- **Purpose:** Extract lyrics with word-level timestamps using Whisper API
- **Logic:**
  1. **Prepare audio file:**
     - Save audio_bytes to temporary file (use tempfile module)
     - Ensure file format is supported (MP3, WAV, FLAC)
  2. **Call Whisper API:**
     - Use OpenAI client: `openai.Audio.transcriptions.create()`
     - Parameters:
       - file: Temporary file object
       - model: "whisper-1"
       - response_format: "verbose_json"
       - timestamp_granularities: ["word"]
     - Set timeout: 60 seconds
  3. **Process response:**
     - Extract words array from response
     - For each word: Create Lyric object with text and timestamp (start time)
     - Filter out empty words
  4. **Error handling:**
     - Wrap API call with @retry_with_backoff decorator (3 attempts, 2s base delay)
     - On RetryableError: Retry with exponential backoff
     - On permanent failure: Return empty list, log warning
     - Track cost: $0.006 per minute (calculate from audio duration)
  5. **Cleanup:**
     - Delete temporary file
  6. Return list of Lyric objects

**Function: `_calculate_whisper_cost`**
- **Input:** `duration_seconds: float` | **Output:** `Decimal`
- Calculate: (duration_seconds / 60.0) * 0.006

---

### `cache.py`
**Purpose:** Redis caching utilities for audio analysis

**Function: `get_cached_analysis`**
- **Input:** `file_hash: str` | **Output:** `Optional[AudioAnalysis]`
- Redis key: `videogen:audio_cache:{file_hash}`, deserialize if found

**Function: `store_cached_analysis`**
- **Input:** `file_hash: str`, `analysis: AudioAnalysis`, `ttl: int = 86400`
- Serialize to JSON, store in Redis (24h TTL) and database cache table

**Function: `calculate_file_hash`**
- **Input:** `audio_bytes: bytes` | **Output:** `str` (MD5)
- Use hashlib.md5(), return hexdigest

---

### `boundaries.py`
**Purpose:** Generate beat-aligned clip boundaries

**Function: `generate_boundaries`**
- **Input:** `beat_timestamps: List[float]`, `duration: float`, `bpm: float`, `min_clips: int = 3`, `min_duration: float = 4.0`, `max_duration: float = 8.0`
- **Output:** `List[ClipBoundary]`
- **Purpose:** Generate clip boundaries aligned to beats, 4-8s duration, minimum 3 clips
- **Logic:**
  1. **Calculate target clip duration:**
     - Ideal: 6 seconds (middle of 4-8s range)
     - Adjust based on total duration and min_clips requirement
  2. **Generate boundaries:**
     - Start at first beat (or 0.0 if no beats)
     - For each boundary:
       - Find next beat that is >= min_duration away
       - If next beat is > max_duration away: Use max_duration
       - Create boundary: start=current_beat, end=next_beat (or start+max_duration)
       - Move to next boundary start
     - Ensure last boundary extends to duration (or last beat)
  3. **Validate:**
     - Ensure at least min_clips boundaries
     - If not enough: Reduce duration per clip, regenerate
     - Ensure all boundaries are within [0, duration]
  4. **Beat alignment:**
     - Snap boundary starts/ends to nearest beat within ±100ms
     - Prefer boundaries that start/end exactly on beats
  5. Return list of ClipBoundary objects

**Function: `_snap_to_beat`**
- **Input:** `timestamp: float`, `beat_timestamps: List[float]`, `threshold: float = 0.1` | **Output:** `float`
- **Purpose:** Snap timestamp to nearest beat if within threshold (±100ms default)
- **Logic:**
  1. If beat_timestamps is empty: Return original timestamp
  2. Find nearest beat: Calculate absolute differences, find minimum: `nearest_beat = min(beat_timestamps, key=lambda b: abs(b - timestamp))`
  3. Calculate distance: `distance = abs(nearest_beat - timestamp)`
  4. If distance <= threshold: Return nearest_beat (snap to beat)
  5. Otherwise: Return original timestamp (no snap)

---

### `utils.py`
**Purpose:** Audio file utilities

**Function: `download_audio_file`**
- **Input:** `audio_url: str` | **Output:** `bytes`
- Use shared.storage.download_file(bucket="audio-uploads"), handle errors

**Function: `validate_audio_file`**
- **Input:** `audio_bytes: bytes`, `max_size_mb: int = 10` | **Output:** `bool`
- Check size ≤ max_size_mb, validate format with librosa.load(), raise ValidationError if invalid

---

## Integration Points

### Shared Components Usage

**config.py:**
- Access OpenAI API key: `settings.openai_api_key`
- Access Redis URL: `settings.redis_url`
- Access Supabase settings: `settings.supabase_url`, `settings.supabase_service_key`

**database.py:**
- Store analysis results in `audio_analysis_cache` table
- Query job status for updates

**redis_client.py:**
- Use `redis.get_json()` and `redis.set_json()` for caching
- Key format: `videogen:audio_cache:{file_hash}`

**storage.py:**
- Download audio files: `storage.download_file(bucket="audio-uploads", path=...)`
- Use service key for backend operations

**models/audio.py:**
- Import AudioAnalysis, SongStructure, Lyric, Mood, ClipBoundary models
- All functions return these Pydantic models

**retry.py:**
- Decorate Whisper API calls: `@retry_with_backoff(max_attempts=3, base_delay=2)`
- Only retries on RetryableError exceptions

**cost_tracking.py:**
- Track Whisper API costs: `cost_tracker.track_cost(job_id, stage="audio_analysis", api_name="whisper", cost=...)`
- Calculate cost from audio duration: $0.006 per minute

**logging.py:**
- Use module logger: `logger = get_logger("audio_parser")`
- Include job_id in all log entries
- Log processing time, cache hits, confidence scores

**errors.py:**
- Raise `AudioAnalysisError` for processing failures
- Raise `ValidationError` for invalid inputs
- Raise `RetryableError` for transient API failures

**validation.py:**
- Use `validate_audio_file()` for file validation
- Validate file size and MIME type

---

## Error Handling Patterns

**Input Validation:**
- Validate job_id is valid UUID
- Validate audio_url is valid URL
- Validate audio file size ≤ 10MB
- Raise ValidationError immediately (no retries)

**Processing Errors:**
- Beat detection failure → Use tempo-based fallback, set fallback_used=True
- Structure analysis failure → Use single-segment fallback, set fallback_used=True
- Lyrics extraction failure → Return empty array, set fallback_used=True
- Log all fallbacks with warning level

**API Errors:**
- Whisper API timeout → Retry with exponential backoff (3 attempts)
- Whisper API rate limit → Retry with exponential backoff
- Whisper API permanent error → Return empty lyrics, log error
- Wrap API calls with @retry_with_backoff decorator

**Storage Errors:**
- Download failure → Retry 3 times with exponential backoff
- Cache write failure → Log warning, continue without caching
- Never fail job due to cache errors

---

## Testing Requirements

### Unit Tests

**test_beat_detection.py:**
- Test librosa beat_track returns valid BPM and timestamps
- Test aubio tempo detection returns onset timestamps
- Test merge combines both timestamp lists correctly
- Test deduplication removes beats within 50ms threshold
- Test BPM validation clamps to 60-200 range
- Test fallback tempo-based boundaries when confidence <0.6
- Test confidence calculation measures agreement between methods
- Test edge cases: Very fast tempo (>200 BPM), very slow tempo (<60 BPM), no clear beats

**test_structure.py:**
- Test chroma feature extraction produces valid features
- Test recurrence matrix computation from chroma
- Test segment detection identifies boundaries correctly
- Test segment classification (intro/verse/chorus/bridge/outro) using heuristics
- Test energy calculation for each segment
- Test fallback single-segment structure when segmentation fails
- Test edge cases: Single segment songs, very long songs (>5min), very short songs (<30s)

**test_mood.py:**
- Test mood classification rules (BPM >130 + energy >0.7 → energetic)
- Test confidence calculation based on feature agreement
- Test various BPM/energy combinations produce expected moods
- Test edge cases: Very fast tempo, very slow tempo, very high energy, very low energy

**test_boundaries.py:**
- Test boundary generation produces 4-8s clips
- Test minimum 3 clips requirement (regenerate if not enough)
- Test beat alignment snaps boundaries to beats within ±100ms
- Test duration edge cases: Very short songs (<30s), very long songs (>5min)
- Test boundary validation ensures all within [0, duration]

**test_cache.py:**
- Test cache hit: Return cached analysis, set cache_hit=True
- Test cache miss: Process audio, store in cache
- Test TTL expiration: Cache expires after 24 hours
- Test cache key generation: MD5 hash produces consistent keys
- Test database persistence: Cache stored in both Redis and database

**test_whisper.py:**
- Mock Whisper API responses with word-level timestamps
- Test word timestamp extraction from verbose_json response
- Test retry logic: 3 attempts with exponential backoff on failures
- Test cost calculation: $0.006 per minute
- Test empty lyrics fallback: Return empty array on permanent failure
- Test timeout handling: 60s timeout per request

### Integration Tests

**test_parser.py:**
- Test full parsing pipeline with real audio files (3-minute song)
- Test caching: Cache hit scenario returns immediately
- Test all fallback scenarios: Beat detection fails, lyrics fail, structure fails
- Test error handling: Network errors, API errors, processing errors
- Test cost tracking: Costs tracked accurately per API call
- Test database storage: Results stored in database correctly
- Test with various audio formats: MP3, WAV, FLAC
- Test with instrumental tracks: No lyrics, empty lyrics array returned
- Test with very short songs (<30s): Minimum 3 clips still generated
- Test with very long songs (>5min): Boundaries generated correctly

**Test Fixtures:**
- Electronic track (high BPM ~140, energetic, clear beats)
- Rock track (medium BPM ~120, energetic, clear structure)
- Ambient track (low BPM ~70, calm, minimal beats)
- Instrumental track (no vocals, should return empty lyrics)
- Short clip (<30s, test minimum clips requirement)
- Long track (>5min, test boundary generation at scale)

### Performance Tests

- Process 3-minute song in <60 seconds (target: 45-60s)
- Cache lookup in <10ms (Redis get operation)
- Beat detection accuracy: 90%+ beats within ±50ms of ground truth
- BPM accuracy: ±2 BPM for 80%+ songs (compared to manual BPM detection)
- Structure classification: 70%+ accurate segment boundaries
- Lyrics extraction: >70% word accuracy (compared to manual transcription)

---

## Success Criteria

✅ Process 3-minute song in < 60 seconds  
✅ BPM accuracy: ±2 for 80%+ songs  
✅ Beat detection: 90%+ within ±50ms  
✅ Structure classification: 70%+ accurate  
✅ Lyrics extraction: >70% accurate (gracefully handles instrumental tracks)  
✅ Caching: Redis cache hit rate 20-30%  
✅ Retry logic: 3 attempts for Whisper API with exponential backoff  
✅ Cost tracking: Accurate cost per job (±$0.01)  
✅ Error handling: All fallbacks work correctly  
✅ Test coverage: 80%+ code coverage

---

## Implementation Notes

**Librosa Configuration:**
- Use `sr=None` to preserve original sample rate
- Use hop_length=512 for reasonable feature resolution
- Use n_fft=2048 for spectral analysis

**Aubio Configuration:**
- Buffer size: 1024 samples
- Hop size: 512 samples
- Use default tempo detection method

**Whisper API:**
- Model: "whisper-1" (latest stable)
- Response format: "verbose_json" for word timestamps
- Timeout: 60 seconds per request
- Cost: $0.006 per minute of audio

**Redis Caching:**
- Key format: `videogen:audio_cache:{md5_hash}`
- TTL: 86400 seconds (24 hours)
- Also store in database for persistence

**Performance Optimization:**
- Cache results by audio file hash (MD5)
- Use async/await for I/O operations
- Parallel processing not needed (sequential steps)

**Boundary Ownership:**
- Audio Parser generates initial beat-aligned boundaries
- Scene Planner can refine boundaries within ±2s for narrative needs
- Boundaries must stay within ±2s of beat-aligned positions

---

**Document Status:** Ready for Implementation  
**Next Action:** Begin implementation starting with `main.py` and `parser.py`, then implement each analysis component

