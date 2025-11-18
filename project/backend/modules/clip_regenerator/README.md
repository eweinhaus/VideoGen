# Module: Clip Regenerator

**Tech Stack:** Python (Data Loading, Future: LLM Integration)

## Purpose

This module provides data loading functionality for the clip chatbot feature. It loads clip data, prompts, scene plans, and reference images from the `job_stages.metadata` table, enabling clip regeneration and editing.

## Key Features

- **Data Loading**: Load clips, prompts, scene plans, and reference images from `job_stages.metadata`
- **Nested JSON Handling**: Correctly parses nested JSON structure (`metadata['clips']['clips']`)
- **Pydantic Validation**: Reconstructs Pydantic models from JSON data with validation
- **Error Handling**: Graceful error handling (returns None on failure, doesn't raise exceptions)

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

## Future Enhancements

This module will be extended in Part 2 and Part 3 of the clip chatbot feature:
- **Part 2**: Template system, LLM prompt modification, regeneration API
- **Part 3**: Composer integration, error handling, E2E testing

