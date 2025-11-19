# Module 3: Audio Parser

**Tech Stack:** Python (Librosa + Aubio + OpenAI Whisper)  
**Status:** ✅ Implemented

## Purpose
Comprehensive audio analysis to extract beats (±50ms precision), song structure, lyrics, and mood. Provides creative foundation for all downstream decisions.

## Key Features
- **Beat Detection** (Librosa + Aubio, 90%+ accuracy within ±50ms)
- **Tempo (BPM)** extraction (60-200 range)
- **Song Structure** classification (intro/verse/chorus/bridge/outro)
- **Lyrics extraction** (OpenAI Whisper API with word-level timestamps)
- **Mood classification** (energetic, calm, dark, bright)
- **Clip Boundaries** (beat-aligned, 4-8s clips, minimum 3)
- **Caching** (Redis cache by audio file hash, 24h TTL)

## Architecture

### Core Files
- `main.py` - FastAPI router integration, main entry point `process_audio_analysis()`
- `parser.py` - Core orchestration function `parse_audio()` coordinating all analysis steps
- `beat_detection.py` - Librosa + Aubio beat detection with deduplication
- `structure_analysis.py` - Chroma features → recurrence matrix → clustering → classification
- `mood_classifier.py` - Rule-based mood classification using BPM, energy, spectral features
- `whisper_client.py` - OpenAI Whisper API integration with retry logic
- `boundaries.py` - Beat-aligned clip boundary generation (4-8s clips, min 3)
- `cache.py` - Redis and database caching utilities
- `utils.py` - Audio file download, hash calculation, validation

### Integration Points
- Uses shared components: `config`, `database`, `redis`, `storage`, `models`, `retry`, `cost_tracking`, `logging`, `errors`, `validation`
- Returns `AudioAnalysis` Pydantic model from `shared/models/audio.py`
- Caches results in Redis (`videogen:audio_cache:{hash}`) and database (`audio_analysis_cache` table)

## Fallback Strategies
- **Beat detection fails** → Use tempo-based boundaries (4-beat intervals), confidence=0.5
- **Lyrics extraction fails** → Return empty array (instrumental track), set `fallback_used.lyrics=True`
- **Structure analysis fails** → Use single-segment structure (verse, medium energy)
- **Low confidence** → Proceed with best-effort results, flag in metadata

## Usage

```python
from modules.audio_parser.main import process_audio_analysis
from uuid import UUID

# Process audio analysis
job_id = UUID("...")
audio_url = "https://storage.supabase.co/object/public/audio-uploads/path/to/audio.mp3"

analysis = await process_audio_analysis(job_id, audio_url)

# Access results
print(f"BPM: {analysis.bpm}")
print(f"Duration: {analysis.duration}s")
print(f"Beats: {len(analysis.beat_timestamps)}")
print(f"Segments: {len(analysis.song_structure)}")
print(f"Lyrics: {len(analysis.lyrics)} words")
print(f"Mood: {analysis.mood.primary}")
print(f"Clip boundaries: {len(analysis.clip_boundaries)}")
```

## Testing

Run tests with:
```bash
cd project/backend
pytest modules/audio_parser/tests/ -v
```

Test coverage includes:
- Unit tests for each component (beat detection, structure, mood, boundaries, cache, whisper)
- Integration tests for full parsing pipeline
- Fallback scenario tests
- Error handling tests

## Performance Targets
- Process 3-minute song in < 60 seconds (target: 45-60s)
- Cache lookup in < 10ms
- Beat detection accuracy: 90%+ beats within ±50ms
- BPM accuracy: ±2 BPM for 80%+ songs
- Structure classification: 70%+ accurate segment boundaries
- Lyrics extraction: >70% word accuracy

## Dependencies
- `librosa>=0.10.1` - Audio analysis
- `soundfile>=0.12.1` - Audio I/O
- `numpy>=1.24.0` - Numerical operations
- `scipy>=1.11.0` - Signal processing
- `scikit-learn>=1.3.0` - Clustering for structure analysis
- `openai>=1.3.0` - Whisper API
- `aubio` - Optional (fallback to librosa onset detection if unavailable)

