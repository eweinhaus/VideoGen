# Character Selection for Lipsync

## Overview

This document describes the character selection feature for lipsync operations. Users can now specify which character(s) should be lipsynced in a clip by using natural language in their instructions.

## How It Works

### User Instructions

Users can specify character selection in several ways:

1. **By Name**: "make Sarah lipsync", "sync Kendrick's lips"
2. **By Pronoun**: "make him lipsync", "sync her lips", "make them lipsync"
3. **By Role**: "make the protagonist lipsync", "sync the main character"
4. **Multiple Characters**: "make both characters lipsync", "sync all characters"
5. **No Specification**: "make it lipsync" (syncs all visible characters)

### Examples

```
✅ "make him lipsync" → Syncs the main male character
✅ "make Sarah lipsync" → Syncs character named "Sarah"
✅ "make both characters lipsync" → Syncs all characters in the clip
✅ "make the protagonist lipsync" → Syncs the protagonist
✅ "make it lipsync" → Syncs all visible characters (default)
```

## Implementation Details

### Architecture

The character selection system consists of three main components:

1. **Character Parser** (`character_parser.py`)
   - Extracts character references from user instructions
   - Matches references to character IDs from scene plan
   - Returns list of character IDs to target

2. **Lipsync Processor** (`lipsync_processor/`)
   - Accepts optional `character_ids` parameter
   - Passes character information to lipsync model (if supported)
   - Currently logs character selection (model may sync all visible faces)

3. **Regeneration Process** (`process.py`)
   - Loads scene plan to get character definitions
   - Parses character selection from user instruction
   - Passes character IDs to lipsync processor

### Character Matching

The parser uses a confidence-based matching system:

- **Exact Name Match**: 1.0 confidence
- **Partial Name Match**: 0.8 confidence
- **ID Match**: 0.9 confidence
- **Role Match**: 0.6-0.7 confidence
- **Pronoun Match**: 0.4-0.5 confidence (context-dependent)

Only matches with confidence ≥ 0.4 are used.

### Character Filtering

Characters are filtered by clip:
- Only characters that appear in the target clip are considered
- This prevents matching characters from other clips

## Current Limitations

### Model Support

The PixVerse lipsync model (`pixverse/lipsync`) may not currently support explicit character selection. The implementation:

1. ✅ Parses character selection from user instructions
2. ✅ Passes character IDs to the lipsync processor
3. ✅ Logs character selection for debugging
4. ⚠️ Model may sync all visible characters (if not supported)

### Future Enhancements

When the model supports character selection:

1. **Face Detection**: Identify which faces correspond to which character IDs
2. **Selective Sync**: Only sync specified characters' lips
3. **Multi-Character Audio**: Handle cases where multiple characters speak

## API Changes

### `process_single_clip_lipsync()`

**New Parameter:**
```python
character_ids: Optional[List[str]] = None
```

**Usage:**
```python
lipsynced_clip = await process_single_clip_lipsync(
    clip=original_clip,
    clip_index=clip_index,
    audio_url=audio_url,
    job_id=job_id,
    environment=environment,
    event_publisher=event_publisher,
    character_ids=["protagonist", "love_interest"]  # Optional
)
```

### `generate_lipsync_clip()`

**New Parameter:**
```python
character_ids: Optional[List[str]] = None
```

**Current Behavior:**
- Character IDs are logged but not passed to Replicate API
- Model will sync all visible characters
- Ready for future model support

## Testing

### Test Character Selection Parsing

```python
from modules.clip_regenerator.character_parser import parse_character_selection

# Test with scene plan
character_ids = parse_character_selection(
    instruction="make him lipsync",
    scene_plan=scene_plan,
    clip_index=0
)
assert "protagonist" in character_ids
```

### Test Lipsync with Character Selection

```python
# In regeneration process
character_ids = parse_character_selection(
    instruction="make Sarah lipsync",
    scene_plan=scene_plan,
    clip_index=0
)

lipsynced_clip = await process_single_clip_lipsync(
    clip=clip,
    clip_index=0,
    audio_url=audio_url,
    job_id=job_id,
    character_ids=character_ids
)
```

## User Experience

### Frontend Integration

The frontend can enhance the user experience by:

1. **Showing Available Characters**: Display characters that appear in the selected clip
2. **Character Suggestions**: Suggest character names when user types "make [character] lipsync"
3. **Visual Feedback**: Show which characters will be synced

### Example UI Flow

```
User selects clip → ClipChatbot shows:
  "Available characters in this clip: Sarah, John"
  
User types: "make Sarah lipsync"
  → System parses: character_ids = ["sarah"]
  → Shows: "Syncing Sarah's lips..."
  → Processes lipsync with character selection
```

## Error Handling

### No Character Match

If no character matches are found:
- System logs warning
- Returns empty list (syncs all visible characters)
- Does not fail the operation

### Invalid Character ID

If character ID doesn't exist in scene plan:
- Character is ignored
- Other valid characters are still processed
- Logs warning

## Future Work

1. **Model Support**: When PixVerse adds character selection support, enable it
2. **Face Detection**: Add face detection to map character IDs to faces in video
3. **Multi-Character Audio**: Handle audio with multiple speakers
4. **Character Preview**: Show character thumbnails in UI
5. **Confidence Threshold**: Make confidence threshold configurable

## Related Files

- `project/backend/modules/clip_regenerator/character_parser.py` - Character parsing logic
- `project/backend/modules/clip_regenerator/process.py` - Integration with regeneration
- `project/backend/modules/lipsync_processor/process.py` - Lipsync orchestration
- `project/backend/modules/lipsync_processor/generator.py` - Replicate API integration

