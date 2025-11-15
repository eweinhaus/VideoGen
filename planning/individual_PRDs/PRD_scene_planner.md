# Scene Planner Module - Implementation PRD

**Version:** 1.0 | **Date:** December 2025  
**Module:** Module 4 (Scene Planner)  
**Phase:** Phase 3  
**Status:** Implementation-Ready

---

## Executive Summary

This document provides a complete implementation guide for the Scene Planner module, which generates comprehensive video plans using music video director knowledge. The module transforms audio analysis data and user prompts into professional video scripts with characters, scenes, clip descriptions, transitions, and visual style guidelines. It serves as the creative foundation for all downstream video generation modules.

**Timeline:** 8-10 hours  
**Dependencies:** Phase 0 shared components, Audio Parser (Module 3) output  
**Output:** ScenePlan Pydantic model conforming to `shared/models/scene.py`  
**LLM:** OpenAI GPT-4o or Claude 3.5 Sonnet (with retry logic)

---

## Directory Structure

```
backend/modules/scene_planner/
├── __init__.py                 # Module exports
├── main.py                     # Main entry point, FastAPI router integration
├── planner.py                  # Core scene planning orchestration
├── llm_client.py               # LLM API integration (OpenAI/Claude)
├── director_knowledge.py       # Director knowledge base (for prompt context)
├── script_generator.py         # Clip script generation logic
├── transition_planner.py       # Transition planning based on beat intensity
├── style_analyzer.py           # Style consistency analysis
├── validator.py                # Output validation and refinement
├── tests/
│   ├── __init__.py
│   ├── test_planner.py          # Main planner integration tests
│   ├── test_llm_client.py       # LLM API integration tests
│   ├── test_script_generator.py # Script generation tests
│   ├── test_transitions.py     # Transition planning tests
│   ├── test_style_analyzer.py  # Style analysis tests
│   ├── test_validator.py       # Validation tests
│   └── fixtures/
│       ├── sample_audio_analysis.json  # Mock AudioAnalysis data
│       └── sample_scene_plan.json      # Expected output examples
└── README.md                   # Module documentation
```

---

## File Specifications

### `__init__.py`
**Purpose:** Module exports and public API

**Exports:**
- `plan_scenes` function (main entry point)
- `ScenePlanner` class (if using class-based approach)
- All exception classes from this module

**Implementation Notes:**
- Export only public API functions
- Import shared utilities (errors, logging, models) at module level
- Define module-level logger using `get_logger("scene_planner")`

---

### `main.py`
**Purpose:** FastAPI router integration and job processing entry point

**Function: `process_scene_planning`**
- **Input:** `job_id: UUID`, `user_prompt: str`, `audio_data: AudioAnalysis`
- **Output:** `ScenePlan` Pydantic model
- **Purpose:** Main entry point called by API Gateway orchestrator
- **Logic:**
  1. Validate inputs using shared validation utilities
  2. Load director knowledge from `director_knowledge.py`
  3. Call `plan_scenes` function with inputs and director knowledge
  4. Validate output against ScenePlan Pydantic model
  5. Track cost using cost_tracker (LLM API calls)
  6. Return ScenePlan model
- **Error Handling:**
  - Raise `ValidationError` for invalid inputs
  - Raise `GenerationError` for LLM failures
  - Wrap LLM calls with retry decorator
  - Log all errors with job_id context

---

### `planner.py`
**Purpose:** Core orchestration of scene planning steps

**Function: `plan_scenes`**
- **Input:** `job_id: UUID`, `user_prompt: str`, `audio_data: AudioAnalysis`, `director_knowledge: str`
- **Output:** `ScenePlan` Pydantic model
- **Purpose:** Coordinate all planning steps and assemble final result
- **Logic:**
  1. Analyze audio data: Extract mood, structure, beats, lyrics
  2. Generate video summary: High-level narrative overview
  3. Generate characters: Main and supporting characters
  4. Generate scenes: Locations and settings
  5. Generate style guide: Color palette, lighting, cinematography
  6. Generate clip scripts: Detailed visual descriptions for each clip boundary
  7. Plan transitions: Cut/crossfade/fade based on beat intensity
  8. Validate consistency: Ensure characters/scenes/style align across clips
  9. Assemble ScenePlan model with all results
  10. Return ScenePlan

**Error Handling:**
- Catch LLM API errors → Retry with exponential backoff
- If LLM fails after retries → Use fallback simple scene descriptions
- Log all fallback scenarios with warning level

---

### `llm_client.py`
**Purpose:** LLM API integration with retry logic

**Function: `generate_scene_plan`**
- **Input:** `system_prompt: str`, `user_prompt: str`, `audio_context: dict`, `job_id: UUID`
- **Output:** `dict` (JSON response from LLM)
- **Purpose:** Call LLM API to generate scene plan JSON
- **Logic:**
  1. **Prepare prompt:**
     - Combine system prompt (director knowledge) with user prompt
     - Include audio analysis context (BPM, mood, structure, lyrics, clip boundaries)
     - Request JSON output matching ScenePlan schema
  2. **Call LLM API:**
     - **OpenAI GPT-4o:** Use `openai.ChatCompletion.create()` with `response_format={"type": "json_object"}`
     - **Claude 3.5 Sonnet:** Use Anthropic API with JSON mode
     - Model: GPT-4o (preferred) or Claude 3.5 Sonnet (fallback)
     - Temperature: 0.7 (creative but consistent)
     - Max tokens: 4000 (sufficient for full scene plan)
     - Timeout: 90 seconds
  3. **Parse response:**
     - Extract JSON from LLM response
     - Validate JSON structure
     - Return parsed dict
  4. **Error handling:**
     - Wrap API call with `@retry_with_backoff` decorator (3 attempts, 2s base delay)
     - On `RetryableError`: Retry with exponential backoff
     - On permanent failure: Raise `GenerationError`
     - Track cost: ~$0.05 per job (GPT-4o) or ~$0.03 (Claude 3.5 Sonnet)

**Function: `_calculate_llm_cost`**
- **Input:** `model: str`, `input_tokens: int`, `output_tokens: int` | **Output:** `Decimal`
- Calculate cost based on model pricing:
  - GPT-4o: $0.005 per 1K input tokens, $0.015 per 1K output tokens
  - Claude 3.5 Sonnet: $0.003 per 1K input tokens, $0.015 per 1K output tokens

---

### `director_knowledge.py`
**Purpose:** Music video director knowledge base for LLM prompt context

**Function: `get_director_knowledge`**
- **Input:** None | **Output:** `str` (formatted knowledge text)
- **Purpose:** Return comprehensive director knowledge for system prompt
- **Content:** See "Director Knowledge Base" section below

**Structure:**
- Visual metaphors and symbolism
- Color palette guidelines by mood
- Camera movement techniques by energy level
- Transition styles by beat intensity
- Lighting techniques by mood
- Cinematography principles
- Character and scene planning principles

---

### `script_generator.py`
**Purpose:** Generate detailed clip scripts from LLM output

**Function: `generate_clip_scripts`**
- **Input:** `llm_output: dict`, `clip_boundaries: List[ClipBoundary]`, `lyrics: List[Lyric]`
- **Output:** `List[ClipScript]`
- **Purpose:** Transform LLM output into structured clip scripts
- **Logic:**
  1. Extract clip scripts from LLM JSON response
  2. Align scripts to clip boundaries (start/end times)
  3. Match lyrics to clips based on timestamps
  4. Ensure each clip has: visual_description, motion, camera_angle, characters, scenes
  5. Validate clip scripts match boundaries count
  6. Return list of ClipScript objects

**Function: `_align_lyrics_to_clip`**
- **Input:** `clip_start: float`, `clip_end: float`, `lyrics: List[Lyric]` | **Output:** `Optional[str]`
- Find lyrics within clip time range, return combined text or None

---

### `transition_planner.py`
**Purpose:** Plan transitions between clips based on beat intensity

**Function: `plan_transitions`**
- **Input:** `clip_scripts: List[ClipScript]`, `beat_timestamps: List[float]`, `song_structure: List[SongStructure]`
- **Output:** `List[Transition]`
- **Purpose:** Generate transition plan between clips
- **Logic:**
  1. For each adjacent clip pair (i, i+1):
     - Analyze beat intensity at transition point
     - Check song structure (chorus → verse, verse → chorus, etc.)
     - Determine transition type:
       - **Hard cut (0s):** Strong beat, high energy, chorus transitions
       - **Crossfade (0.5s):** Medium beat, continuous motion, verse transitions
       - **Fade (0.5s):** Soft beat, low energy, intro/outro transitions
     - Generate rationale explaining transition choice
  2. Return list of Transition objects

**Function: `_get_beat_intensity_at_time`**
- **Input:** `timestamp: float`, `beat_timestamps: List[float]`, `window: float = 0.5` | **Output:** `Literal["low", "medium", "high"]`
- Count beats within window around timestamp, classify intensity

---

### `style_analyzer.py`
**Purpose:** Analyze and ensure style consistency

**Function: `analyze_style_consistency`**
- **Input:** `scene_plan: ScenePlan` | **Output:** `bool`
- **Purpose:** Validate style consistency across all clips
- **Logic:**
  1. Check color palette consistency (same palette referenced in all clips)
  2. Check character consistency (same character descriptions across clips)
  3. Check scene consistency (same scene IDs referenced appropriately)
  4. Check cinematography consistency (similar camera styles)
  5. Return True if consistent, False if inconsistencies found

**Function: `refine_style`**
- **Input:** `scene_plan: ScenePlan` | **Output:** `ScenePlan`
- **Purpose:** Refine style guide to ensure consistency
- **Logic:**
  1. If inconsistencies found, adjust style guide
  2. Update clip scripts to reference consistent style elements
  3. Return refined ScenePlan

---

### `validator.py`
**Purpose:** Validate and refine ScenePlan output

**Function: `validate_scene_plan`**
- **Input:** `scene_plan: ScenePlan`, `audio_data: AudioAnalysis` | **Output:** `ScenePlan`
- **Purpose:** Validate ScenePlan against audio data and fix issues
- **Logic:**
  1. **Validate clip boundaries:**
     - Ensure clip scripts match clip_boundaries count from audio_data
     - Ensure start/end times align with boundaries (±0.5s tolerance)
     - If mismatch: Adjust clip scripts to match boundaries
  2. **Validate transitions:**
     - Ensure transitions match clip count (N-1 transitions for N clips)
     - Ensure transition from_clip/to_clip indices are valid
  3. **Validate characters/scenes:**
     - Ensure all referenced character IDs exist in characters list
     - Ensure all referenced scene IDs exist in scenes list
  4. **Validate style:**
     - Ensure color_palette has at least 3 colors
     - Ensure all required style fields are present
  5. Return validated ScenePlan

---

## Director Knowledge Base

**Purpose:** Comprehensive music video director knowledge for LLM system prompt

**Content Structure:**

### Visual Metaphors & Symbolism
- Use visual metaphors to represent lyrical themes (e.g., "loneliness" → empty spaces, "freedom" → open landscapes)
- Symbolic objects can reinforce narrative (e.g., mirrors for self-reflection, clocks for time)
- Color symbolism: Red (passion, danger), Blue (calm, sadness), Yellow (joy, energy), Black (mystery, darkness)

### Color Palette Guidelines by Mood
- **Energetic:** Vibrant, saturated colors (reds, oranges, yellows, electric blues)
- **Calm:** Muted, desaturated colors (soft blues, greens, pastels)
- **Dark:** Low saturation, high contrast (blacks, deep purples, dark blues)
- **Bright:** High brightness, pastel or neon colors (whites, light blues, pinks)

### Camera Movement Techniques by Energy Level
- **High Energy (BPM >130, high energy):**
  - Fast cuts, handheld camera with shake
  - Tracking shots, dolly movements
  - Low angles for power, high angles for vulnerability
  - Quick zooms, whip pans
- **Medium Energy (BPM 90-130, medium energy):**
  - Steady tracking shots, smooth pans
  - Medium shots, balanced framing
  - Slow push-ins, pull-outs
- **Low Energy (BPM <90, low energy):**
  - Static shots, minimal movement
  - Wide shots, slow zooms
  - High angles, contemplative framing

### Transition Styles by Beat Intensity
- **Hard Cut (0s duration):**
  - Strong beats, high energy sections
  - Chorus transitions, dramatic moments
  - Beat-synchronized cuts for impact
- **Crossfade (0.5s duration):**
  - Medium beats, continuous motion
  - Verse transitions, narrative flow
  - Smooth scene changes
- **Fade (0.5s duration):**
  - Soft beats, low energy sections
  - Intro/outro transitions
  - Emotional, contemplative moments

### Lighting Techniques by Mood
- **Dark Mood:**
  - Low-key lighting, high contrast
  - Shadows, silhouettes
  - Single source lighting (practical lights, neon)
  - Color temperature: Cool (blue/cyan)
- **Bright Mood:**
  - High-key lighting, low contrast
  - Soft, diffused light
  - Multiple sources, even illumination
  - Color temperature: Warm (orange/yellow)
- **Energetic Mood:**
  - Dynamic lighting, color shifts
  - Neon, practical lights
  - Strobing effects (sparingly)
  - High contrast, saturated colors

### Cinematography Principles
- **Rule of Thirds:** Place subjects off-center for visual interest
- **Leading Lines:** Use lines (roads, buildings) to guide viewer's eye
- **Depth:** Create depth with foreground/background elements
- **Framing:** Use natural frames (doorways, windows) to focus attention
- **Movement:** Camera movement should match music rhythm (fast cuts for fast beats)

### Character Planning Principles
- **Main Character:** Should appear in 60-80% of clips for narrative consistency
- **Supporting Characters:** 1-2 supporting characters maximum to avoid confusion
- **Character Consistency:** Same appearance, clothing, style across all clips
- **Character Arc:** Consider visual progression (e.g., character starts alone, ends with others)

### Scene Planning Principles
- **Scene Variety:** Use 2-4 distinct scenes to maintain interest without confusion
- **Scene Transitions:** Plan scene changes at structural boundaries (verse → chorus)
- **Scene Consistency:** Same location should have consistent lighting, color palette
- **Location Logic:** Scenes should make narrative sense (e.g., don't jump from desert to arctic)

### Clip Script Structure
Each clip script should include:
- **Visual Description:** What's happening in the clip (1-2 sentences)
- **Motion:** How elements move (character walking, camera tracking, etc.)
- **Camera Angle:** Shot type (wide, medium, close-up, low angle, high angle)
- **Characters:** Which characters appear (reference character IDs)
- **Scenes:** Which scene location (reference scene ID)
- **Lyrics Context:** Relevant lyrics during this clip (if available)
- **Beat Intensity:** Low/medium/high (for transition planning)

---

## Integration Points

### Shared Components Usage

**config.py:**
- Access OpenAI API key: `settings.openai_api_key`
- Access Anthropic API key: `settings.anthropic_api_key` (if using Claude)
- Access LLM model preference: `settings.llm_model` ("gpt-4o" or "claude-3-5-sonnet")

**models/scene.py:**
- Import ScenePlan, Character, Scene, Style, ClipScript, Transition models
- All functions return these Pydantic models

**models/audio.py:**
- Receive AudioAnalysis model as input
- Extract: bpm, duration, beat_timestamps, song_structure, lyrics, mood, clip_boundaries

**retry.py:**
- Decorate LLM API calls: `@retry_with_backoff(max_attempts=3, base_delay=2)`
- Only retries on RetryableError exceptions

**cost_tracking.py:**
- Track LLM API costs: `cost_tracker.track_cost(job_id, stage="scene_planning", api_name="gpt-4o", cost=...)`
- Calculate cost from token usage: ~$0.05 per job (GPT-4o) or ~$0.03 (Claude 3.5 Sonnet)

**logging.py:**
- Use module logger: `logger = get_logger("scene_planner")`
- Include job_id in all log entries
- Log processing time, LLM token usage, validation results

**errors.py:**
- Raise `GenerationError` for LLM failures
- Raise `ValidationError` for invalid inputs
- Raise `RetryableError` for transient API failures

### API Gateway Integration

**Orchestrator Call:**
```python
from modules.scene_planner.main import process_scene_planning

scene_plan = await process_scene_planning(
    job_id=job_id,
    user_prompt=user_prompt,
    audio_data=audio_data  # AudioAnalysis from Module 3
)
```

**Progress Updates:**
- Update progress: 15% (start), 18% (LLM call), 20% (complete)
- Publish events: "Starting scene planning...", "Generating video plan...", "Scene planning complete!"

---

## Error Handling Patterns

**Input Validation:**
- Validate job_id is valid UUID
- Validate user_prompt is 50-500 characters
- Validate audio_data is valid AudioAnalysis model
- Raise ValidationError immediately (no retries)

**LLM API Errors:**
- LLM timeout → Retry with exponential backoff (3 attempts)
- LLM rate limit → Retry with exponential backoff
- LLM invalid JSON → Retry with exponential backoff
- LLM permanent error → Use fallback simple scene descriptions

**Fallback Strategy:**
- If LLM fails after all retries:
  1. Generate simple scene plan based on audio mood/energy
  2. Create 1-2 basic characters (from user prompt)
  3. Create 1-2 basic scenes (from user prompt)
  4. Generate simple clip scripts aligned to boundaries
  5. Use default transitions (crossfade for all)
  6. Set basic style (color palette from mood, simple lighting)
  7. Log warning: "LLM failed, using fallback scene plan"

**Validation Errors:**
- Clip scripts don't match boundaries → Adjust scripts to match boundaries
- Missing characters/scenes → Add default entries
- Invalid transitions → Regenerate transitions

---

## Testing Requirements

### Unit Tests

**test_llm_client.py:**
- Test OpenAI API call returns valid JSON
- Test Claude API call returns valid JSON
- Test retry logic: 3 attempts with exponential backoff on failures
- Test cost calculation: Token usage → cost conversion
- Test timeout handling: 90s timeout per request
- Mock LLM responses with valid ScenePlan JSON

**test_script_generator.py:**
- Test clip script generation from LLM output
- Test alignment to clip boundaries
- Test lyrics matching to clips
- Test edge cases: No lyrics, single clip, many clips

**test_transitions.py:**
- Test transition planning based on beat intensity
- Test transition type selection (cut/crossfade/fade)
- Test transition count (N-1 for N clips)
- Test edge cases: Single clip (no transitions), many clips

**test_style_analyzer.py:**
- Test style consistency checking
- Test style refinement when inconsistencies found
- Test color palette validation

**test_validator.py:**
- Test clip boundary validation
- Test character/scene reference validation
- Test style validation
- Test transition validation

### Integration Tests

**test_planner.py:**
- Test full planning pipeline with real audio data
- Test LLM integration (with mocked API responses)
- Test fallback scenario: LLM fails, fallback used
- Test validation: Invalid output corrected
- Test cost tracking: Costs tracked accurately
- Test with various audio types: Energetic, calm, dark, bright
- Test with various clip counts: 3 clips, 6 clips, 10 clips

**Test Fixtures:**
- Energetic audio (high BPM, high energy, clear structure)
- Calm audio (low BPM, low energy, minimal structure)
- Dark audio (low spectral centroid, moody)
- Bright audio (high spectral centroid, uplifting)
- Audio with lyrics, audio without lyrics

---

## Success Criteria

✅ Scene plan generated for all clips  
✅ Style consistent across clips  
✅ Clip scripts align to beat boundaries (±0.5s)  
✅ Director knowledge applied (color, camera, transitions)  
✅ Valid JSON output (ScenePlan Pydantic model)  
✅ Auto-retry: 3 attempts for LLM with exponential backoff (2s, 4s, 8s)  
✅ Fallback: Simple scene descriptions if LLM fails  
✅ Processing time: <30 seconds for 6-clip video  
✅ Cost: ~$0.05 per job (GPT-4o) or ~$0.03 (Claude 3.5 Sonnet)  
✅ Test coverage: 80%+ code coverage

---

## Implementation Notes

**LLM Configuration:**
- Model: GPT-4o (preferred) or Claude 3.5 Sonnet (fallback)
- Temperature: 0.7 (creative but consistent)
- Max tokens: 4000 (sufficient for full scene plan)
- Response format: JSON object (enforced by API)
- Timeout: 90 seconds per request

**Prompt Engineering:**
- System prompt: Director knowledge (comprehensive, ~2000 words)
- User prompt: User's creative prompt (50-500 chars)
- Audio context: BPM, mood, structure, lyrics, clip boundaries (structured JSON)
- Output format: Explicit JSON schema matching ScenePlan model

**Performance Optimization:**
- Single LLM call for entire scene plan (more efficient than per-clip calls)
- Cache director knowledge (load once, reuse)
- Parallel validation (validate multiple aspects simultaneously)

**Boundary Alignment:**
- Scene Planner receives clip_boundaries from Audio Parser
- Clip scripts must align to these boundaries (±0.5s tolerance)
- Scene Planner can refine boundaries within ±2s for narrative needs (future enhancement)

---

**Document Status:** Ready for Implementation  
**Next Action:** Begin implementation starting with `director_knowledge.py` and `llm_client.py`, then implement `planner.py` and supporting modules

