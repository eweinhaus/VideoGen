# Module: Clip Regenerator

**Tech Stack:** Python (Data Loading, LLM Integration, Video Generation)

## Purpose

This module provides clip regeneration functionality for the clip chatbot feature. It loads clip data, prompts, scene plans, and reference images from the `job_stages.metadata` table, enables LLM-powered prompt modification with intelligent temperature determination, and regenerates video clips with appropriate randomness control.

## Key Features

- **Data Loading**: Load clips, prompts, scene plans, and reference images from `job_stages.metadata`
- **Template Matching**: Fast template-based transformations for common modifications (brighter, darker, nighttime, etc.)
- **LLM Prompt Modification**: GPT-4o-powered prompt modification with intelligent temperature determination
- **Temperature Control**: LLM determines appropriate temperature (0.0-1.0) based on user instruction:
  - Low (0.3-0.5): Precise, minimal changes (e.g., "keep scene same, change hair color")
  - Medium (0.6-0.7): Moderate changes (e.g., "change lighting and add motion")
  - High (0.8-1.0): Complete regeneration (e.g., "completely regenerate this scene")
- **Seed Reuse**: For precise changes (low temperature), reuses original clip's seed for consistency
- **Nested JSON Handling**: Correctly parses nested JSON structure (`metadata['clips']['clips']`)
- **Pydantic Validation**: Reconstructs Pydantic models from JSON data with validation
- **Error Handling**: Graceful error handling with fallbacks for JSON parsing failures

## Module Structure

```
modules/clip_regenerator/
├── __init__.py
├── data_loader.py          # Data loading functions
├── tests/
│   └── test_data_loader.py # Unit tests
└── README.md
```

## Data Loading Functions

### `load_clips_from_job_stages(job_id: UUID) -> Optional[Clips]`

Loads `Clips` object from `job_stages` table where `stage_name='video_generator'`.

**Metadata Structure:**
```json
{
  "clips": {
    "clips": [
      {
        "clip_index": 0,
        "video_url": "https://...",
        "actual_duration": 12.5,
        ...
      }
    ],
    "total_clips": 6,
    "successful_clips": 6,
    ...
  }
}
```

**Returns:** `Clips` object if found, `None` if stage not found or invalid

### `load_clip_prompts_from_job_stages(job_id: UUID) -> Optional[ClipPrompts]`

Loads `ClipPrompts` object from `job_stages` table where `stage_name='prompt_generator'`.

**Returns:** `ClipPrompts` object if found, `None` if stage not found or invalid

### `load_scene_plan_from_job_stages(job_id: UUID) -> Optional[ScenePlan]`

Loads `ScenePlan` object from `job_stages` table where `stage_name='scene_planner'`.

**Returns:** `ScenePlan` object if found, `None` if stage not found or invalid

### `load_reference_images_from_job_stages(job_id: UUID) -> Optional[ReferenceImages]`

Loads `ReferenceImages` object from `job_stages` table where `stage_name='reference_generator'`.

**Returns:** `ReferenceImages` object if found, `None` if stage not found or invalid

## Error Handling

All functions handle errors gracefully:
- **Missing Stage**: Returns `None` (job may not be completed)
- **Invalid JSON**: Logs error, returns `None`
- **Pydantic Validation Error**: Logs error, returns `None`
- **Database Error**: Logs error, returns `None`

Functions never raise exceptions for non-critical operations, allowing the calling code to handle missing data appropriately.

## Usage Example

```python
from modules.clip_regenerator.data_loader import load_clips_from_job_stages
from uuid import UUID

# Load clips for a job
clips = await load_clips_from_job_stages(UUID("550e8400-e29b-41d4-a716-446655440000"))

if clips:
    print(f"Loaded {len(clips.clips)} clips")
    for clip in clips.clips:
        print(f"Clip {clip.clip_index}: {clip.video_url}")
else:
    print("Clips not found or invalid")
```

## Testing

Run unit tests:
```bash
cd project/backend
PYTHONPATH=. pytest modules/clip_regenerator/tests/test_data_loader.py -v
```

## Regeneration Process

### Temperature Determination

The LLM analyzes user instructions and determines appropriate temperature for video generation:

- **Very Low Temperature (0.2-0.3)**: For "almost exactly the same" requests with minor fixes (e.g., "regenerate almost exactly the same, avoid weird right arm", "keep everything identical except fix X")
- **Low Temperature (0.3-0.4)**: For precise, minimal changes (e.g., "keep scene same, change hair color", "keep everything the same but...")
- **Medium-Low Temperature (0.4-0.5)**: For small but noticeable changes (e.g., "slightly adjust lighting")
- **Moderate Changes (0.6-0.7)**: User requests moderate modifications (e.g., "change lighting and add motion")
- **Complete Regeneration (0.8-1.0)**: User requests complete regeneration (e.g., "completely regenerate")

**Post-Processing Refinement**: If the LLM chooses 0.35 or higher but the user instruction contains phrases like "almost exactly the same", the system automatically refines the temperature downward to 0.2-0.3 for maximum consistency.

### Seed Reuse Strategy

- **Precise Changes (temp < 0.5)**: Reuses original clip's seed for consistency
- **Moderate/Complete (temp ≥ 0.5)**: Uses random seed for variation

### LLM Response Format

The LLM returns JSON with:
```json
{
  "prompt": "modified prompt text",
  "temperature": 0.4,
  "reasoning": "Precise change requested - only hair color modification"
}
```

If JSON parsing fails, the system falls back to text parsing with default temperature 0.7.

## Temperature and Seed Parameters

### Temperature (Veo 3.1 only)

- **Range**: 0.0 - 1.0
- **Lower values**: More deterministic, preserves original scene better
- **Higher values**: More creative variation, allows larger changes
- **Default**: 0.7 (if not determined by LLM)

### Seed (Veo 3.1 only)

- **Type**: Integer or None
- **Purpose**: Ensures reproducible generation
- **Strategy**: 
  - Reused for precise changes (maintains consistency)
  - Random for complete regenerations (ensures variation)
- **Storage**: Stored in clip metadata as `generation_seed` for future reuse

## Future Enhancements

- Enhanced seed storage in original clip generation
- Temperature tuning based on user feedback
- Support for temperature/seed in other video models

