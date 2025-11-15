# Module 6 – Prompt Generator

**Tech Stack:** Python 3.13, FastAPI worker context, OpenAI GPT-4o (configurable)

## Purpose
Convert `ScenePlan + ReferenceImages` into high-quality clip prompts for Module 7.  
The module merges clip scripts, reference URLs, and job-level style vocabulary, then optionally calls an LLM to polish every prompt in a single batch.

## Highlights

- Deterministic template builder powered by `prompt_synthesizer` (always available, <200 words per prompt)
- Global style vocabulary extracted once per job for consistent look/feel
- Optional LLM refinement (single batched call, retries, cost-tracked, <90s timeout)
- Rich metadata (`word_count`, `style_keywords`, `reference_mode`, `llm_used`, etc.) returned with each `ClipPrompt`
- Validation layer guarantees clip counts, durations, and URLs match upstream expectations
- SSE event `prompt_generator_results` streamed to the frontend when the stage completes

## Environment Flags

| Env Var | Default | Description |
| --- | --- | --- |
| `PROMPT_GENERATOR_USE_LLM` | `true` | Toggle LLM refinement on/off |
| `PROMPT_GENERATOR_LLM_MODEL` | `gpt-4o` | Preferred model (fallbacks to GPT-4o if unsupported) |

## File Map

- `process.py` – high-level orchestration used by the API Gateway
- `prompt_synthesizer.py` – deterministic prompt assembly + negative prompts
- `style_synthesizer.py` – extracts/enforces canonical style keywords
- `reference_mapper.py` – maps clip IDs → reference image URLs
- `llm_client.py` – batch GPT-4o call with retry + cost tracking
- `validator.py` – sanity checks and metadata normalization
- `templates.py` – base prompt payloads for both LLM input and fallback output
- `tests/` – unit + integration tests with fixtures for plans, references, and prompts

## Running Tests

```bash
cd project/backend
pytest modules/prompt_generator/tests -q
```

The suite includes unit tests for every helper plus async integration tests for `process()` with both deterministic and mocked LLM paths.



