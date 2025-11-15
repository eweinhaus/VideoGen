## Prompt Generator Module - Implementation PRD

**Version:** 1.0 | **Date:** November 2025  
**Module:** Module 6 (Prompt Generator)  
**Phase:** Phase 3  
**Status:** Implementation-Ready

---

## Executive Summary

This document specifies the Prompt Generator module, which synthesizes optimized text-to-video prompts for each clip in the music video. The module takes a `ScenePlan` (Module 4 output) and `ReferenceImages` (Module 5 output) and produces `ClipPrompts` (video prompt bundle) that combine clip scripts, visual style, and reference images into concise, consistent prompts suitable for text-to-video models.

**Role in Pipeline:**
- **Upstream inputs:** `ScenePlan` (clip scripts, style, transitions) and `ReferenceImages` (scene + character reference images).
- **Downstream consumer:** `Video Generator` (Module 7), which uses `ClipPrompts` to generate video clips.
- **Orchestrator stage:** `prompt_generator` at **40% progress** (after Reference Generator, before Video Generator).

**High-level requirements:**
- **Inputs:**  
  - `job_id: UUID` (pipeline job identifier)  
  - `plan: ScenePlan` (from `shared.models.scene`)  
  - `references: Optional[ReferenceImages]` (from `shared.models.scene`, may be `None` when Reference Generator fails or is skipped)
- **Output:**  
  - `ClipPrompts` (from `shared.models.video`) containing a list of `ClipPrompt` objects with:
    - `clip_index: int`  
    - `prompt: str` (optimized, \<200 words)  
    - `negative_prompt: str`  
    - `duration: float` (from clip script `end - start`)  
    - `scene_reference_url: Optional[str]`  
    - `character_reference_urls: List[str]`  
    - `metadata: Dict[str, Any]` with at least:
      - `word_count: int`  
      - `style_keywords: List[str]` (consistent across all prompts)  
      - `scene_id: Optional[str]`  
      - `character_ids: List[str]`  
      - `validated: bool`

**Performance & Cost Targets:**
- Generate prompts for all clips in **\<5 seconds** of wall-clock time for a typical 6–15 clip video (dominated by a single LLM call).
- Use **single-batch LLM generation as the primary path** (one call that produces all clip prompts).
- **Cost estimate:** ~$0.01–0.03 per job for typical 10-clip video:
  - Input tokens: ~2500–4000 (clip contexts, style, references)
  - Output tokens: ~1500–2500 (optimized prompts)
  - GPT-4o: $0.005/1K input + $0.015/1K output = ~$0.02–0.03
  - Claude 3.5 Sonnet: $0.003/1K input + $0.015/1K output = ~$0.01–0.02 (cheaper)
- Integrate cost tracking via `shared.cost_tracking`, budget-guarded by the orchestrator at the `prompt_generator` stage.
- **Timeout budget:** LLM call should complete within **90 seconds** (same as Scene Planner); deterministic fallback path must complete in \<5 seconds.

---

## Directory Structure

```text
backend/modules/prompt_generator/
├── __init__.py                 # Module exports
├── main.py                     # Main entry point, orchestrator-facing API
├── process.py                  # High-level process(job_id, plan, references) function
├── prompt_synthesizer.py       # Core prompt synthesis and formatting logic
├── style_synthesizer.py        # Style keyword extraction and consistency enforcement
├── reference_mapper.py         # Mapping from ScenePlan IDs → ReferenceImages URLs
├── validator.py                # Validation and normalization of ClipPrompts output
├── llm_client.py               # Primary LLM integration (batch prompt generation)
├── templates.py                # Deterministic prompt templates (fallback / base prompts)
├── tests/
│   ├── __init__.py
│   ├── test_process.py         # End-to-end module tests with mocks
│   ├── test_prompt_synthesizer.py
│   ├── test_style_synthesizer.py
│   ├── test_reference_mapper.py
│   ├── test_validator.py
│   ├── test_llm_client.py      # LLM logic, mocked API calls
│   └── fixtures/
│       ├── sample_scene_plan.json
│       ├── sample_reference_images.json
│       └── sample_clip_prompts.json
└── README.md                   # Module documentation and usage examples
```

---

## File Specifications

### `__init__.py`

**Purpose:** Define the module’s public API.

**Exports:**
- `process_prompts` (main high-level function, synonym for `process.process`)
- Any module-specific exception classes defined in this package.

**Notes:**
- Import and re-export `process` from `process.py`.
- Set up module-level logger via `get_logger("prompt_generator")`.

---

### `main.py`

**Purpose:** Provide a clear entry point for orchestrator and potential future FastAPI integration (if module ever exposed directly).

**Function: `async def process_prompt_generation(job_id: UUID, plan: ScenePlan, references: Optional[ReferenceImages]) -> ClipPrompts`**

**Inputs:**
- `job_id: UUID` – job identifier.
- `plan: ScenePlan` – validated scene plan from Scene Planner.
- `references: Optional[ReferenceImages]` – may be `None` if Reference Generator failed or is disabled (text-only mode).

**Output:**
- `ClipPrompts` Pydantic model (`shared.models.video.ClipPrompts`).

**Responsibilities:**
1. Validate inputs (`ScenePlan` and `ReferenceImages` types) or raise `ValidationError`.
2. Wrap call to `process.process(job_id, plan, references)` with:
   - Structured logging (`job_id`, clip count).
   - Cost tracking for LLM use, if `llm_client` path is enabled.
3. Return validated `ClipPrompts` model to orchestrator.

**Error Handling:**
- Raise `ValidationError` for malformed inputs.
- Propagate `GenerationError` from internal logic when prompt generation fails.
- Do not catch budget or pipeline-level errors (orchestrator handles these).

---

### `process.py`

**Purpose:** High-level orchestration for the Prompt Generator module, called by the orchestrator.

**Function: `async def process(job_id: Union[str, UUID], plan: ScenePlan, references: Optional[ReferenceImages]) -> ClipPrompts`**

**Responsibilities:**
1. **Normalize job_id:**
   - Accept both `str` and `UUID` (orchestrator currently passes `job_id` as `str`).
   - Convert to `UUID`, raising `ValidationError` if invalid.
2. **Derive base clip context:**
   - For each `ClipScript` in `plan.clip_scripts`, compute:
     - `duration = end - start`
     - `scene_ids`, `character_ids` from the script.
3. **Map references:**
   - Call `reference_mapper.map_references(plan, references)` to produce a per-clip mapping:
     - `scene_reference_url` for the primary scene (or `None` if unavailable).
     - `character_reference_urls` list (may be empty).
4. **Build style context:**
   - Call `style_synthesizer.extract_style_keywords(plan.style)` to get a canonical ordered list of `style_keywords` to be used uniformly across all prompts.
5. **Synthesize prompts (LLM-first):**
   - First, build base template prompts via `templates.build_prompt(...)` for each clip (cheap, deterministic).
   - Then call `llm_client.optimize_prompts(...)` once to generate **final curated prompts** for all clips in a single LLM batch call.
   - If the LLM call fails or is disabled (e.g. in test mode), fall back to the base template prompts without failing the job.
6. **Assemble `ClipPrompt` objects:**
   - For each clip:
     - Set `clip_index`, `prompt`, `negative_prompt`, `duration`, `scene_reference_url`, `character_reference_urls`.
     - Populate `metadata` with:
       - `word_count` (tokenized by whitespace).
       - `style_keywords` (canonical global list).
       - `scene_id` (primary scene for this clip or `None`).
       - `character_ids`.
       - `validated` (initially `False`, updated by `validator`).
       - Optional: `llm_used: bool`, `llm_model: Optional[str]`.
7. **Validate and normalize:**
   - Call `validator.validate_clip_prompts(job_id, plan, clip_prompts)` to enforce:
     - Clip count alignment with `plan.clip_scripts`.
     - Duration sanity.
     - Reference URL formatting.
     - Word-count and style consistency.
8. **Return `ClipPrompts` model:**
   - Include `job_id`, `clip_prompts`, `total_clips`, `generation_time`.
   - `generation_time` measured via `time.monotonic()` (in seconds).

**Error Handling:**
- Raise `GenerationError` if no prompts can be generated or validation fails irrecoverably.
- Gracefully handle `references is None` or missing references by falling back to text-only prompts with `scene_reference_url=None` and empty `character_reference_urls`.

---

### `prompt_synthesizer.py`

**Purpose:** Core algorithm to turn clip + style + references into a final `prompt` and `negative_prompt` for each clip.

**Key functions:**

1. **`build_clip_prompt(clip_ctx: ClipContext) -> Tuple[str, str]`**

   Where `ClipContext` is an internal dataclass or typed dict containing:
   - `visual_description: str` (from `ClipScript.visual_description`)
   - `motion: str`
   - `camera_angle: str`
   - `style_keywords: List[str]` (from `style_synthesizer`)
   - `color_palette: List[str]` (hex codes)
   - `mood: str`
   - `lighting: str`
   - `cinematography: str`
   - `scene_reference_url: Optional[str]`
   - `character_reference_urls: List[str]`
   - `beat_intensity: Literal["low", "medium", "high"]`

   **Prompt synthesis algorithm (template-based MVP):**
   - Construct an ordered list of fragments:
     1. Core action: `visual_description` (short, imperative or descriptive).
     2. Motion: `motion` (camera and subject motion).
     3. Camera: `camera_angle`.
     4. Style: `visual_style` + `mood` + `cinematography`.
     5. Color: short description derived from `color_palette` (e.g., "neon cyan and magenta color palette").
     6. Lighting: `lighting`.
     7. Quality modifiers: `"cinematic lighting, highly detailed, professional cinematography, 4K, 16:9 aspect ratio"`.
     8. Optional: Reference hint: `"match the look of the reference image"` if `scene_reference_url` present.
   - Join fragments with commas, then normalize whitespace and punctuation.
   - Truncate to **\<200 words**:
     - Compute word list via `prompt.split()`.
     - If length > 200, truncate to first 200 words, append `"..."`.

   **Negative prompt defaults:**
   - Fixed, reused for all clips:
     - `"blurry, low resolution, distorted faces, extra limbs, text, watermark, logo, oversaturated, flickering, low quality"`.
   - Optionally vary per mood (e.g., avoid "cartoon" for realistic styles).

2. **`summarize_color_palette(color_palette: List[str]) -> str`**
   - Convert hex codes into textual description (e.g., map `#00FFFF` → "cyan", `#FF00FF` → "magenta") using a small lookup table.
   - Respect style (e.g., for dark mood, emphasize "deep blues and purples").

3. **`compute_word_count(prompt: str) -> int`**
   - Simple whitespace split.

**Edge cases:**
- If `visual_description` is missing or empty, fall back to `"Wide shot of the main scene consistent with the overall style"`.
- If `motion` or `camera_angle` missing, use defaults based on `beat_intensity`:
  - `high` → "dynamic tracking shot, handheld camera".
  - `medium` → "smooth tracking shot".
  - `low` → "static camera, slow subtle movement".

---

### `style_synthesizer.py`

**Purpose:** Extract and enforce a globally consistent style vocabulary for all prompts in a job.

**Functions:**

1. **`extract_style_keywords(style: Style) -> List[str]`**
   - Inputs: `Style` from `ScenePlan`.
   - Outputs: ordered list of 5–10 canonical style keywords, e.g.:
     - From `visual_style`: `"cyberpunk"`, `"neo-noir"`.
     - From `mood`: `"melancholic"`, `"hopeful"`.
     - From `cinematography`: `"wide shots"`, `"tracking shots"`.
     - From `lighting`: `"neon lighting"`, `"high contrast"`.
   - Deduplicate and normalize to lowercase.

2. **`apply_style_keywords(base_prompt: str, style_keywords: List[str]) -> str`**
   - Append 2–4 of the canonical `style_keywords` near the end of the prompt in a natural phrase:
     - `"in a {style_keywords[0]} {style_keywords[1]} style, {style_keywords[2]} lighting"`.
   - Ensure final prompt still respects `<200` word limit.

3. **`ensure_global_consistency(prompts: List[str], style_keywords: List[str]) -> List[str]`**
   - Post-process a list of prompts to ensure all contain at least a subset of the canonical `style_keywords`.

**Metadata:**
- `style_keywords` list persisted into each clip’s `metadata["style_keywords"]` for downstream analytics or debugging.

---

### `reference_mapper.py`

**Purpose:** Map clip-level scene and character IDs from `ScenePlan` to reference image URLs from `ReferenceImages`.

**Functions:**

1. **`build_reference_index(references: Optional[ReferenceImages]) -> ReferenceIndex`**
   - If `references` is `None` or `references.status != "success"`:
     - Return an index with no URLs (text-only prompts).
   - Otherwise, create:
     - `scene_id -> scene_reference_url` (choose first image for each scene_id).
     - `character_id -> character_reference_url` (first image for each character_id).

2. **`map_clip_references(clip: ClipScript, index: ReferenceIndex) -> Tuple[Optional[str], List[str]]`**
   - `scene_reference_url`:
     - If clip has one or more `scenes`, choose the first scene_id that exists in the index.
   - `character_reference_urls`:
     - For each character_id in `clip.characters`, add corresponding URL when found.
   - If no mapping exists:
     - Return `None` for scene and an empty list for characters.

3. **`map_references(plan: ScenePlan, references: Optional[ReferenceImages]) -> Dict[int, ClipReferenceMapping]`**
   - For each `ClipScript`, produce a mapping:
     - `clip_index -> { "scene_id", "character_ids", "scene_reference_url", "character_reference_urls" }`.

**Edge Cases:**
- **Partial reference success:** Some scenes/characters missing images:
  - Leave URLs empty for those entities; prompts still generated.
- **Reference failure (fallback_mode):**
  - Module must fully function in text-only mode; maintain style consistency regardless of references.

---

### `validator.py`

**Purpose:** Validate and normalize the `ClipPrompts` output before returning to orchestrator.

**Functions:**

1. **`validate_clip_prompts(job_id: UUID, plan: ScenePlan, clip_prompts: ClipPrompts) -> ClipPrompts`**

   **Checks:**
   - **Count alignment:** `len(clip_prompts.clip_prompts) == len(plan.clip_scripts)`.
   - **Index alignment:** All `clip_index` values form a contiguous range `[0, N-1]`.
   - **Duration sanity:**
     - For each clip, `abs(duration - (clip_script.end - clip_script.start)) <= 0.25` seconds.
   - **Word count limit:**
     - `word_count <= 200` for all prompts.
   - **Reference URL validation:**
     - If `scene_reference_url` present, it must be a valid HTTP/HTTPS URL.
     - All `character_reference_urls` must be valid URLs.
   - **Metadata completeness:**
     - `word_count`, `style_keywords`, `scene_id`, `character_ids`, and `validated` exist in `metadata`.
   - **Style consistency:**
     - All `style_keywords` sets should be identical (or a superset) across clips.

   **Mutations:**
   - Fix minor issues (e.g., recompute durations, fix `word_count`, fill missing `scene_id` when possible).
   - Set `metadata["validated"] = True` once a clip passes all checks.
   - If severe issues detected (e.g., mismatched clip count), raise `GenerationError`.

2. **`normalize_negative_prompt(negative_prompt: str) -> str`**
   - Ensure a consistent negative prompt across clips (e.g., sort comma-separated tokens, remove duplicates).

---

### `llm_client.py`

**Purpose:** Primary LLM-based generation of curated prompts from base template/context data.

**Initial MVP Choice:** Implemented and **enabled by default** (config flag in `settings` can disable it for deterministic-only mode or tests).

**Function: `async def optimize_prompts(job_id: UUID, base_prompts: List[Dict[str, Any]], style_keywords: List[str]) -> List[str]`**

**Behavior (primary path):**
1. Build a single system prompt summarizing:
   - Project goal (music video generation pipeline).
   - Director-style prompt guidelines (how to write great clip prompts, not the full director knowledge base).
   - Style keywords that must be preserved and used consistently.
   - Constraints: `<200` words, no shot lists, no numbered lists.
2. Provide `base_prompts` (one per clip) as structured JSON in the user message.
3. Call GPT-4o or Claude 3.5 Sonnet with JSON mode to return an array of **final curated prompt strings** (one per clip).
   - Recommended parameters:
     - `model`: `"gpt-4o"` (default) or `"claude-3-5-sonnet"` (configurable).
     - `temperature`: `0.7` (balanced creativity/consistency).
     - `max_tokens`: ~`2000–4000` total (sufficient for all clip prompts).
     - `timeout`: `90.0` seconds (same budget as Scene Planner).
4. Validate length and ensure style keywords retained.

**Base Prompt Schema (`base_prompts`):**
- Each entry in `base_prompts` is a dict with at least:
  - `clip_index: int`
  - `visual_description: str`
  - `motion: str`
  - `camera_angle: str`
  - `scene_id: Optional[str]`
  - `character_ids: List[str]`
  - `duration: float`
  - `beat_intensity: "low" | "medium" | "high"`
  - `style_keywords: List[str]` (canonical global list)
  - `reference_mode: "scene" | "character" | "text_only"`
- The system prompt explains how to interpret this schema and how to convert each entry into a final prompt.

**Integration & Cost:**
- Decorate with `@retry_with_backoff(max_attempts=3, base_delay=2)` → delays 2s, 4s, 8s on retries.
- Use `cost_tracker.track_cost(job_id, stage="prompt_generator", api_name=model, cost=calculated_cost)`.
- Respect orchestrator’s budget checks; abort if budget exceeded.

---

### `templates.py`

**Purpose:** Provide deterministic prompt templates used both as:
- A **cheap base representation** of each clip prompt (fed into the LLM for refinement).
- A **fallback path** when the LLM is disabled or unavailable.

**Key components:**
- Template strings and helper functions for the algorithm described in `prompt_synthesizer.py`.
- Make all string building pure and easily testable.

---

### `README.md`

**Contents:**
- Module purpose and role in pipeline.
- Input and output model descriptions.
- Example JSON for `ScenePlan`, `ReferenceImages`, and resulting `ClipPrompts`.
- Configuration options:
  - `PROMPT_GENERATOR_USE_LLM` (bool)
  - `PROMPT_GENERATOR_LLM_MODEL` (str)
- Guidance for adding new style or negative prompt presets.

---

## Prompt Synthesis Algorithm

**Goal:** Convert each `ClipScript` + style + references into a concise, high-quality text-to-video prompt that:
- Stays under **200 words**.
- Uses a consistent, job-level style vocabulary.
- Correctly reflects the specific clip's action, camera, and mood.
- Is optimized for the target T2V models (Stable Video Diffusion and CogVideoX via Replicate).

### T2V Model-Specific Requirements

**Stable Video Diffusion (SVD) - Primary Model:**
- **Prompt style:** Concise, directive prompts work best (avoid overly narrative or poetic language).
- **Structure preference:** Action → Camera → Style → Quality modifiers.
- **Reference images:** Passed via API `image` parameter (not in text prompt).
- **Length:** 50–150 words optimal (SVD doesn't benefit from extremely long prompts).
- **Avoid:** URLs, shot lists, numbered sequences in text.

**CogVideoX - Fallback Model:**
- **Prompt style:** Can handle slightly longer, more narrative prompts.
- **Structure preference:** Similar to SVD but more flexible.
- **Reference images:** Also via API parameter.
- **Length:** 100–200 words (can utilize fuller context).

**Reference Image Handling:**
- Reference URLs are **not** included in prompt text.
- Prompts may include textual hints like:
  - "consistent with the established visual style" (if `scene_reference_url` present)
  - "character appearance matching earlier shots" (if `character_reference_urls` present)
- Actual reference URLs passed separately to Video Generator API as `image` parameter.

### Inputs per Clip

For each `ClipScript` in `ScenePlan`:
- `visual_description`, `motion`, `camera_angle`, `characters`, `scenes`, `lyrics_context`, `beat_intensity`.

From `Style`:
- `color_palette`, `visual_style`, `mood`, `lighting`, `cinematography`.

From `ReferenceIndex`:
- `scene_reference_url`, `character_reference_urls`.

From `style_synthesizer`:
- Canonical `style_keywords` list.

### Steps

1. **Core description:**
   - Start with `visual_description`, lightly normalized:
     - Ensure sentence-case.
     - Remove trailing periods to avoid excessive punctuation.

2. **Motion & camera:**
   - Add `motion` and `camera_angle` as separate clauses.
   - Adjust with `beat_intensity`:
     - `high`: emphasize faster, more dynamic motion.
     - `low`: emphasize calm, smooth or static motion.

3. **Style & mood:**
   - Add a phrase such as:
     - `"in a {visual_style} style that feels {mood}, with {cinematography}"`.

4. **Color & lighting:**
   - Use `summarize_color_palette(color_palette)` to create a short phrase like:
     - `"featuring neon cyan and magenta lights"`.
   - Include `lighting` text, ensuring it doesn’t conflict with style.

5. **Global quality modifiers:**
   - Append fixed high-quality modifiers:
     - `"cinematic lighting, highly detailed, professional cinematography, 4K, 16:9 aspect ratio"`.

6. **Reference hints (optional):**
   - If `scene_reference_url` is present:
     - Add a **textual hint**, not the URL itself:
       - `"match the look and composition of the established scene reference image"`.
   - If `character_reference_urls` present:
     - Add:
       - `"keep character appearance consistent with earlier shots"`.

7. **Style keyword injection:**
   - Use `style_synthesizer.apply_style_keywords` to inject 2–4 canonical `style_keywords` into the text in a natural way.

8. **Length enforcement:**
   - Truncate to `<200` words (hard cap).
   - Recompute `word_count` and store in `metadata`.

9. **Negative prompt construction:**
   - Start from a shared global template.
   - Optionally add mood-specific negatives:
     - For realistic styles: `"no cartoon, no anime, no illustration"`.

---

## Integration Points

### Orchestrator Integration (Module 2)

In `api_gateway/orchestrator.py`, the Prompt Generator is invoked as:

- `from modules.prompt_generator.process import process as generate_prompts`
- `clip_prompts = await generate_prompts(job_id, plan, references)`

**Requirements:**
- `process(job_id, plan, references)` must:
  - Accept `job_id` as `str` or `UUID`.
  - Accept `plan: ScenePlan`.
  - Accept `references: Optional[ReferenceImages]` (may be `None`).
  - Return a `ClipPrompts` instance.

**Progress & Stages:**
- Orchestrator publishes:
  - `stage_update` `"prompt_generator"` with `status: "started"`.
  - `update_progress(job_id, 40, "prompt_generator")` on completion.
  - **`prompt_generator_results` event** with prompt data for UI display (see below).
- Prompt Generator does **not** publish its own SSE events directly; only orchestrator handles publishing.

**SSE Event: `prompt_generator_results`**

After Prompt Generator completes, orchestrator publishes results for frontend display:

```typescript
event: prompt_generator_results
data: {
  "total_clips": 6,
  "generation_time": 3.2,
  "llm_used": true,
  "llm_model": "gpt-4o",
  "clip_prompts": [
    {
      "clip_index": 0,
      "prompt": "A lone figure walks toward camera through rain-slicked cyberpunk...",  // Full text
      "negative_prompt": "blurry, low resolution, distorted faces, extra limbs...",
      "duration": 5.2,
      "metadata": {
        "word_count": 85,
        "style_keywords": ["cyberpunk", "neon", "high-contrast"],
        "validated": true
      }
    }
    // ... remaining clips
  ]
}
```

**Frontend Integration:**
- Add `PromptGeneratorResultsEvent` type to `types/sse.ts`.
- Add `onPromptGeneratorResults` handler in `useSSE` hook.
- Display prompts in `ProgressTracker` component (collapsible card, one row per clip with index, duration, and truncated prompt).
- Show full prompt on click/hover for review.

**Budget & Cost Tracking:**
- Before expensive operations (e.g., LLM), orchestrator pre-checks budget via `cost_tracker.check_budget`.
- Prompt Generator itself:
  - Uses `cost_tracker.track_cost` for LLM calls.
  - Must not exceed environment-specific budget configured in `settings`.
  - Estimated cost: ~$0.01–0.03 per job (small relative to Video Generator's ~$0.60).

**Integration with Video Generator (Module 7):**

The Prompt Generator produces `ClipPrompts` with reference URLs that the Video Generator consumes. **Reference image priority rules:**

1. **Primary reference (API `image` parameter):**
   - If `scene_reference_url` exists → use it as the primary reference image.
   - Else if `character_reference_urls` is non-empty → use `character_reference_urls[0]`.
   - Else → text-only mode (no reference image passed to T2V API).

2. **Character consistency in text prompts:**
   - **Always** include character descriptions from `ScenePlan.characters` in the prompt text for consistency.
   - Example: "Young woman in futuristic jacket, consistent with previous shots..."
   - Character reference URLs stored in `metadata` for future multi-reference support.

3. **Scene context:**
   - Scene descriptions from `ScenePlan.scenes` guide the prompt text.
   - Scene reference URL (if available) passed as primary `image` to establish location/lighting/atmosphere.

4. **Fallback strategy:**
   - If no references available (`references is None` or all URLs missing):
     - Prompts still generated with rich textual descriptions.
     - Video Generator operates in text-only mode.
     - Style keywords ensure consistency across clips.

### Shared Components Usage

- `shared.models.scene.ScenePlan`, `ReferenceImages`.
- `shared.models.video.ClipPrompts`, `ClipPrompt`.
- `shared.retry.retry_with_backoff` for LLM calls.
- `shared.cost_tracking.CostTracker` for cost accounting.
- `shared.logging.get_logger` for structured logs.
- `shared.errors`:
  - `ValidationError` for input/model issues.
  - `GenerationError` for prompt generation failures.
  - `RetryableError` when LLM call is temporarily failing.

---

## Error Handling & Fallbacks

### Input Validation Errors

- Conditions:
  - `plan.clip_scripts` is empty.
  - `len(plan.clip_scripts) == 0` while `audio_data` indicates clips (should not happen, but be defensive if invoked directly).
  - `job_id` cannot be parsed as `UUID`.
- Behavior:
  - Raise `ValidationError` with details.
  - Orchestrator handles marking job as failed and publishing error SSE.

### Missing or Partial References

- `references is None` or `references.status in {"partial", "failed"}`:
  - Operate in **text-only mode**:
    - `scene_reference_url` set to `None`.
    - `character_reference_urls` empty.
  - Still enforce style consistency and valid prompts.
  - Optionally set `metadata["reference_mode"] = "text_only"` or `"partial"`.

### LLM Failures (Primary Path)

- LLM optimization is **enabled by default**:
  - Wrap calls with `@retry_with_backoff`.
  - On permanent failure:
    - Log warning and fall back to template-only prompts.
    - Do **not** fail the job if deterministic templates succeed.

### Validation Failures

- If validator detects fixable issues:
  - Normalize data and continue (e.g., recompute durations).
- If unfixable issues (e.g., mismatched clip counts):
  - Raise `GenerationError`.

---

## Performance & Caching

### Performance Targets

- Prompt generation for a typical 3-minute song (10–20 clips):
  - **Target:** \<5 seconds end-to-end in deterministic mode.
  - **With LLM optimization:** dominated by LLM latency (e.g., \<3–4s for a single batch call).

### Caching

- Phase 1: No persistent caching needed; prompt generation is cheap.
- Potential future enhancement:
  - Cache prompts keyed by `(job_id, ScenePlan.hash())` if prompt regeneration is requested repeatedly.

---

## Testing Requirements

### Unit Tests

**`test_prompt_synthesizer.py`:**
- Prompt structure includes all key elements (description, motion, camera, style, color, quality modifiers).
- Word-count enforcement: prompts are truncated to ≤200 words.
- Negative prompts contain the expected banned tokens.
- Edge cases: missing `motion`, missing `camera_angle`, missing `visual_description`.

**`test_style_synthesizer.py`:**
- Style keyword extraction from various `Style` configurations (cyberpunk, bright pop, dark moody).
- Consistent keyword ordering and deduplication.
- Ensuring all prompts contain a subset of `style_keywords`.

**`test_reference_mapper.py`:**
- Mapping for full `ReferenceImages` (scene + character references).
- Partial reference coverage (some scene/character IDs missing).
- `references is None` (text-only mode).

**`test_validator.py`:**
- Clip count alignment checks.
- Duration sanity checks.
- Reference URL validation (valid/invalid).
- Metadata completeness and `validated` flag behavior.

**`test_llm_client.py`:**
- With mocked LLM API:
  - Single-call batch optimization returns updated prompts.
  - Retry path on transient errors (e.g., HTTP 500).
  - Cost calculation and tracking.

### Integration Tests (`test_process.py`)

- Scenario 1: **Happy path**
  - Given realistic `ScenePlan` and full `ReferenceImages`, `process(...)` returns `ClipPrompts` with:
    - Matching clip counts.
    - Valid URLs where expected.
    - Proper metadata (word_count, style_keywords, etc.).

- Scenario 2: **No references (text-only mode)**
  - `references = None`:
    - Prompts still generated.
    - No reference URLs included.
    - Rich textual descriptions compensate for missing images.

- Scenario 3: **Partial references**
  - Some scenes/characters missing reference images:
    - Only existing references mapped.
    - No crashes or invalid URLs.
    - Priority rules applied (scene → character → text-only).

- Scenario 4: **LLM disabled vs enabled**
  - `PROMPT_GENERATOR_USE_LLM = False`: deterministic templates only.
  - `PROMPT_GENERATOR_USE_LLM = True` with mocked LLM: uses optimized prompts and still passes validation.

- Scenario 5: **Extreme clip counts**
  - Short songs (3 clips) and long songs (20+ clips).
  - Ensure performance remains acceptable and no timeouts in tests.

**Parallel Development Fixtures:**

To enable development in parallel with Reference Generator (Module 5), create mock fixtures:

**`fixtures/sample_reference_images.json`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "scene_references": [
    {
      "scene_id": "city_street",
      "image_url": "https://placeholder.example/scene_city_street.png",
      "prompt_used": "Rain-slicked cyberpunk street with neon signs",
      "generation_time": 8.5,
      "cost": "0.005"
    }
  ],
  "character_references": [
    {
      "character_id": "protagonist",
      "image_url": "https://placeholder.example/char_protagonist.png",
      "prompt_used": "Young woman, 25-30, futuristic jacket, cyberpunk style",
      "generation_time": 8.2,
      "cost": "0.005"
    }
  ],
  "total_references": 2,
  "total_generation_time": 16.7,
  "total_cost": "0.010",
  "status": "success",
  "metadata": {}
}
```

**Testing Strategy:**
1. **Phase 1 (parallel dev):** Test with `references = None` and mock `ReferenceImages` fixtures.
2. **Phase 2 (integration):** Test with real `ReferenceImages` from Reference Generator.
3. **Use placeholder images:** Public domain images or generated test images for manual verification.

---

## Success Criteria

- **Functional:**
  - **✅** For every `ClipScript` in `ScenePlan`, a corresponding `ClipPrompt` is produced.
  - **✅** All prompts are valid, non-empty strings and respect the `<200` word limit.
  - **✅** `ClipPrompts` output conforms exactly to `shared.models.video.ClipPrompts`.
  - **✅** Module gracefully handles missing or partial `ReferenceImages` (text-only prompts).

- **Quality:**
  - **✅** Prompts use a **consistent style vocabulary** across all clips (same `style_keywords`).
  - **✅** Prompts reflect beat intensity and scene/character context.
  - **✅** Negative prompts consistently avoid common T2V artifacts.

- **Performance & Reliability:**
  - **✅** Prompt generation completes in **\<5 seconds** for typical jobs (excluding LLM latency if enabled).
  - **✅** If LLM optimization is used, failures fall back to deterministic prompts instead of failing the job.
  - **✅** No unhandled exceptions; all validation or generation errors surface as `GenerationError`/`ValidationError`.
  - **✅** 80%+ code coverage for the `prompt_generator` module.

---

## Implementation Notes & Phasing

**Phase 1 (MVP – Build Now):**
- Implement **full pipeline with LLM as primary path**:
  - `process.py`: Orchestration with LLM-first flow (templates → LLM → validation).
  - `llm_client.py`: Batch prompt optimization via GPT-4o/Claude 3.5 Sonnet.
  - `prompt_synthesizer.py`, `style_synthesizer.py`, `reference_mapper.py`, `validator.py`: Core logic.
  - `templates.py`: Deterministic base prompts (used as LLM input and fallback).
- **Cost tracking and budget enforcement** integrated from the start.
- **Retry logic** (`@retry_with_backoff`) for LLM failures with template fallback.
- **Test with mocked LLM responses** to validate pipeline without API costs during development.
- **Orchestrator publishes `prompt_generator_results` event** for UI display.

**Phase 2 (Enhancement – Post-MVP):**
- **A/B testing:** Compare LLM-optimized prompts vs deterministic templates for quality.
- **Prompt tuning:** Refine system prompt and style vocabulary based on real T2V model results.
- **Token optimization:** Reduce input token count by compressing clip context (shorter base prompts).
- **Caching:** Cache prompts for identical `ScenePlan` + `ReferenceImages` combinations.
- **Multi-model support:** Test and optimize for different T2V models (SVD, CogVideoX, future models).
- **Advanced features:** Previous clip context for narrative continuity, lyrics-synced prompt adjustments.

**Parallel Development with Reference Generator:**
- Use **mock `ReferenceImages` fixtures** during development (see Testing Requirements).
- Test in **text-only mode** (`references = None`) first to validate core logic.
- Integrate real reference images when Reference Generator (Module 5) is complete.

This PRD is sufficient for a developer to implement the Prompt Generator module and integrate it into the existing pipeline following current patterns in the Scene Planner and orchestrator.


