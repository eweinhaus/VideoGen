# Pipeline Inputs and Outputs

Exact formatting information for each module's inputs and outputs.

## 0. Frontend: User Input

**Name**: Frontend: User Input

**Inputs**:
- `audio_file` (File): Audio file in MP3, WAV, or other supported format
- `creative_prompt` (String): Text description of desired video content
- `optional_parameters` (Object, optional): 
  - `style_preferences` (String, optional): Style hints
  - `duration` (Number, optional): Desired duration in seconds
  - `mood` (String, optional): Mood preference

**Outputs**:
- `job_id` (String): Unique job identifier (UUID format)
- `status` (String): "queued" or "error"
- `error_message` (String, optional): Error details if status is "error"

---

## 1. Audio Parsing Agent

**Name**: Audio Parsing Agent

**Inputs**:
- `audio_file` (File): Audio file path or file object (MP3, WAV format)

**Outputs**:
- `lyrics` (Object):
  - `full_text` (String): Complete lyrics transcription (empty string if instrumental or transcription fails)
  - `timed_lyrics` (Array of Objects): `[{"timestamp": Number (seconds), "text": String}, ...]`
  - `language` (String): Language code (e.g., "en")
- `beat_timestamps` (Array of Numbers): `[0.0, 0.5, 1.2, ...]` in seconds (empty array if beat detection fails)
- `tempo_bpm` (Number): Beats per minute (required, used for fallback)
- `audio_features` (Object):
  - `loudness` (Number): Decibels (dB)
  - `energy_level` (Number): 0-1 scale (basic mood/energy)
- `clip_boundaries` (Array of Objects): `[{"start": Number, "end": Number, "duration": Number}, ...]` in seconds
- `validation` (Object):
  - `beat_detection_success` (Boolean): Whether beat detection succeeded
  - `fallback_used` (Boolean): Whether tempo-based fallback was used
  - `confidence` (Number): Confidence score (0-1) for beat detection
  - `transcription_success` (Boolean): Whether lyrics transcription succeeded

---

## 2. Scene Planning Agent

**Name**: Scene Planning Agent

**Inputs**:
- `user_prompt` (String): Creative prompt from user
- `audio_parsing_output` (Object): Complete output from Audio Parsing Agent

**Outputs**:
- `video_summary` (String): High-level description of entire video
- `characters` (Array of Objects):
  - `name` (String): Character identifier
  - `physical_attributes` (Object):
    - `appearance` (String): General appearance description
    - `hair` (String): Hair description
    - `clothing` (String): Clothing description
    - `age_range` (String): Age range description
    - `distinctive_features` (Array of Strings): Notable features
  - `personality` (String): Personality traits
  - `role` (String): Role in video
- `scenes` (Array of Objects):
  - `scene_id` (String): Scene identifier
  - `environment` (String): Environment description
  - `physical_details` (Object):
    - `architecture` (String): Architecture description
    - `ground` (String): Ground/surface description
    - `atmosphere` (String): Atmospheric conditions
    - `key_objects` (Array of Strings): Important objects in scene
- `objects` (Array of Objects):
  - `object_name` (String): Object identifier
  - `physical_attributes` (Object):
    - `appearance` (String): Appearance description
    - `size` (String): Size description
    - `material` (String): Material description
  - `importance` (String): Importance to plot
- `style_info` (Object):
  - `color_palette` (Array of Strings): `["#FF5733", "#33FF57", ...]` hex codes
  - `color_descriptions` (String): Color description text
  - `visual_style` (String): Visual style description
  - `mood` (String): Mood description
  - `lighting` (String): Lighting description
- `clip_scripts` (Array of Objects):
  - `clip_index` (Number): Zero-based clip index
  - `start_time` (Number): Start timestamp in seconds
  - `end_time` (Number): End timestamp in seconds
  - `duration` (Number): Duration in seconds
  - `lyrics_context` (String): Matching lyrics for this clip
  - `visual_description` (String): Visual description
  - `motion` (String): Motion description
  - `camera` (String): Camera description
  - `style_parameters` (String): Style parameters text
  - `characters_in_scene` (Array of Strings): Character names in scene
  - `scene_reference` (String): Scene ID reference
- `transitions` (Array of Objects):
  - `from_clip_index` (Number): Source clip index
  - `to_clip_index` (Number): Destination clip index
  - `type` (String): "crossfade", "cut", or "fade"
  - `duration` (Number, optional): Transition duration in seconds (for crossfade/fade)

---

## 3. Reference Photo Generation Agent

**Name**: Reference Photo Generation Agent

**Inputs**:
- `scene_planning_output` (Object): Complete output from Scene Planning Agent

**Outputs**:
- `reference_photo` (Object, nullable):
  - `type` (String): "style_reference"
  - `image_path` (String, nullable): File path to generated image (null if generation failed)
  - `description` (String): Description of reference image
  - `cache_key` (String, optional): Cache key for reuse
- `color_palette` (Object): Color palette reference (non-photo, from scene planning)
  - `hex_codes` (Array of Strings): `["#FF5733", ...]` hex codes
  - `description` (String): Color palette description
- `validation` (Object):
  - `photo_generated` (Boolean): Whether reference photo generated successfully
  - `fallback_used` (Boolean): Whether fallback to null (text-only) was used

---

## 4. Video Prompt Generation Agent

**Name**: Video Prompt Generation Agent

**Inputs**:
- `clip_script` (Object): Single clip script from Scene Planning Agent
- `reference_photo` (Object, nullable): Reference photo object from Reference Photo Agent (null if unavailable)
- `video_summary` (String): Video summary from Scene Planning Agent
- `style_info` (Object): Style info object from Scene Planning Agent
- `transition_info` (Object, optional): Transition information for this clip from Scene Planning Agent

**Outputs**:
- `clip_index` (Number): Zero-based clip index
- `video_prompt` (String): Optimized text prompt for video generation
- `style_parameters` (Object):
  - `colors` (Array of Strings): `["#FF5733", ...]` hex codes
  - `aesthetic` (String): Aesthetic description
  - `mood` (String): Mood description
  - `lighting` (String): Lighting description
- `motion_parameters` (Object):
  - `camera` (String): Camera movement description
  - `subject_motion` (String): Subject motion description
  - `speed` (String): Motion speed description
- `camera_parameters` (Object):
  - `shot_type` (String): Shot type (e.g., "close-up")
  - `movement` (String): Camera movement type
  - `angle` (String): Camera angle
- `duration` (Number): Exact duration in seconds (from beat boundaries)
- `reference_photo_path` (String, nullable): Reference photo file path (null if unavailable)
- `transition_hint` (String, optional): Transition type hint for composition stage

---

## 5. Video Generation Agent

**Name**: Video Generation Agent

**Inputs**:
- `video_prompt` (Object): Complete output from Video Prompt Generation Agent
- `reference_photo_path` (String, nullable): Reference photo file path (null if unavailable)

**Outputs**:
- `clip_index` (Number): Zero-based clip index
- `video_path` (String, nullable): File path to generated video clip (MP4 format, null if failed)
- `requested_duration` (Number): Requested duration in seconds (from beat boundaries)
- `actual_duration` (Number): Actual duration in seconds (may differ from requested)
- `api_duration_used` (Number): Duration option used from API (e.g., 4, 5, 10 seconds)
- `resolution` (String): Resolution (e.g., "1080x1920")
- `frame_rate` (Number): Frame rate (e.g., 30)
- `status` (String): "success" or "error"
- `cost` (Number): API cost in USD
- `generation_time` (Number): Generation time in seconds
- `error_message` (String, optional): Error details if status is "error"
- `retry_count` (Number): Number of retries attempted (0-3)
- `validation` (Object):
  - `duration_match` (Boolean): Whether actual duration matches requested (within ±2s tolerance)
  - `quality_check` (Boolean): Basic quality validation passed
  - `duration_difference` (Number): Difference between requested and actual duration in seconds

---

## 6. Audio-Video Composition Agent

**Name**: Audio-Video Composition Agent

**Inputs**:
- `generated_clips` (Array of Objects): All clip outputs from Video Generation Agent
- `original_audio_file` (File): Original audio file from Frontend
- `beat_timestamps` (Array of Numbers): Beat timestamps from Audio Parsing Agent
- `clip_boundaries` (Array of Objects): Clip boundaries from Audio Parsing Agent
- `transition_plans` (Array of Objects): Transition plans from Scene Planning Agent

**Outputs**:
- `composed_video` (Object):
  - `path` (String): File path to final composed video (MP4 format)
  - `duration` (Number): Final video duration in seconds
  - `resolution` (String): Final resolution (e.g., "1080x1920")
  - `frame_rate` (Number): Final frame rate (e.g., 30)
  - `audio_synced` (Boolean): Whether audio sync was successful
  - `file_size_mb` (Number): File size in megabytes
- `clips` (Array of Objects):
  - `clip_index` (Number): Zero-based clip index
  - `video_path` (String): File path to individual clip
  - `start_time` (Number): Start timestamp in seconds
  - `end_time` (Number): End timestamp in seconds
  - `selected` (Boolean): Whether clip is included (default: true)
- `audio_file` (String): Path to original audio file
- `metadata` (Object):
  - `beat_timestamps` (Array of Numbers): Beat timestamps
  - `clip_boundaries` (Array of Objects): Clip boundaries
  - `clips_trimmed` (Number): Number of clips that were trimmed to fit beat boundaries
  - `clips_looped` (Number): Number of clips that were looped to fill duration
  - `total_trim_duration` (Number): Total seconds trimmed from all clips
  - `total_loop_duration` (Number): Total seconds added via looping
- `validation` (Object):
  - `audio_sync_verified` (Boolean): Whether audio sync was verified
  - `duration_match` (Boolean): Whether final duration matches audio duration (within 0.1s tolerance)
  - `sync_drift` (Number): Audio-video drift in seconds (should be < 0.1s)
  - `speed_adjustment_used` (Boolean): Whether video speed was adjusted to match audio

---

## 7. Frontend: Display & Export

**Name**: Frontend: Display & Export

**Inputs**:
- `individual_clips` (Array of Objects): Clip metadata from Composition Agent
- `composed_video` (Object): Composed video object from Composition Agent
- `progress_updates` (Object, via WebSocket/SSE):
  - `stage` (String): Current stage name
  - `progress` (Number): Progress percentage (0-100)
  - `message` (String): Progress message
  - `clip_index` (Number, optional): Current clip being generated

**Outputs**:
- `video_preview` (HTML5 Video Element): Video player with composed video
- `clip_preview` (Array of HTML5 Video Elements): Individual clip players
- `export_file` (File): MP4 or MOV file download when user clicks export

