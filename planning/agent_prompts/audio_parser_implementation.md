# Audio Parser Module Implementation Prompt

Implement Module 3 (Audio Parser) for the AI Music Video Generation Pipeline. Follow the detailed implementation PRD located at `planning/individual_PRDs/PRD_audio_parser.md`.

**Context:** This module performs comprehensive audio analysis to extract beats, tempo, song structure, lyrics, mood, and clip boundaries. It serves as the foundation for all downstream creative decisions in the music video generation pipeline. The module is completely independent and can be built in parallel with other Phase 2 modules.

**Requirements:**
- Implement all files in `backend/modules/audio_parser/` according to the PRD directory structure
- Use Librosa + Aubio for beat detection with ±50ms precision requirement
- Integrate OpenAI Whisper API for lyrics extraction with word-level timestamps
- Implement Redis caching with 24-hour TTL using MD5 file hashes
- Generate beat-aligned clip boundaries (4-8s clips, minimum 3)
- Integrate with Phase 0 shared components (config, database, redis, storage, models, retry, cost_tracking, logging, errors, validation)
- Implement all fallback strategies for beat detection, lyrics, and structure analysis failures
- Write comprehensive unit, integration, and performance tests per PRD testing requirements

**Key Implementation Details:**
- Main entry point: `process_audio_analysis(job_id: UUID, audio_url: str)` in `main.py`
- Core orchestration: `parse_audio()` function in `parser.py` coordinates all analysis steps
- Beat detection: Merge librosa and aubio results, deduplicate within 50ms threshold
- Structure analysis: Chroma features → recurrence matrix → agglomerative clustering → heuristic classification
- Mood classification: Rule-based using BPM, energy, spectral features
- Output: Return `AudioAnalysis` Pydantic model conforming to `shared/models/audio.py`

**Dependencies:** Phase 0 shared components must be complete. No dependency on API Gateway or other Phase 2 modules. Can be tested in isolation with audio files.

**Deliverables:** Complete implementation with all files, tests, and documentation. Ensure code follows PRD logic specifications without making architectural decisions.

