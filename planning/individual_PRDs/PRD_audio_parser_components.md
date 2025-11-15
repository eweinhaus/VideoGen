# Module 3: Audio Parser - Component Specifications

**Version:** 2.0 | **Date:** November 15, 2025  
**Related PRDs:**
- [Overview & Integration](./PRD_audio_parser_overview.md) - High-level architecture and integration points
- [Implementation Guide](./PRD_audio_parser_implementation.md) - Step-by-step implementation instructions

---

## Component Overview

The Audio Parser consists of 6 core components that work together to analyze audio files:

| Component | File | Purpose | Performance Target |
|-----------|------|---------|-------------------|
| Beat Detection | `beat_detection.py` | Extract BPM and beat timestamps | <10s |
| Structure Analysis | `structure_analysis.py` | Identify song sections | <15s |
| Lyrics Extraction | `lyrics_extraction.py` | Extract lyrics with timestamps | <30s |
| Mood Classification | `mood_classifier.py` | Determine emotional tone | <1s |
| Clip Boundaries | `boundaries.py` | Generate clip boundaries | <1s |
| Caching | `cache.py` | Cache results by file hash | <1s (cache hit) |

**Component Dependencies:**
```
Beat Detection (independent)
    ↓
Structure Analysis (uses: beat detection results for energy)
    ↓
Lyrics Extraction (independent)
    ↓
Mood Classification (uses: BPM, structure energy, spectral features)
    ↓
Clip Boundaries (uses: beat timestamps, duration)
    ↓
Caching (wraps all components)
```

---

## Component 1: Beat Detection (`beat_detection.py`)

**Purpose**: Extract BPM and precise beat timestamps for video synchronization.

### Algorithm Details

**Librosa-based beat detection** (simple, reliable for MVP):

1. **Load audio**:
   - Use `librosa.load()` with default parameters
   - Sample rate: 22050 Hz (librosa default)
   - Mono conversion: Automatic

2. **Extract tempo**:
   ```python
   tempo, beats = librosa.beat.beat_track(y=audio, sr=sr)
   ```
   - Returns: BPM (float) and beat frame indices
   - Default parameters: `hop_length=512`, `start_bpm=120`

3. **Convert frames to timestamps**:
   ```python
   beat_timestamps = librosa.frames_to_time(beats, sr=sr)
   ```
   - Returns: List of beat timestamps in seconds

4. **Validate BPM**:
   - Range: 60-200 BPM
   - If outside range: Clamp to nearest valid value (60 or 200)
   - Log warning if clamped

5. **Calculate confidence**:
   - Use librosa's built-in confidence from `beat_track()`
   - If confidence <0.6: Trigger fallback

**Output**: `(bpm: float, beat_timestamps: List[float], confidence: float)`

### Fallback Strategy

**When fallback triggers**:
- Beat detection fails (exception)
- Confidence <0.6
- No beats found (empty list)

**Fallback algorithm**:
```python
# Calculate beat interval from tempo
beat_interval = 60.0 / bpm

# Generate beats from start
beat_timestamps = []
current_time = 0.0
while current_time < duration:
    beat_timestamps.append(current_time)
    current_time += beat_interval

# Set confidence to 0.5 (indicates fallback used)
confidence = 0.5
```

**Metadata flag**: `fallbacks_used: ["beat_detection"]`

### Edge Cases

- **No beats detected**: Use tempo-based fallback
- **Very slow tempo (<60 BPM)**: Clamp to 60 BPM, use fallback
- **Very fast tempo (>200 BPM)**: Clamp to 200 BPM, use fallback
- **Variable tempo**: Use average tempo (may cause slight misalignment)

### Performance Target

<10s for 3-minute song

### Code Example

```python
import librosa
import numpy as np
from typing import Tuple, List

def detect_beats(audio: np.ndarray, sr: int = 22050) -> Tuple[float, List[float], float]:
    """
    Detect beats in audio using Librosa.
    
    Args:
        audio: Audio signal (numpy array)
        sr: Sample rate (default: 22050)
        
    Returns:
        (bpm, beat_timestamps, confidence)
    """
    duration = len(audio) / sr  # Calculate duration from audio length
    
    try:
        # Extract tempo and beats
        tempo, beats = librosa.beat.beat_track(y=audio, sr=sr)
        
        # Convert tempo to scalar (librosa may return numpy array)
        tempo = float(tempo) if hasattr(tempo, 'item') else float(tempo)
        
        # Validate BPM range
        if tempo < 60:
            tempo = 60.0
            confidence = 0.5  # Low confidence due to clamping
        elif tempo > 200:
            tempo = 200.0
            confidence = 0.5
        else:
            # Librosa doesn't return confidence directly, estimate from beat consistency
            # Calculate confidence based on beat interval consistency
            if len(beats) > 1:
                beat_intervals = np.diff(beats)
                interval_std = np.std(beat_intervals)
                interval_mean = np.mean(beat_intervals)
                # Lower std relative to mean = higher confidence
                confidence = max(0.0, min(1.0, 1.0 - (interval_std / interval_mean)))
            else:
                confidence = 0.5
        
        # Convert frames to timestamps
        beat_timestamps = librosa.frames_to_time(beats, sr=sr).tolist()
        
        # Check if fallback needed
        if confidence < 0.6 or len(beat_timestamps) == 0:
            return _tempo_based_fallback(tempo, duration)
        
        return tempo, beat_timestamps, confidence
        
    except Exception as e:
        # Fallback on any error
        return _tempo_based_fallback(120.0, duration)  # Default 120 BPM

def _tempo_based_fallback(bpm: float, duration: float) -> Tuple[float, List[float], float]:
    """
    Generate tempo-based beats as fallback.
    
    Args:
        bpm: Tempo in beats per minute
        duration: Audio duration in seconds
        
    Returns:
        (bpm, beat_timestamps, confidence)
    """
    beat_interval = 60.0 / bpm
    beat_timestamps = []
    current_time = 0.0
    while current_time < duration:
        beat_timestamps.append(current_time)
        current_time += beat_interval
    return bpm, beat_timestamps, 0.5  # Low confidence indicates fallback used
```

---

## Component 2: Structure Analysis (`structure_analysis.py`)

**Purpose**: Identify song sections (intro/verse/chorus/bridge/outro) for narrative planning.

### Algorithm Details

**Fixed 8 clusters** (simple, predictable for MVP):

1. **Extract chroma features**:
   ```python
   chroma = librosa.feature.chroma(y=audio, sr=sr)
   ```
   - Hop length: 512 samples (default)
   - Sample rate: 22050 Hz (librosa default)
   - 12-dimensional chroma (one per semitone)
   - Shape: (12, num_frames)

2. **Build recurrence matrix** (optimized for performance):
   ```python
   # Window size: 30 frames (~1.4s at 22050 Hz)
   window_size = 30
   num_frames = chroma.shape[1]
   
   # Use sparse matrix or sliding window to avoid O(n²) for long songs
   # For MVP: Build full matrix but note performance implications
   from sklearn.metrics.pairwise import cosine_similarity
   
   recurrence = np.zeros((num_frames, num_frames))
   
   # Performance note: For songs >5min, consider using sliding window or sparse matrix
   # For 3-minute song: ~8000 frames = 64M comparisons (acceptable for MVP)
   for i in range(num_frames):
       # Only compare within window (reduces comparisons)
       j_start = max(0, i - window_size)
       j_end = min(num_frames, i + window_size)
       
       for j in range(j_start, j_end):
           # Cosine similarity
           similarity = cosine_similarity(
               chroma[:, i:i+1].T, 
               chroma[:, j:j+1].T
           )[0, 0]
           if similarity > 0.7:  # Threshold
               recurrence[i, j] = similarity
   ```
   
   **Performance Note**: For very long songs (>10min), this O(n²) operation can be slow. Consider:
   - Using sparse matrix representation
   - Sliding window approach (only compare nearby frames)
   - Downsampling chroma features before clustering

3. **Apply agglomerative clustering**:
   ```python
   from sklearn.cluster import AgglomerativeClustering
   
   clustering = AgglomerativeClustering(
       n_clusters=8,
       linkage='ward',
       metric='euclidean'
   )
   labels = clustering.fit_predict(recurrence)
   ```

4. **Convert frame labels to time segments**:
   ```python
   # Map cluster labels to time
   frame_times = librosa.frames_to_time(np.arange(num_frames), sr=sr)
   
   # Group consecutive frames with same label
   segments = []
   current_label = labels[0]
   start_frame = 0
   
   for i, label in enumerate(labels[1:], 1):
       if label != current_label:
           segments.append({
               'label': current_label,
               'start': frame_times[start_frame],
               'end': frame_times[i-1]
           })
           start_frame = i
           current_label = label
   ```

5. **Enforce minimum segment duration** (5 seconds):
   ```python
   min_duration = 5.0
   merged_segments = []
   
   for seg in segments:
       duration = seg['end'] - seg['start']
       if duration < min_duration:
           # Merge with next segment
           if merged_segments:
               merged_segments[-1]['end'] = seg['end']
       else:
           merged_segments.append(seg)
   ```

6. **Classify segments using heuristics**:
   ```python
   for i, seg in enumerate(segments):
       energy = calculate_energy(seg)  # From audio
       
       if i == 0 and energy < 0.4:
           seg['type'] = 'intro'
       elif energy > 0.7 and has_repeated_pattern(seg, segments):
           seg['type'] = 'chorus'
       elif 0.4 <= energy <= 0.7 and duration > 10:
           seg['type'] = 'verse'
       elif is_middle_section(i, len(segments)) and energy_differs(seg, surrounding):
           seg['type'] = 'bridge'
       elif i == len(segments) - 1 and energy < 0.5:
           seg['type'] = 'outro'
       else:
           seg['type'] = 'verse'  # Default
   ```

**Output**: `List[SongStructure]` with type, start, end, energy

### Fallback Strategy

**When fallback triggers**:
- Clustering fails (exception)
- <3 segments after merging

**Fallback algorithm**:
```python
# Uniform segmentation
num_segments = 8
segment_duration = total_duration / num_segments

segments = []
for i in range(num_segments):
    segments.append({
        'type': 'verse',
        'start': i * segment_duration,
        'end': (i + 1) * segment_duration,
        'energy': 0.5  # Medium energy
    })
```

**Metadata flag**: `fallbacks_used: ["structure_analysis"]`

### Edge Cases

- **Songs with no clear structure**: Use uniform segmentation fallback
- **Very short songs (<15s)**: Reduce to 3-4 segments
- **Songs with many sections**: Fixed 8 clusters may merge similar sections

### Performance Target

<15s for 3-minute song

---

## Component 3: Lyrics Extraction (`lyrics_extraction.py`)

**Purpose**: Extract lyrics with word-level timestamps for visual context.

### Algorithm Details

**OpenAI Whisper API integration**:

1. **Prepare audio file**:
   - Ensure audio is in supported format (MP3, WAV, FLAC)
   - If needed, convert using `soundfile` or `librosa`

2. **Budget check** (before API call):
   ```python
   from shared.cost_tracking import CostTracker
   from shared.errors import BudgetExceededError
   
   cost_tracker = CostTracker()
   estimated_cost = (duration_seconds / 60.0) * 0.006
   
   can_proceed = await cost_tracker.check_budget(
       job_id, 
       estimated_cost, 
       limit=get_budget_limit()
   )
   if not can_proceed:
       raise BudgetExceededError("Budget exceeded before Whisper API call")
   ```

3. **Call Whisper API** (with retry - decorator supports async):
   ```python
   from shared.retry import retry_with_backoff
   from shared.errors import RetryableError
   from openai import OpenAI
   from shared.config import settings
   
   @retry_with_backoff(max_attempts=3, base_delay=2)
   async def call_whisper_api(audio_file_path: str):
       """
       Call Whisper API with retry logic.
       
       Note: @retry_with_backoff decorator fully supports async functions.
       """
       client = OpenAI(api_key=settings.OPENAI_API_KEY)
       
       try:
           with open(audio_file_path, 'rb') as f:
               response = await client.audio.transcriptions.create(
                   model="whisper-1",
                   file=f,
                   response_format="verbose_json",
                   timestamp_granularities=["word"]
               )
           return response
       except Exception as e:
           # Convert API errors to RetryableError for retry decorator
           if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
               raise RetryableError(f"Whisper API error: {str(e)}") from e
           raise
   ```

4. **Parse response**:
   ```python
   lyrics = []
   for word in response.words:
       lyrics.append({
           'text': word.word,
           'timestamp': word.start  # Word start time in seconds
       })
   ```

5. **Track cost** (after success):
   ```python
   actual_cost = (duration_seconds / 60.0) * 0.006
   await cost_tracker.track_cost(
       job_id,
       "audio_parser",
       "whisper",
       actual_cost
   )
   ```

**Output**: `List[Lyric]` with text and timestamp

### Retry Logic

- **Max attempts**: 3
- **Backoff**: Exponential (2s, 4s, 8s)
- **Retry on**: `RetryableError` (API rate limits, timeouts)
- **Don't retry on**: `BudgetExceededError`, `ValidationError`

### Fallback Strategy

**When fallback triggers**:
- Whisper API fails after 3 retries
- Budget exceeded

**Fallback algorithm**:
```python
# Return empty lyrics array
lyrics = []
confidence = 0.0
```

**Metadata flag**: `fallbacks_used: ["lyrics_extraction"]`

**Note**: Fallback always succeeds (instrumental tracks are valid)

### Edge Cases

- **Instrumental tracks**: Empty lyrics array (valid)
- **Non-English lyrics**: Whisper handles automatically (may be less accurate)
- **Very long songs (>10min)**: May need chunking (post-MVP)

### Performance Target

<30s for 3-minute song (Whisper API dependent)

### Cost

~$0.006 per minute of audio (Whisper API pricing)

---

## Component 4: Mood Classification (`mood_classifier.py`)

**Purpose**: Determine emotional tone for style decisions.

### Algorithm Details

**Rule-based classification** (simple, fast for MVP):

1. **Extract features** (reuse chroma from structure analysis if available):
   ```python
   # Energy: Mean RMS energy from structure analysis segments
   energy_mean = np.mean([seg.energy for seg in song_structure])
   
   # Spectral Centroid: Mean frequency (brightness indicator)
   spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
   centroid_mean = np.mean(spectral_centroid)
   
   # Spectral Rolloff: Frequency below which 85% of energy is contained
   spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr)[0]
   rolloff_mean = np.mean(spectral_rolloff)
   
   # Chroma: Reuse from structure analysis if available, otherwise compute
   # Note: Structure analysis already computes chroma, so reuse it to avoid redundant computation
   if hasattr(structure_analysis_result, 'chroma_features'):
       chroma = structure_analysis_result.chroma_features
   else:
       chroma = librosa.feature.chroma(y=audio, sr=sr)
   chroma_variance = np.var(chroma)
   ```
   
   **Performance Optimization**: Reuse chroma features from structure analysis to avoid redundant computation.

2. **Calculate rule match scores**:
   ```python
   scores = {
       'energetic': 0.0,
       'calm': 0.0,
       'dark': 0.0,
       'bright': 0.0
   }
   
   # Energetic: BPM >120 AND energy_mean >0.6 AND spectral_centroid >3000 Hz
   if bpm > 120 and energy_mean > 0.6 and centroid_mean > 3000:
       scores['energetic'] = min(1.0, (bpm/200) * (energy_mean/1.0) * (centroid_mean/5000))
   
   # Calm: BPM <90 AND energy_mean <0.4 AND spectral_rolloff <4000 Hz
   if bpm < 90 and energy_mean < 0.4 and rolloff_mean < 4000:
       scores['calm'] = min(1.0, ((90-bpm)/90) * ((0.4-energy_mean)/0.4) * ((4000-rolloff_mean)/4000))
   
   # Dark: Energy_mean <0.5 AND spectral_centroid <2500 Hz
   if energy_mean < 0.5 and centroid_mean < 2500:
       scores['dark'] = min(1.0, ((0.5-energy_mean)/0.5) * ((2500-centroid_mean)/2500))
   
   # Bright: Energy_mean >0.5 AND spectral_centroid >3500 Hz
   if energy_mean > 0.5 and centroid_mean > 3500:
       scores['bright'] = min(1.0, ((energy_mean-0.5)/0.5) * ((centroid_mean-3500)/3500))
   ```

3. **Select primary and secondary moods**:
   ```python
   primary_mood = max(scores, key=scores.get)
   primary_score = scores[primary_mood]
   
   # Remove primary from consideration
   scores.pop(primary_mood)
   secondary_mood = max(scores, key=scores.get) if scores else None
   secondary_score = scores.get(secondary_mood, 0.0)
   
   # Only set secondary if score >0.3
   if secondary_score < 0.3:
       secondary_mood = None
   ```

4. **Set energy level**:
   ```python
   if bpm > 120 and energy_mean > 0.6:
       energy_level = "high"
   elif bpm < 90:
       energy_level = "low"
   else:
       energy_level = "medium"
   ```

5. **Calculate confidence**:
   ```python
   confidence = primary_score
   ```

**Output**: `Mood` object with primary, secondary, energy_level, confidence

### Fallback Strategy

**When fallback triggers**:
- Feature extraction fails
- All scores <0.3

**Fallback algorithm**:
```python
primary_mood = "energetic"
secondary_mood = None
energy_level = "medium"
confidence = 0.5
```

**Metadata flag**: `fallbacks_used: ["mood_classification"]`

### Edge Cases

- **Ambiguous moods**: Low confidence scores, may default to fallback
- **Mixed genres**: Primary mood selected, secondary may be set

### Performance Target

<1s (rule-based, very fast)

---

## Component 5: Clip Boundaries (`boundaries.py`)

**Purpose**: Generate initial clip boundaries aligned to beats.

### Algorithm Details

**Beat-aligned boundaries with edge case handling**:

**Algorithm Overview**:
1. Handle very short songs (<12s) → Create 3 equal segments
2. Handle no beats → Use tempo-based fallback
3. Create beat-aligned boundaries with 4-8s duration
4. Ensure minimum 3 clips
5. Enforce maximum clips (default: 20)

**Step-by-Step Implementation**:

```python
import math
import numpy as np
from typing import List
from shared.models.audio import ClipBoundary

def generate_boundaries(
    beat_timestamps: List[float], 
    bpm: float, 
    total_duration: float,
    max_clips: int = 20
) -> List[ClipBoundary]:
    """
    Generate clip boundaries aligned to beats.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        bpm: Beats per minute
        total_duration: Total audio duration in seconds
        max_clips: Maximum number of clips (default: 20)
        
    Returns:
        List of ClipBoundary objects
    """
    # Edge case 1: Very short songs (<12s) → 3 equal segments
    if total_duration < 12.0:
        segment_duration = total_duration / 3.0
        return [
            ClipBoundary(
                start=i * segment_duration,
                end=(i + 1) * segment_duration if i < 2 else total_duration,
                duration=segment_duration if i < 2 else (total_duration - 2 * segment_duration)
            )
            for i in range(3)
        ]
    
    # Edge case 2: No beats detected → Use tempo-based fallback
    if len(beat_timestamps) == 0:
        beat_interval = 60.0 / bpm
        boundaries = []
        current_time = 0.0
        while current_time < total_duration and len(boundaries) < max_clips:
            end_time = min(current_time + (4 * beat_interval), total_duration)
            boundaries.append(ClipBoundary(
                start=current_time,
                end=end_time,
                duration=end_time - current_time
            ))
            current_time = end_time
        
        # Ensure minimum 3 clips
        if len(boundaries) < 3:
            return _create_equal_segments(total_duration, 3)
        
        return boundaries[:max_clips]
    
    # Normal case: Beat-aligned boundaries
    target_duration = 6.0  # Middle of 4-8s range
    beat_interval = np.mean(np.diff(beat_timestamps)) if len(beat_timestamps) > 1 else (60.0 / bpm)
    beats_per_clip = max(1, math.ceil(target_duration / beat_interval))
    
    boundaries = []
    current_beat_idx = 0
    
    while current_beat_idx < len(beat_timestamps) and len(boundaries) < max_clips:
        start = beat_timestamps[current_beat_idx]
        end_idx = min(current_beat_idx + beats_per_clip, len(beat_timestamps) - 1)
        end = beat_timestamps[end_idx]
        duration = end - start
        
        # Adjust duration to fit 4-8s range
        if duration < 4.0:
            # Extend to next beats (up to 8s max)
            while end_idx < len(beat_timestamps) - 1 and duration < 8.0:
                end_idx += 1
                end = beat_timestamps[end_idx]
                duration = end - start
                if duration >= 8.0:
                    break
        elif duration > 8.0:
            # Find nearest beat to 8s mark
            target_end = start + 8.0
            nearest_idx = min(
                range(current_beat_idx, len(beat_timestamps)),
                key=lambda i: abs(beat_timestamps[i] - target_end)
            )
            end = beat_timestamps[nearest_idx]
            duration = end - start
        
        boundaries.append(ClipBoundary(
            start=start,
            end=end,
            duration=duration
        ))
        
        current_beat_idx = end_idx + 1
    
    # Ensure minimum 3 clips
    if len(boundaries) < 3:
        return _create_equal_segments(total_duration, 3)
    
    # Trim last clip to end if needed
    if boundaries[-1].end < total_duration:
        boundaries[-1].end = total_duration
        boundaries[-1].duration = boundaries[-1].end - boundaries[-1].start
    
    return boundaries[:max_clips]

def _create_equal_segments(duration: float, num_segments: int) -> List[ClipBoundary]:
    """Create equal-length segments."""
    segment_duration = duration / num_segments
    return [
        ClipBoundary(
            start=i * segment_duration,
            end=(i + 1) * segment_duration if i < num_segments - 1 else duration,
            duration=segment_duration if i < num_segments - 1 else (duration - (num_segments - 1) * segment_duration)
        )
        for i in range(num_segments)
    ]
```

**Output**: `List[ClipBoundary]` with start, end, duration

### Edge Cases

- **Song <12s**: Create 3 equal segments (ignore beats)
- **Beat interval >8s**: Split at 8s, align to nearest beat
- **Variable tempo**: Use average beat interval (may cause slight misalignment)
- **No beats detected**: Use tempo-based fallback (4-beat intervals)

### Fallback Strategy

**When fallback triggers**:
- Beat detection failed (using tempo-based fallback)

**Fallback algorithm**:
```python
# Tempo-based boundaries (4-beat intervals)
beat_interval = 60.0 / bpm
boundaries = []
current_time = 0.0

while current_time < total_duration:
    end_time = min(current_time + (4 * beat_interval), total_duration)
    boundaries.append({
        'start': current_time,
        'end': end_time,
        'duration': end_time - current_time
    })
    current_time = end_time

# Ensure minimum 3 clips
if len(boundaries) < 3:
    # Create 3 equal segments
    segment_duration = total_duration / 3
    boundaries = [
        {'start': 0, 'end': segment_duration, 'duration': segment_duration},
        {'start': segment_duration, 'end': 2*segment_duration, 'duration': segment_duration},
        {'start': 2*segment_duration, 'end': total_duration, 'duration': total_duration - 2*segment_duration}
    ]
```

### Performance Target

<1s (simple algorithm)

---

## Component 6: Caching (`cache.py`)

**Purpose**: Cache analysis results by file hash to avoid redundant processing.

### Strategy Details

**Redis-only for MVP** (simple, fast) with cache-before-download optimization:

- **Cache Key**: `videogen:cache:audio_cache:{md5_hash}`
- **TTL**: 86400 seconds (24 hours)
- **Value**: JSON-serialized `AudioAnalysis` object

### Cache Flow (Optimized)

1. **Try to extract hash from URL first**:
   ```python
   file_hash = extract_hash_from_url(audio_url)
   if file_hash:
       # Check cache before downloading
       cached = await get_cached_analysis(file_hash)
       if cached:
           return cached  # Skip download entirely
   ```

2. **Download audio file** (if hash not in URL or cache miss):
   ```python
   audio_bytes = await download_audio_file(audio_url)
   ```

3. **Calculate MD5 hash** of file bytes:
   ```python
   if not file_hash:
       file_hash = calculate_file_hash(audio_bytes)
       # Check cache again (in case hash wasn't in URL)
       cached = await get_cached_analysis(file_hash)
       if cached:
           return cached
   ```

4. **Process audio** (if not cached):
   ```python
   analysis = await parse_audio(audio_bytes, job_id)
   ```

5. **Store in cache** (non-blocking):
   ```python
   await store_cached_analysis(file_hash, analysis, ttl=86400)
   ```

### Implementation

```python
from shared.redis_client import RedisClient
import json
from typing import Optional
from shared.models.audio import AudioAnalysis
import re

redis_client = RedisClient()

async def get_cached_analysis(file_hash: str) -> Optional[AudioAnalysis]:
    """Get cached analysis by file hash."""
    cache_key = f"videogen:cache:audio_cache:{file_hash}"
    cached_data = await redis_client.get(cache_key)
    
    if cached_data:
        return AudioAnalysis.model_validate_json(cached_data)
    return None

async def store_cached_analysis(file_hash: str, analysis: AudioAnalysis, ttl: int = 86400):
    """Store analysis in cache."""
    cache_key = f"videogen:cache:audio_cache:{file_hash}"
    cached_data = analysis.model_dump_json()
    await redis_client.set(cache_key, cached_data, ttl=ttl)

def extract_hash_from_url(audio_url: str) -> Optional[str]:
    """
    Try to extract MD5 hash from Supabase Storage URL.
    
    Note: Supabase Storage URLs typically don't include file hashes in the URL.
    This function attempts to extract hash if present in URL parameters or path,
    but will return None if hash is not available (which is the common case).
    
    Args:
        audio_url: Supabase Storage URL
        
    Returns:
        MD5 hash if found in URL, None otherwise
    """
    # Supabase Storage URLs format:
    # https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
    # or
    # https://<project>.supabase.co/storage/v1/object/sign/<bucket>/<path>?token=...
    
    # Check for hash in URL parameters (if Supabase adds it in future)
    if 'hash=' in audio_url:
        match = re.search(r'hash=([a-f0-9]{32})', audio_url)
        if match:
            return match.group(1)
    
    # Check for hash in path (unlikely but possible)
    hash_match = re.search(r'([a-f0-9]{32})', audio_url)
    if hash_match:
        # Only return if it looks like an MD5 hash (32 hex chars)
        potential_hash = hash_match.group(1)
        if len(potential_hash) == 32:
            return potential_hash
    
    # Default: Hash not in URL, will be calculated after download
    return None
```

### Edge Cases

- **Hash not in URL**: Download first, then calculate hash and check cache
  - This is the common case (Supabase URLs don't include hashes)
  - Hash is calculated from file bytes after download
- **Cache miss**: Process audio, store in cache (non-blocking write)
- **Redis unavailable**: Log warning, continue without cache (non-blocking)
  - Cache failures should not fail the request
  - Processing continues normally without caching

### Performance Target

Cache hit: <1s  
Cache miss: Full processing time (no overhead)

---

## Component Dependencies

**Execution Order**:
1. Beat Detection (independent)
2. Structure Analysis (uses beat detection results for energy calculation)
3. Lyrics Extraction (independent, can run in parallel with structure)
4. Mood Classification (uses BPM, structure energy, spectral features)
5. Clip Boundaries (uses beat timestamps, duration)
6. Caching (wraps all components)

**Data Flow**:
```
Beat Detection → beat_timestamps, bpm
    ↓
Structure Analysis → song_structure (with energy)
    ↓
Mood Classification → mood (uses bpm, energy, spectral features)
    ↓
Clip Boundaries → clip_boundaries (uses beat_timestamps)
    ↓
Lyrics Extraction → lyrics (independent)
    ↓
All → AudioAnalysis object → Caching
```

---

**Document Status:** Ready for Implementation  
**Next Steps:** 
1. Review [Overview & Integration](./PRD_audio_parser_overview.md) for architecture
2. Follow [Implementation Guide](./PRD_audio_parser_implementation.md) for step-by-step instructions

