# Module 3: Audio Parser - Implementation Guide

**Version:** 2.0 | **Date:** November 15, 2025  
**Related PRDs:**
- [Overview & Integration](./PRD_audio_parser_overview.md) - High-level architecture and integration points
- [Component Specifications](./PRD_audio_parser_components.md) - Detailed technical specs for each component

---

## Getting Started (For Junior Engineers)

### Prerequisites

Before starting, ensure you have:
1. ✅ Python 3.9+ installed
2. ✅ Virtual environment activated (`source venv/bin/activate`)
3. ✅ All dependencies installed (`pip install -r requirements.txt`)
4. ✅ Environment variables configured (`.env` file with Supabase, Redis, OpenAI keys)
5. ✅ Redis running (local or cloud instance)
6. ✅ Supabase project set up with database migrations applied

### Current Status

**Important**: The audio parser module is **fully implemented** and exists in `project/backend/modules/audio_parser/`. 

**What needs to be done**:
- ✅ All components are implemented (beat detection, structure analysis, lyrics, mood, boundaries, caching)
- ⏳ **Orchestrator integration**: Replace the stub in `orchestrator.py` (lines 174-205) with actual integration code
- ⏳ **Testing**: Verify end-to-end flow works correctly

### Quick Start Checklist

1. [ ] Verify audio parser module exists: `ls project/backend/modules/audio_parser/`
2. [ ] Review existing implementation: Read `main.py` and `parser.py`
3. [ ] Replace orchestrator stub (see Phase 4 below)
4. [ ] Test integration: Upload audio file via API and verify processing
5. [ ] Verify progress updates appear in frontend

### Common Pitfalls to Avoid

1. **Type Mismatch**: Orchestrator passes `job_id` as `str`, but `process_audio_analysis()` expects `UUID`. Convert: `UUID(job_id)`
2. **Progress Updates**: Progress updates are sent by the **orchestrator**, not by the audio parser module itself
3. **Error Handling**: Don't catch exceptions in the audio parser - let them propagate to orchestrator
4. **Database Storage**: Use `audio_data.model_dump()` (not `model_dump_json()`) for JSONB column
5. **Import Path**: Use `from modules.audio_parser.main import process_audio_analysis` (not `from audio_parser.main`)

---

## Implementation Timeline

**Total Time:** 14-20 hours (2-3 days)  
**Team Size:** 1-2 developers

**Schedule:**
- **Day 1 Morning**: Phase 0-1 (Models, Foundation)
- **Day 1 Afternoon**: Phase 2 (Core Components)
- **Day 2 Morning**: Phase 3 (Lyrics & Caching)
- **Day 2 Afternoon**: Phase 4 (Orchestrator Integration)
- **Day 2 Evening**: Phase 5 (Testing & Validation)

---

## Phase 0: Model Creation (Before Phase 1)

**Estimated Time:** 1-2 hours  
**Prerequisites:** None

### Step 1: Create Audio Models

**File**: `project/backend/shared/models/audio.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from enum import Enum

class SongStructureType(str, Enum):
    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"

class EnergyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class SongStructure(BaseModel):
    type: SongStructureType
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., gt=0, description="End time in seconds")
    energy: EnergyLevel

class Lyric(BaseModel):
    text: str
    timestamp: float = Field(..., ge=0, description="Word start time in seconds")

class Mood(BaseModel):
    primary: str = Field(..., description="Primary mood (energetic, calm, dark, bright)")
    secondary: Optional[str] = Field(None, description="Secondary mood if confidence >0.3")
    energy_level: EnergyLevel
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")

class ClipBoundary(BaseModel):
    start: float = Field(..., ge=0, description="Clip start time in seconds")
    end: float = Field(..., gt=0, description="Clip end time in seconds")
    duration: float = Field(..., ge=4, le=8, description="Clip duration in seconds (4-8s)")

class AudioAnalysis(BaseModel):
    job_id: UUID
    bpm: float = Field(..., ge=60, le=200, description="Beats per minute")
    duration: float = Field(..., gt=0, description="Audio duration in seconds")
    beat_timestamps: List[float] = Field(..., description="Beat timestamps in seconds")
    song_structure: List[SongStructure] = Field(..., min_length=1, description="Song sections")
    lyrics: List[Lyric] = Field(default_factory=list, description="Lyrics with timestamps")
    mood: Mood
    clip_boundaries: List[ClipBoundary] = Field(..., min_length=3, description="Clip boundaries (min 3)")
    metadata: dict = Field(default_factory=dict, description="Processing metadata")
```

### Step 2: Add AudioAnalysisError

**File**: `project/backend/shared/errors.py`

```python
class AudioAnalysisError(PipelineError):
    """Raised when audio analysis fails."""
    
    def __init__(self, message: str, job_id: Optional[str] = None):
        super().__init__(message, job_id=job_id)
        self.error_type = "AUDIO_ANALYSIS_ERROR"
```

### Step 3: Update Model Exports

**File**: `project/backend/shared/models/__init__.py`

```python
from .audio import (
    SongStructure,
    Lyric,
    Mood,
    ClipBoundary,
    AudioAnalysis,
    SongStructureType,
    EnergyLevel
)

__all__ = [
    # ... existing exports ...
    "SongStructure",
    "Lyric",
    "Mood",
    "ClipBoundary",
    "AudioAnalysis",
    "SongStructureType",
    "EnergyLevel",
]
```

### Step 4: Test Model Creation

**File**: `project/backend/shared/tests/test_models.py`

```python
def test_audio_analysis_model():
    """Test AudioAnalysis model creation and validation."""
    analysis = AudioAnalysis(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        bpm=128.5,
        duration=185.3,
        beat_timestamps=[0.5, 1.0, 1.5],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=8.5, energy="low")
        ],
        lyrics=[],
        mood=Mood(primary="energetic", energy_level="high", confidence=0.85),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=5.2, duration=5.2),
            ClipBoundary(start=5.2, end=10.5, duration=5.3),
            ClipBoundary(start=10.5, end=15.8, duration=5.3)
        ]
    )
    assert analysis.bpm == 128.5
    assert len(analysis.clip_boundaries) >= 3
```

**Checklist:**
- [ ] `audio.py` created with all models
- [ ] `AudioAnalysisError` added to `errors.py`
- [ ] Models exported in `__init__.py`
- [ ] Tests pass
- [ ] Models validate correctly

---

## Phase 1: Foundation & Integration (Day 1 - Morning)

**Estimated Time:** 2-3 hours  
**Prerequisites:** Phase 0 complete

### Step 1: Create Module Directory Structure

```bash
mkdir -p project/backend/modules/audio_parser
touch project/backend/modules/audio_parser/__init__.py
touch project/backend/modules/audio_parser/main.py
touch project/backend/modules/audio_parser/parser.py
```

### Step 2: Review `main.py` Entry Point

**File**: `project/backend/modules/audio_parser/main.py`

**Note**: This file already exists and is fully implemented. Review it to ensure it matches the specification in [Overview PRD](./PRD_audio_parser_overview.md#1-orchestrator-integration).

```python
"""
Main entry point for audio analysis.

FastAPI router integration and job processing entry point.
"""

import time
from typing import Optional
from uuid import UUID

from shared.models.audio import AudioAnalysis
from shared.errors import ValidationError, AudioAnalysisError
from shared.logging import get_logger, set_job_id

from modules.audio_parser.parser import parse_audio
from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis
from modules.audio_parser.utils import (
    download_audio_file,
    validate_audio_file,
    calculate_file_hash,
    extract_hash_from_url
)

logger = get_logger("audio_parser")


async def process_audio_analysis(job_id: UUID, audio_url: str) -> AudioAnalysis:
    """
    Main entry point called by API Gateway orchestrator.
    
    Args:
        job_id: Job ID
        audio_url: URL or path to audio file in storage
        
    Returns:
        AudioAnalysis model
        
    Raises:
        ValidationError: If inputs are invalid
        AudioAnalysisError: If processing fails
    """
    set_job_id(job_id)
    start_time = time.time()
    
    try:
        # Validate inputs
        if not job_id:
            raise ValidationError("job_id is required", job_id=job_id)
        if not audio_url:
            raise ValidationError("audio_url is required", job_id=job_id)
        
        # Try to extract hash from URL to check cache before downloading
        file_hash = extract_hash_from_url(audio_url)
        if file_hash:
            cached_analysis = await get_cached_analysis(file_hash)
            if cached_analysis is not None:
                logger.info(f"Cache hit for job {job_id}")
                cached_analysis.metadata["cache_hit"] = True
                cached_analysis.metadata["processing_time"] = time.time() - start_time
                cached_analysis.job_id = job_id
                return cached_analysis
        
        # Download audio file
        audio_bytes = await download_audio_file(audio_url)
        
        # Calculate MD5 hash if not extracted from URL
        if not file_hash:
            file_hash = calculate_file_hash(audio_bytes)
            cached_analysis = await get_cached_analysis(file_hash)
            if cached_analysis is not None:
                logger.info(f"Cache hit for job {job_id} (after download)")
                cached_analysis.metadata["cache_hit"] = True
                cached_analysis.metadata["processing_time"] = time.time() - start_time
                cached_analysis.job_id = job_id
                return cached_analysis
        
        # Validate audio file
        validate_audio_file(audio_bytes, max_size_mb=10)
        
        # Parse audio
        analysis = await parse_audio(audio_bytes, job_id)
        
        # Store in cache (non-blocking)
        try:
            await store_cached_analysis(file_hash, analysis, ttl=86400)
        except Exception as e:
            logger.warning(f"Failed to store cache: {str(e)}")
        
        # Set metadata
        analysis.metadata["processing_time"] = time.time() - start_time
        analysis.metadata["cache_hit"] = False
        
        return analysis
        
    except ValidationError:
        raise
    except AudioAnalysisError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in audio analysis: {str(e)}")
        raise AudioAnalysisError(f"Failed to process audio analysis: {str(e)}", job_id=job_id) from e
```

### Step 3: Review `parser.py` Implementation

**File**: `project/backend/modules/audio_parser/parser.py`

**Note**: This file already exists and is fully implemented. Review it to ensure it orchestrates all components correctly.

**What to verify**:
- ✅ Imports all component functions (beat_detection, structure_analysis, lyrics_extraction, mood_classifier, boundaries)
- ✅ Loads audio using librosa
- ✅ Calls each component in correct order
- ✅ Handles errors appropriately
- ✅ Returns complete `AudioAnalysis` object

**Note**: The parser does NOT send progress updates - that's handled by the orchestrator. The parser only processes audio and returns results.

### Step 4: Integrate with Orchestrator

**File**: `project/backend/api_gateway/orchestrator.py` (replace lines 174-205)

**Current State**: Orchestrator has a stub that fails with "Audio parser module not implemented". 

**Required**: Replace the stub with the implementation from [Overview PRD](./PRD_audio_parser_overview.md#1-orchestrator-integration).

**Note**: The audio parser module is fully implemented, so the orchestrator stub should be replaced with the actual integration code.

### Step 5: Test Integration

```python
# Test that orchestrator can import and call module
from modules.audio_parser.main import process_audio_analysis

# Should not raise ImportError
```

**Checklist:**
- [ ] Module directory structure created
- [ ] `main.py` entry point implemented
- [ ] `parser.py` skeleton created
- [ ] Orchestrator integration updated
- [ ] Import test passes
- [ ] No syntax errors

---

## Phase 2: Core Components (Day 1 - Afternoon)

**Estimated Time:** 4-5 hours  
**Prerequisites:** Phase 1 complete

### Implementation Order

1. **Beat Detection** (`beat_detection.py`)
2. **Structure Analysis** (`structure_analysis.py`)
3. **Mood Classification** (`mood_classifier.py`)
4. **Clip Boundaries** (`boundaries.py`)

See [Component Specifications](./PRD_audio_parser_components.md) for detailed implementation of each component.

### Step 1: Implement Beat Detection

**File**: `project/backend/modules/audio_parser/beat_detection.py`

Follow the algorithm and code example from [Component Specifications](./PRD_audio_parser_components.md#component-1-beat-detection-beat_detectionpy).

### Step 2: Review Structure Analysis

**File**: `project/backend/modules/audio_parser/structure_analysis.py`

**Note**: File exists and is fully implemented. Review it to ensure it matches the algorithm in [Component Specifications](./PRD_audio_parser_components.md#component-2-structure-analysis-structure_analysispy).

**Key Points to Verify**:
- Uses fixed 8 clusters (not dynamic)
- Performance note: O(n²) recurrence matrix for long songs (>10min may be slow)
- Fallback to uniform segmentation if clustering fails

### Step 3: Implement Mood Classification

**File**: `project/backend/modules/audio_parser/mood_classifier.py`

Follow the algorithm from [Component Specifications](./PRD_audio_parser_components.md#component-4-mood-classification-mood_classifierpy).

### Step 4: Implement Clip Boundaries

**File**: `project/backend/modules/audio_parser/boundaries.py`

Follow the algorithm from [Component Specifications](./PRD_audio_parser_components.md#component-5-clip-boundaries-boundariespy).

### Step 5: Update `parser.py` to Orchestrate Components

**File**: `project/backend/modules/audio_parser/parser.py`

```python
import librosa
import soundfile as sf
import io
from uuid import UUID

from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

from modules.audio_parser.beat_detection import detect_beats
from modules.audio_parser.structure_analysis import analyze_structure
from modules.audio_parser.mood_classifier import classify_mood
from modules.audio_parser.boundaries import generate_boundaries

logger = get_logger("audio_parser")


async def parse_audio(audio_bytes: bytes, job_id: UUID) -> AudioAnalysis:
    """
    Parse audio file and extract all analysis data.
    """
    # Load audio
    audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
    duration = len(audio) / sr
    
    # 1. Beat Detection
    bpm, beat_timestamps, beat_confidence = detect_beats(audio, sr)
    
    # 2. Structure Analysis
    song_structure = analyze_structure(audio, sr, beat_timestamps)
    
    # 3. Mood Classification (uses BPM, structure energy, spectral features)
    mood = classify_mood(audio, sr, bpm, song_structure)
    
    # 4. Clip Boundaries (uses beat timestamps, duration)
    clip_boundaries = generate_boundaries(beat_timestamps, bpm, duration)
    
    # 5. Lyrics (will be added in Phase 3)
    lyrics = []
    
    # Create AudioAnalysis object
    analysis = AudioAnalysis(
        job_id=job_id,
        bpm=bpm,
        duration=duration,
        beat_timestamps=beat_timestamps,
        song_structure=song_structure,
        lyrics=lyrics,
        mood=mood,
        clip_boundaries=clip_boundaries,
        metadata={
            "beat_detection_confidence": beat_confidence,
            "fallbacks_used": []
        }
    )
    
    return analysis
```

### Step 6: Test Each Component

Create unit tests for each component (see Testing Requirements below).

**Checklist:**
- [ ] Beat detection implemented and tested
- [ ] Structure analysis implemented and tested
- [ ] Mood classification implemented and tested
- [ ] Clip boundaries implemented and tested
- [ ] `parser.py` orchestrates all components
- [ ] All components return correct data types
- [ ] Fallbacks work correctly

---

## Phase 3: Lyrics & Caching (Day 2 - Morning)

**Estimated Time:** 3-4 hours  
**Prerequisites:** Phase 2 complete

### Step 1: Implement Lyrics Extraction

**File**: `project/backend/modules/audio_parser/lyrics_extraction.py`

Follow the algorithm from [Component Specifications](./PRD_audio_parser_components.md#component-3-lyrics-extraction-lyrics_extractionpy).

**Key Points:**
- Budget check before API call
- Retry logic with exponential backoff
- Cost tracking after success
- Fallback to empty lyrics array

### Step 2: Implement Caching

**File**: `project/backend/modules/audio_parser/cache.py`

Follow the implementation from [Component Specifications](./PRD_audio_parser_components.md#component-6-caching-cachepy).

### Step 3: Review Utilities

**File**: `project/backend/modules/audio_parser/utils.py`

**Note**: File exists and is fully implemented. Review it to ensure it matches the specification.

**Key Functions to Verify**:
- `download_audio_file()`: Downloads from Supabase Storage with retry logic
- `calculate_file_hash()`: Calculates MD5 hash from file bytes
- `extract_hash_from_url()`: Attempts to extract hash from URL (returns None if not available - common case)
- `validate_audio_file()`: Validates file size (format validation happens in API Gateway)

**Implementation Reference**: See [Component Specifications](./PRD_audio_parser_components.md#component-6-caching-cachepy) for `extract_hash_from_url()` implementation details.

### Step 4: Integrate Lyrics into `parser.py`

Update `parser.py` to call lyrics extraction:

```python
from modules.audio_parser.lyrics_extraction import extract_lyrics

# In parse_audio():
lyrics = await extract_lyrics(audio_bytes, job_id, duration)
```

### Step 5: Test Lyrics & Caching

- Test lyrics extraction with real audio
- Test cache hit/miss scenarios
- Test cost tracking
- Test budget enforcement

**Checklist:**
- [ ] Lyrics extraction implemented
- [ ] Caching implemented
- [ ] Utilities implemented
- [ ] Cost tracking integrated
- [ ] Budget checks work
- [ ] Cache hit/miss tested
- [ ] Retry logic tested

---

## Phase 4: Orchestrator Integration (Day 2 - Afternoon)

**Estimated Time:** 2-3 hours  
**Prerequisites:** Phase 3 complete

### Step 1: Update Orchestrator

Replace orchestrator stub with full implementation (see Phase 1, Step 4).

### Step 2: Add Progress Updates (In Orchestrator, Not Parser)

**Important**: Progress updates are sent by the **orchestrator**, not by the audio parser module. The parser is a pure processing module.

The orchestrator should send progress updates after calling each component. However, since the parser processes all components internally, the orchestrator can only send updates at the start and end:

```python
# In orchestrator.py, after calling process_audio_analysis():
# Progress updates are sent by orchestrator, not by parser
await publish_event(job_id, "message", {
    "text": "Audio analysis complete",
    "stage": "audio_parser"
})
await update_progress(job_id, 10, "audio_parser")
```

**Note**: If you need granular progress updates (2%, 4%, 6%, etc.), you would need to modify `parser.py` to accept a progress callback function, but this is not required for MVP.

### Step 3: Add Error Handling

Ensure all errors are properly raised and handled by orchestrator.

### Step 4: Test End-to-End via API Gateway

**Testing Steps**:

1. **Start Services**:
   ```bash
   # Terminal 1: Start API Gateway
   cd project/backend
   uvicorn api_gateway.main:app --reload --port 8000
   
   # Terminal 2: Start Worker
   python -m api_gateway.worker
   ```

2. **Upload Audio via API**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/upload-audio \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -F "audio_file=@test_audio.mp3" \
     -F "user_prompt=Create a cyberpunk music video"
   ```

3. **Verify Processing**:
   - Check worker logs for audio parser execution
   - Verify no errors in logs
   - Check job status: `GET /api/v1/jobs/{job_id}`

4. **Verify Results**:
   - Check database: `jobs.audio_data` column should contain JSON
   - Verify `AudioAnalysis` object structure
   - Check Redis cache: `videogen:cache:audio_cache:{hash}`

5. **Verify Progress Updates** (if frontend connected):
   - Connect to SSE stream: `GET /api/v1/jobs/{job_id}/stream`
   - Verify `stage_update` and `progress` events received

**Expected Results**:
- ✅ Job status changes from "queued" → "processing" → "completed"
- ✅ `audio_data` column populated with `AudioAnalysis` JSON
- ✅ No errors in logs
- ✅ Cache entry created in Redis

**Checklist:**
- [ ] Orchestrator stub replaced with actual integration code
- [ ] Type conversion: `UUID(job_id)` before calling `process_audio_analysis()`
- [ ] Database storage: `audio_data.model_dump()` used (not `model_dump_json()`)
- [ ] Error handling: Exceptions propagate to `handle_pipeline_error()`
- [ ] Progress updates sent by orchestrator (not parser)
- [ ] End-to-end test passes (upload → processing → results in database)
- [ ] Cache works (second upload of same file should hit cache)
- [ ] Frontend receives progress updates (if connected)

---

## Phase 5: Testing & Validation (Day 2 - Evening)

**Estimated Time:** 3-4 hours  
**Prerequisites:** Phase 4 complete

### Unit Tests

**File**: `project/backend/modules/audio_parser/tests/test_beat_detection.py`

```python
import pytest
import numpy as np
from modules.audio_parser.beat_detection import detect_beats

def test_beat_detection_normal():
    """Test beat detection with normal audio."""
    # Create synthetic audio with clear beats
    sr = 22050
    duration = 10.0
    bpm = 120
    beat_interval = 60.0 / bpm
    
    # Generate audio with beats
    t = np.linspace(0, duration, int(sr * duration))
    audio = np.sin(2 * np.pi * 440 * t)  # Simple tone
    
    bpm_result, beats, confidence = detect_beats(audio, sr)
    
    assert 60 <= bpm_result <= 200
    assert len(beats) > 0
    assert 0 <= confidence <= 1

def test_beat_detection_fallback():
    """Test beat detection fallback."""
    # Test with audio that should trigger fallback
    pass
```

**Create similar test files for:**
- `test_structure_analysis.py`
- `test_mood_classifier.py`
- `test_boundaries.py`
- `test_lyrics_extraction.py` (with mocks)
- `test_cache.py`

### Integration Tests

**File**: `project/backend/modules/audio_parser/tests/test_parser.py`

```python
import pytest
from modules.audio_parser.parser import parse_audio

@pytest.mark.asyncio
async def test_parse_audio_full_flow():
    """Test full parse_audio flow."""
    # Load test audio file
    with open("test_audio.mp3", "rb") as f:
        audio_bytes = f.read()
    
    analysis = await parse_audio(audio_bytes, job_id=UUID("test-id"))
    
    assert analysis.bpm > 0
    assert len(analysis.beat_timestamps) > 0
    assert len(analysis.song_structure) > 0
    assert len(analysis.clip_boundaries) >= 3
```

### End-to-End Tests

Test via API Gateway:
- Upload audio
- Verify job creation
- Verify processing
- Verify results in database
- Verify progress updates

### Manual Testing

**Test Cases:**
1. **Electronic (128 BPM, 3min)**: Should detect beats, structure, mood
2. **Acoustic (70 BPM, 2min)**: Should work with slower tempo
3. **Instrumental (no lyrics)**: Should return empty lyrics array
4. **Short song (15s)**: Should create minimum 3 clips
5. **Long song (10min)**: Should handle without OOM

**Checklist:**
- [ ] Unit tests for all components
- [ ] Integration tests for full flow
- [ ] End-to-end tests via API Gateway
- [ ] Manual testing with diverse genres
- [ ] Performance validation (<60s for 3min song)
- [ ] Error scenarios tested
- [ ] Cost tracking verified

---

## Testing Requirements

### Unit Tests

**Requirements per component:**
- Test normal operation
- Test fallback scenarios
- Test edge cases
- Mock external dependencies (Whisper API, storage)
- Assert correct output types

**Test Coverage Target:** 80%+

### Integration Tests

**Requirements:**
- Test full `parse_audio()` flow
- Test caching (hit and miss)
- Test database storage
- Test cost tracking
- Test error propagation

### End-to-End Tests

**Requirements:**
- Upload audio via API Gateway
- Verify job processing
- Verify results in database
- Verify progress updates in frontend
- Verify error handling

### Manual Testing

**Test Scenarios:**
- Diverse genres (electronic, rock, jazz, ambient, instrumental)
- Different song lengths (30s, 3min, 10min)
- Error scenarios (invalid file, API failure, budget exceeded)
- Performance validation

---

## Dependencies

### Python Packages

```bash
pip install librosa>=0.10.1
pip install soundfile>=0.12.1
pip install numpy>=1.24.0
pip install scipy>=1.11.0
pip install scikit-learn>=1.3.0
pip install openai>=1.3.0
```

**Add to**: `project/backend/requirements.txt`

### Shared Components (Already Built)

- `shared.config` - Environment variables
- `shared.database` - Database client
- `shared.redis_client` - Redis client
- `shared.storage` - Storage client
- `shared.cost_tracking` - Cost tracker
- `shared.logging` - Structured logging
- `shared.retry` - Retry decorator
- `shared.errors` - Error classes
- `shared.models` - Pydantic models (to be created in Phase 0)

---

## Code Patterns & Examples

### Error Handling Pattern

```python
from shared.errors import AudioAnalysisError, RetryableError

try:
    result = some_operation()
except RetryableError as e:
    # Will be retried by retry decorator
    raise
except Exception as e:
    # Convert to AudioAnalysisError
    raise AudioAnalysisError(f"Operation failed: {str(e)}", job_id=job_id) from e
```

### Cost Tracking Pattern

```python
from shared.cost_tracking import CostTracker
from shared.errors import BudgetExceededError

cost_tracker = CostTracker()

# Before API call
estimated_cost = calculate_estimated_cost()
can_proceed = await cost_tracker.check_budget(job_id, estimated_cost, limit)
if not can_proceed:
    raise BudgetExceededError("Budget exceeded")

# After successful API call
actual_cost = calculate_actual_cost()
await cost_tracker.track_cost(job_id, "audio_parser", "whisper", actual_cost)
```

### Progress Update Pattern

```python
from api_gateway.services.event_publisher import publish_event

# Send progress update
await publish_event(job_id, "message", {
    "text": "Beats detected",
    "stage": "audio_parser"
})

# Update progress percentage
await update_progress(job_id, 2, "audio_parser")
```

### Caching Pattern

```python
from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis

# Check cache
cached = await get_cached_analysis(file_hash)
if cached:
    return cached

# Process (if not cached)
result = await process()

# Store in cache (non-blocking)
try:
    await store_cached_analysis(file_hash, result, ttl=86400)
except Exception as e:
    logger.warning(f"Cache write failed: {e}")
    # Continue - cache failure shouldn't fail request
```

### Retry Pattern

```python
from shared.retry import retry_with_backoff
from shared.errors import RetryableError

# Note: @retry_with_backoff fully supports async functions
@retry_with_backoff(max_attempts=3, base_delay=2)
async def call_external_api():
    """
    Call external API with retry logic.
    
    The retry decorator automatically detects async functions and handles them correctly.
    """
    try:
        response = await api_client.call()
        return response
    except RateLimitError as e:
        raise RetryableError("Rate limit exceeded") from e
    except TimeoutError as e:
        raise RetryableError("Request timeout") from e
```

---

## File Structure

```
project/backend/modules/audio_parser/
├── __init__.py
├── main.py                    # Entry point
├── parser.py                  # Core orchestration
├── beat_detection.py          # Beat detection component
├── structure_analysis.py      # Structure analysis component
├── lyrics_extraction.py       # Lyrics extraction component
├── mood_classifier.py         # Mood classification component
├── boundaries.py              # Clip boundaries component
├── cache.py                   # Caching helpers
├── utils.py                   # Utility functions
└── tests/
    ├── __init__.py
    ├── test_beat_detection.py
    ├── test_structure_analysis.py
    ├── test_mood_classifier.py
    ├── test_boundaries.py
    ├── test_lyrics_extraction.py
    ├── test_cache.py
    └── test_parser.py
```

---

## Troubleshooting Guide

### Common Issues

1. **ImportError: No module named 'modules.audio_parser'**
   - **Solution**: Ensure you're running from `project/backend/` directory
   - **Fix**: `cd project/backend && python -m api_gateway.worker`

2. **TypeError: process_audio_analysis() got unexpected keyword argument 'job_id'**
   - **Solution**: Convert `job_id` from `str` to `UUID`: `UUID(job_id)`

3. **AttributeError: 'AudioAnalysis' object has no attribute 'model_dump'**
   - **Solution**: Use Pydantic v2 syntax: `audio_data.model_dump()` (not `dict(audio_data)`)

4. **Redis Connection Error**
   - **Solution**: Ensure Redis is running: `redis-cli ping` should return `PONG`
   - **Fix**: Check `REDIS_URL` in `.env` file

5. **Whisper API Error: Rate limit exceeded**
   - **Solution**: Retry logic should handle this automatically (3 attempts with backoff)
   - **Check**: Verify `OPENAI_API_KEY` is set correctly

6. **Database Error: column "audio_data" does not exist**
   - **Solution**: Run migration: `supabase/migrations/20251115013200_add_audio_data.sql`
   - **Fix**: Apply migration via Supabase dashboard or CLI

7. **Cache Not Working**
   - **Solution**: Check Redis connection and key format
   - **Debug**: `redis-cli KEYS "videogen:cache:audio_cache:*"` should show cache entries

### Debugging Tips

1. **Enable Debug Logging**:
   ```python
   # In .env
   LOG_LEVEL=DEBUG
   ```

2. **Check Logs**:
   ```bash
   # Worker logs
   tail -f logs/app.log
   
   # API Gateway logs
   # Check terminal output
   ```

3. **Test Components Independently**:
   ```python
   # Test beat detection
   from modules.audio_parser.beat_detection import detect_beats
   import librosa
   audio, sr = librosa.load("test_audio.mp3")
   bpm, beats, confidence = detect_beats(audio, sr)
   print(f"BPM: {bpm}, Beats: {len(beats)}, Confidence: {confidence}")
   ```

4. **Verify Database Storage**:
   ```sql
   -- Check if audio_data is stored
   SELECT id, status, audio_data->>'bpm' as bpm 
   FROM jobs 
   WHERE id = 'your-job-id';
   ```

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

---

## Implementation Checklist

### Phase 0: Model Creation
- [ ] Create `shared/models/audio.py`
- [ ] Add `AudioAnalysisError` to `shared/errors.py`
- [ ] Update `shared/models/__init__.py`
- [ ] Test model creation

### Phase 1: Foundation & Integration
- [ ] Create module directory structure
- [ ] Create `main.py` entry point
- [ ] Create `parser.py` skeleton
- [ ] Integrate with orchestrator
- [ ] Test integration

### Phase 2: Core Components
- [ ] Implement `beat_detection.py`
- [ ] Implement `structure_analysis.py`
- [ ] Implement `mood_classifier.py`
- [ ] Implement `boundaries.py`
- [ ] Update `parser.py` to orchestrate
- [ ] Test each component

### Phase 3: Lyrics & Caching
- [ ] Implement `lyrics_extraction.py`
- [ ] Implement `cache.py`
- [ ] Implement `utils.py`
- [ ] Integrate lyrics into `parser.py`
- [ ] Test lyrics & caching

### Phase 4: Orchestrator Integration
- [ ] Update orchestrator
- [ ] Add progress updates
- [ ] Add error handling
- [ ] Test end-to-end

### Phase 5: Testing & Validation
- [ ] Unit tests for all components
- [ ] Integration tests
- [ ] End-to-end tests
- [ ] Manual testing
- [ ] Performance validation

---

**Document Status:** Ready for Implementation  
**Next Steps:** Begin with Phase 0 (Model Creation)

