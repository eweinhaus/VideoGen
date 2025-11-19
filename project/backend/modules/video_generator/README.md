# Module 7: Video Generator

**Tech Stack:** Python (Stable Video Diffusion / CogVideoX via Replicate)

## Purpose
Generate video clips in **parallel** (5 concurrent) using text-to-video models with retry logic and duration handling.

## Key Features
- Parallel Processing (5 clips concurrently, saves 60-70% time)
- Model: Stable Video Diffusion or CogVideoX via Replicate
- Reference Images (uses scene_reference_url and character_reference_urls)
- Multi-reference (combines scene background with character references)
- Duration Strategy (request closest available duration, accept ±2s tolerance)
- Retry Logic (3 attempts per clip with exponential backoff)
- Progress Updates (SSE event after each clip completes)
- Partial Success (accept ≥3 clips, don't require all)
- **Thumbnail Generation** (async, non-blocking): Automatically generates thumbnails for all clips during video generation

## Generation Settings
- Resolution: 1024x576 or 768x768
- FPS: 24-30
- Motion amount: 127 (medium)
- Steps: 20-30
- Timeout: 120s per clip
- Aspect Ratio: User-selectable (16:9, 9:16, 1:1, 4:3, 3:4) - varies by model

## Duration Buffer Configuration

The video generator implements a buffer strategy to request longer durations than targets, ensuring adequate clip length for cascading compensation.

### Environment Variable
- `VIDEO_GENERATOR_DURATION_BUFFER`: Buffer multiplier for continuous models (default: 1.25 = 25% buffer)
  - Only applies to models with continuous duration support (e.g., Veo 3.1)
  - Discrete models (Kling, etc.) use maximum buffer strategy instead

### Buffer Strategies

#### Discrete Models (Kling, etc.)
- **Maximum Buffer Strategy**: Always request the maximum supported duration
  - Targets ≤5s: Request 5s (no buffer possible due to model constraints)
  - Targets >5s: Request 10s (maximum available, may exceed 25% buffer)
- **Cost Impact**: Discrete models may have >20% cost increase for targets 5.1-7.5s (requesting 10s instead of 5s)
- This is acceptable per PRD and should be monitored

#### Continuous Models (Veo 3.1, etc.)
- **Percentage Buffer Strategy**: Apply configurable percentage buffer
  - Request `min(target * buffer_multiplier, 10.0)` (25% buffer default, capped at 10s)
  - Configurable via `VIDEO_GENERATOR_DURATION_BUFFER` env var
- **Cost Impact**: <20% average increase (25% buffer)

## Thumbnail Generation

The video generator automatically generates thumbnails for all clips during video generation. This is an **async, non-blocking** operation that doesn't interfere with the video generation pipeline.

### How It Works

1. **After Clip Upload**: When a clip is successfully uploaded to Supabase Storage, a thumbnail generation task is started asynchronously
2. **FFmpeg Extraction**: Uses FFmpeg to extract the first frame from the video
3. **Resize**: Resizes the frame to 320x180 (16:9 aspect ratio) for optimal display
4. **Storage**: Uploads thumbnail to `clip-thumbnails` bucket in Supabase Storage
5. **Database**: Stores thumbnail URL in `clip_thumbnails` table

### Implementation

- **Module**: `modules/video_generator/thumbnail_generator.py`
- **Function**: `generate_clip_thumbnail(clip_url, job_id, clip_index)`
- **Integration**: Called via `asyncio.create_task()` after clip upload (fire-and-forget)
- **Error Handling**: Failures are logged but don't block video generation

### Configuration

- **Thumbnail Size**: 320x180 pixels (16:9 aspect ratio)
- **Format**: JPEG
- **Quality**: High quality (`-q:v 2`)
- **Storage Bucket**: `clip-thumbnails` (private)
- **Storage Path**: `{job_id}/clip_{clip_index}_thumbnail.jpg`

### Performance

- **Generation Time**: ~200-400ms per thumbnail (async, non-blocking)
- **Impact**: No impact on video generation pipeline (runs in background)
- **Failure Handling**: Missing thumbnails show placeholder in UI

### Original Target Duration
- The original target duration (before buffer) is preserved in the `Clip` model as `original_target_duration`
- This is used by Part 2 (Composer Cascading Compensation) for the compensation algorithm
- If not explicitly set, defaults to `target_duration` for backward compatibility

## Aspect Ratio Support

The video generator supports user-selectable aspect ratios that vary by model. Aspect ratios are validated against each model's supported list before generation.

### Supported Aspect Ratios by Model

- **Kling v2.1**: 16:9 (uses resolution parameter) ⚠️ LIMITED
- **Kling v2.5 Turbo**: 16:9, 9:16, 1:1, 4:3, 3:4 (uses resolution parameter)
- **Hailuo 2.3**: 16:9, 9:16, 1:1 (uses aspect_ratio parameter)
- **Wan 2.5 i2v**: 16:9, 1:1, 9:16 (uses aspect_ratio parameter)
- **Veo 3.1**: 16:9, 9:16 (uses aspect_ratio parameter) ⚠️ LIMITED - ONLY these two ratios supported

### Parameter Mapping

Some models require resolution strings instead of aspect ratios:
- **Kling models**: Use `resolution` parameter with mapping (e.g., "16:9" → "1080p")
- **Other models**: Use `aspect_ratio` or `ratio` parameter directly

The generator automatically maps aspect ratios to the correct format based on each model's configuration.

### Validation

- Aspect ratio is validated against model's supported list before generation
- Raises `ValidationError` if aspect ratio not supported for selected model
- Default aspect ratio: "16:9" (used if not specified)

### Important Notes

⚠️ **Critical**: If an unsupported aspect ratio is selected, **ALL clips will fail immediately** with `ValidationError`. This prevents wasted API calls but requires frontend validation to prevent user confusion.

**Limited Support Models:**
- **Kling v2.1**: Only supports 16:9
- **Veo 3.1**: Only supports 16:9 and 9:16

Always verify the selected model supports the desired aspect ratio before starting generation.



