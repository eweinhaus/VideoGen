# AI Music Video Generation Pipeline - Product PRD

**Version:** 1.0 | **Date:** November 14, 2025

---

## Executive Summary

An AI-powered pipeline that generates professional, beat-synchronized music videos with consistent visual style informed by music video director expertise. Users upload a song and creative prompt, then receive a complete music video with multiple clips, smooth transitions, and perfect audio sync.

**Timeline:** 72 hours (3 days)  
**Budget:** $2.00/minute maximum ($20 per job hard limit)  
**Quality:** 1080p, 30 FPS, beat-aligned transitions, minimum 3 clips  
**Differentiator:** Integration of music video director knowledge for creative decisions

---

## System Architecture

The pipeline consists of 8 modular components that process jobs sequentially:

```
User Upload → [1] Frontend → [2] API Gateway → [3] Audio Parser
    ↓
[8] Composer ← [7] Video Generator ← [6] Prompt Generator
    ↓                                        ↑
Final Video                        [4] Scene Planner → [5] Reference Generator
```

**Processing Flow:**
1. User uploads audio + prompt via frontend
2. API Gateway creates job, queues for processing
3. Audio Parser extracts beats, lyrics, structure, mood
4. Scene Planner generates video plan using director knowledge
5. Reference Generator creates reference images (scenes + characters)
6. Prompt Generator optimizes prompts for each clip
7. Video Generator creates clips in parallel
8. Composer stitches clips with audio and transitions

**Average Generation Time:** 5-10 minutes for 3-minute song  
**Cost per Video:** $0.60-$1.20 ($0.20-$0.40/minute)

---

## Module 1: Frontend

### Purpose
User-facing web interface for uploading audio, entering creative prompts, tracking generation progress in real-time, and viewing/downloading completed videos.

### Key Features
- **Audio Upload**: Drag-and-drop, MP3/WAV/FLAC, max 10MB
- **Creative Prompt**: 50-500 characters with examples
- **Real-time Progress**: SSE stream with stage updates, ETA (cost tracking via API, UI display post-MVP)
- **Video Player**: Progressive clip rendering, final video playback, download
- **Authentication**: Login, registration, password reset (email/password, Supabase Auth)

### User Flow
1. Register/Login → Upload audio + enter prompt → Submit
2. Redirect to progress page with real-time updates
3. Watch clips appear as they generate
4. Play final video when complete
5. Download MP4

### Input (from User)
```
- audio_file: File (MP3/WAV/FLAC, ≤10MB)
- user_prompt: string (50-500 chars)
```

### Output (to User)
```
- job_id: UUID
- progress: Real-time SSE stream
- video_url: Final composed video
```
*Note: Cost tracking available via API, UI display planned for post-MVP*

### Success Criteria
✅ Upload works (<2s to submit)  
✅ Real-time progress visible (<1s latency)  
✅ Video plays and downloads correctly  
✅ Mobile-responsive  
✅ Handles 5+ concurrent users  

---

## Module 2: API Gateway

### Purpose
REST API server and SSE handler that orchestrates pipeline execution via job queue (BullMQ).

### Key Features
- **REST Endpoints**: Upload, job status, video download, authentication
- **SSE Streaming**: Real-time progress events to frontend
- **Job Queue**: BullMQ + Redis for background processing
- **Pipeline Orchestrator**: Executes modules 3-8 sequentially
- **Cost Tracking**: Aggregate costs per stage, enforce $20 budget limit
- **Budget Enforcement**: Pre-flight cost estimate, real-time tracking, abort if exceeded
- **Concurrency Control**: Max 6 concurrent jobs system-wide (3 per worker × 2 workers)
- **Rate Limiting**: 5 jobs per user per hour (configurable)

### Endpoints
- `POST /api/v1/upload-audio` → Create job, upload to storage
- `GET /api/v1/jobs/{id}` → Job status (polling fallback)
- `GET /api/v1/jobs/{id}/stream` → SSE progress stream
- `GET /api/v1/jobs/{id}/download` → Final video file
- `POST /api/v1/auth/login` → JWT token
- `POST /api/v1/auth/register` → Create account
- `POST /api/v1/auth/reset-password` → Password reset request

### Pipeline Orchestration
```python
1. Audio Parser (10% progress) → audio_data
2. Scene Planner (20% progress) → plan
3. Reference Generator (30% progress) → reference_images
4. Prompt Generator (40% progress) → clip_prompts
5. Video Generator (85% progress) → clips (parallel)
6. Composer (100% progress) → final_video
```
*Note: Progress percentages are cumulative completion markers, not time-weighted*

### Input (from Frontend)
```
- audio_file: File
- user_prompt: string
```

### Output (to Frontend via SSE)
```
Events:
- stage_update: {stage, status, duration}
- progress: {progress, estimated_remaining}
- message: {text, stage}
- cost_update: {stage, cost, total}
- completed: {video_url, total_cost}
- error: {error, code, retryable}
```

### Success Criteria
✅ Jobs created and tracked  
✅ SSE delivers updates (<1s latency)  
✅ Background processing works  
✅ Errors handled gracefully  
✅ Cost tracking accurate (±$0.10)  
✅ Budget limit enforced (abort if >$20)  
✅ Concurrency limits respected (max 6 jobs)  
✅ Rate limiting prevents abuse  

---

## Module 3: Audio Parser

### Purpose
Comprehensive audio analysis to extract beats (±50ms precision), song structure, lyrics, and mood. Provides creative foundation for all downstream decisions.

### Key Features
- **Beat Detection**: Librosa + Aubio for 90%+ accuracy within ±50ms
- **Tempo (BPM)**: Extract tempo, validate 60-200 range
- **Song Structure**: Classify intro/verse/chorus/bridge/outro sections
- **Lyrics**: OpenAI Whisper API with word-level timestamps
- **Mood**: Rule-based classification (energetic, calm, dark, bright)
- **Clip Boundaries**: Beat-aligned boundaries, 4-8s clips, minimum 3
- **Caching**: Redis cache by audio file hash (24h TTL)
- **Boundary Ownership**: Audio Parser generates initial boundaries; Scene Planner can refine based on narrative needs (must stay within ±2s of beat-aligned boundaries)

### Fallback Strategies
- **Beat detection fails**: Use tempo-based boundaries (4-beat intervals)
- **Lyrics fail**: Return empty array (instrumental)
- **Low confidence**: Flag for review, proceed with best-effort

### Input
```
- job_id: UUID
- audio_url: string (Supabase Storage URL)
```

### Output
```json
{
  "job_id": "uuid",
  "bpm": 128.5,
  "duration": 185.3,
  "beat_timestamps": [0.5, 1.0, 1.5, ...],
  "song_structure": [
    {"type": "intro", "start": 0.0, "end": 8.5, "energy": "low"},
    {"type": "verse", "start": 8.5, "end": 30.2, "energy": "medium"},
    {"type": "chorus", "start": 30.2, "end": 50.5, "energy": "high"}
  ],
  "lyrics": [
    {"text": "I see the lights", "timestamp": 10.5}
  ],
  "mood": {
    "primary": "energetic",
    "secondary": "uplifting",
    "energy_level": "high",
    "confidence": 0.85
  },
  "clip_boundaries": [
    {"start": 0.0, "end": 5.2, "duration": 5.2}
  ],
  "metadata": {
    "processing_time": 45.2,
    "cache_hit": false,
    "beat_detection_confidence": 0.92,
    "fallback_used": false
  }
}
```

### Success Criteria
✅ Process 3-min song in <60s  
✅ BPM ±2 for 80%+ songs  
✅ Beats 90%+ within ±50ms  
✅ Structure 70%+ accurate  
✅ Lyrics >70% accurate (gracefully handles instrumental tracks with empty lyrics)  
✅ Caching works  
✅ Auto-retry: 3 attempts for Whisper API with exponential backoff (2s, 4s, 8s)  

---

## Module 4: Scene Planner

### Purpose
Generate comprehensive video plan using **music video director knowledge** to create professional scripts that match song mood, structure, and lyrics.

### Key Features
- **Director Knowledge Integration**: Apply expert techniques for mood/energy
- **Video Planning**: Characters, scenes, objects, style consistency
- **Clip Scripts**: Detailed visual descriptions aligned to beat boundaries
- **Transition Planning**: Cut/crossfade/fade based on beat intensity
- **Style Guide**: Color palette, cinematography, lighting, mood

### Director Knowledge Application
- Visual metaphors for lyrical themes
- Color palettes for different moods (energetic → vibrant, calm → muted)
- Camera movements for energy levels (high energy → fast cuts, low → static)
- Transition styles (strong beat → hard cut, soft → crossfade)
- Lighting techniques (dark mood → low-key, bright → high-key)

### Input
```
- job_id: UUID
- user_prompt: string
- audio_data: JSON (from Audio Parser)
```

### Output
```json
{
  "job_id": "uuid",
  "video_summary": "A lone figure walks through neon-lit streets...",
  "characters": [
    {
      "id": "protagonist",
      "description": "Young woman, 25-30, futuristic jacket",
      "role": "main character"
    }
  ],
  "scenes": [
    {
      "id": "city_street",
      "description": "Rain-slicked cyberpunk street with neon signs",
      "time_of_day": "night"
    }
  ],
  "style": {
    "color_palette": ["#00FFFF", "#FF00FF", "#0000FF"],
    "visual_style": "Neo-noir cyberpunk with rain and neon",
    "mood": "Melancholic yet hopeful",
    "lighting": "High-contrast neon with deep shadows",
    "cinematography": "Handheld, slight shake, tracking shots"
  },
  "clip_scripts": [
    {
      "clip_index": 0,
      "start": 0.0,
      "end": 5.2,
      "visual_description": "Protagonist walks toward camera through rain",
      "motion": "Slow tracking shot following character",
      "camera_angle": "Medium wide, slightly low angle",
      "characters": ["protagonist"],
      "scenes": ["city_street"],
      "lyrics_context": "I see the lights shining bright",
      "beat_intensity": "medium"
    }
  ],
  "transitions": [
    {
      "from_clip": 0,
      "to_clip": 1,
      "type": "crossfade",
      "duration": 0.5,
      "rationale": "Smooth transition for continuous motion"
    }
  ]
}
```

### Success Criteria
✅ Scripts for all clips generated  
✅ Style consistent across clips  
✅ Scripts align to beat boundaries  
✅ Director knowledge applied  
✅ Valid JSON output  
✅ Auto-retry: 3 attempts for LLM with exponential backoff (2s, 4s, 8s)  
✅ Fallback: If LLM fails after retries, generate simple scene descriptions based on audio mood/energy  

---

## Module 5: Reference Generator

### Purpose
Generate reference images for all scenes and characters using SDXL to establish visual consistency across all video clips.

### Key Features
- **Model**: Stable Diffusion XL via Replicate
- **Scene References**: One reference image per unique scene location/setting
- **Character References**: One reference image per character for consistency
- **Parallel Generation**: Generate all reference images concurrently
- **Prompt Synthesis**: Combine style info from scene planner with character/scene descriptions
- **Settings**: 1024x1024, 30-40 steps, guidance 7-9
- **Storage**: Images stored in Supabase Storage, 14-day retention, auto-cleanup

### Fallback
- **If generation fails**: Proceed with text-only prompts (no reference image) for video generation
- **Text-only mode**: Video prompts include style keywords but no visual reference image
- **Retry**: 3 attempts with exponential backoff (2s, 4s, 8s) before fallback

### Input
```
- job_id: UUID
- plan: JSON (from Scene Planner)
```

### Output
```json
{
  "job_id": "uuid",
  "scene_references": [
    {
      "scene_id": "city_street",
      "image_url": "https://storage.supabase.co/.../scene_city_street.png",
      "prompt_used": "Rain-slicked cyberpunk street with neon signs...",
      "generation_time": 8.5,
      "cost": 0.005
    }
  ],
  "character_references": [
    {
      "character_id": "protagonist",
      "image_url": "https://storage.supabase.co/.../char_protagonist.png",
      "prompt_used": "Young woman, 25-30, futuristic jacket, cyberpunk style...",
      "generation_time": 8.2,
      "cost": 0.005
    }
  ],
  "total_references": 4,
  "total_generation_time": 32.5,
  "total_cost": 0.020,
  "status": "success",
  "metadata": {
    "dimensions": "1024x1024",
    "format": "PNG",
    "scenes_generated": 2,
    "characters_generated": 2
  }
}
```

### Success Criteria
✅ All scene and character images generated in <60s total (parallel generation)
✅ Images match scene/character descriptions  
✅ 1024x1024 dimensions  
✅ Cost <$0.01 per image (typically 2-4 images total)
✅ Fallback works (text-only mode if generation fails)  
✅ Auto-retry: 3 attempts per image with exponential backoff (2s, 4s, 8s)  
✅ Partial success: Accept if ≥50% of images generated successfully  

---

## Module 6: Prompt Generator

### Purpose
Optimize video generation prompts by combining clip scripts with style information into concise, high-quality prompts.

### Key Features
- **Prompt Synthesis**: Visual description + style + camera + quality modifiers
- **Consistency**: Same style keywords in all prompts
- **Conciseness**: <200 words per prompt
- **Batch Generation**: All prompts in one pass

### Prompt Structure
```
{visual_description}, {motion}, {camera_angle}, 
{visual_style} aesthetic with {color_palette}, 
cinematic lighting, highly detailed, professional cinematography, 4K
```

### Input
```
- job_id: UUID
- plan: JSON (from Scene Planner)
- reference: JSON (from Reference Generator)
```

### Output
```json
{
  "job_id": "uuid",
  "clip_prompts": [
    {
      "clip_index": 0,
      "prompt": "A lone figure walks toward camera...",
      "negative_prompt": "blurry, static, low quality",
      "duration": 5.2,
      "scene_reference_url": "https://storage.supabase.co/.../scene_city_street.png",
      "character_reference_urls": [
        "https://storage.supabase.co/.../char_protagonist.png"
      ],
      "metadata": {
        "word_count": 45,
        "style_keywords": ["cyberpunk", "neon", "rain"],
        "scene_id": "city_street",
        "character_ids": ["protagonist"],
        "validated": true
      }
    }
  ],
  "total_clips": 6,
  "generation_time": 2.1
}
```

### Success Criteria
✅ Prompts for all clips  
✅ Consistent style keywords  
✅ <200 words each  
✅ Generation <5s  

---

## Module 7: Video Generator

### Purpose
Generate video clips in **parallel** (5 concurrent) using text-to-video models with retry logic and duration handling.

### Key Features
- **Parallel Processing**: 5 clips concurrently (saves 60-70% time)
- **Model**: Stable Video Diffusion via Replicate (primary), CogVideoX (fallback if SVD unavailable)
- **Reference Images**: Uses scene_reference_url and character_reference_urls from each clip prompt
- **Multi-reference Strategy**: 
  - Primary: Use scene_reference_url as main reference (most models accept one image)
  - Character consistency: Include character descriptions in text prompt, reference image URLs in metadata for potential future multi-reference support
  - Fallback: If multiple character references needed, composite them into single image via image blending (post-MVP)
- **Duration Strategy**: Request closest available duration, accept ±2s tolerance
- **Retry Logic**: 3 attempts per clip with exponential backoff
- **Progress Updates**: SSE event after each clip completes
- **Partial Success**: Accept ≥3 clips (don't require all)
- **Resolution**: Generate at 1024x576 (16:9) for optimal upscaling to 1080p

### Generation Settings
```
- Resolution: 1024x576 (16:9, preferred) or 768x768 (square, fallback)
- FPS: 24-30
- Motion amount: 127 (medium)
- Steps: 20-30
- Timeout: 120s per clip
```

### Input
```
- job_id: UUID
- clip_prompts: JSON array (from Prompt Generator)
```

### Output
```json
{
  "job_id": "uuid",
  "clips": [
    {
      "clip_index": 0,
      "video_url": "https://storage.supabase.co/.../clip_0.mp4",
      "actual_duration": 5.4,
      "target_duration": 5.2,
      "duration_diff": 0.2,
      "status": "success",
      "cost": 0.06,
      "retry_count": 0,
      "generation_time": 45.2
    }
  ],
  "total_clips": 6,
  "successful_clips": 6,
  "failed_clips": 0,
  "total_cost": 0.36,
  "total_generation_time": 90.5
}
```

### Success Criteria
✅ ≥3 clips generated  
✅ Parallel generation works  
✅ Duration ±2s tolerance  
✅ Retry logic works  
✅ Cost <$1 per clip  
✅ Total time <180s for 6 clips  

---

## Module 8: Composer

### Purpose
Stitch video clips with beat-aligned transitions, sync original audio, and produce final MP4 video.

### Key Features
- **Duration Handling**:
  - Trim clips if too long (from end, stay on beat)
  - Loop clips if too short: Repeat entire clip until target duration reached (e.g., 2.5s clip → loop 2x for 5s target)
  - Never extend without looping
- **Resolution & Upscaling**: 
  - Input clips: 1024x576 (16:9) from Video Generator
  - Upscale to 1080p (1920x1080) using FFmpeg lanczos filter (high quality)
  - Normalize all clips to 30 FPS, 1080p before composition
- **Transitions**: Cut (0s), crossfade (0.5s), fade (0.5s) at beat boundaries
- **Audio Sync**: Perfect sync (±100ms tolerance)
- **Output**: MP4 (H.264, AAC, 5000k bitrate)

### Fallback Strategies
- **Transition fails**: Use simple cut
- **Duration mismatch >1s**: Adjust video speed ±5%
- **<3 clips available**: Fail job (minimum not met)
- **FFmpeg errors**: Retry composition once, then fail with detailed error message

### Input
```
- job_id: UUID
- clips: JSON array (from Video Generator)
- audio_url: string
- transitions: JSON array (from Scene Planner)
- beat_timestamps: array (from Audio Parser)
```

### Output
```json
{
  "job_id": "uuid",
  "video_url": "https://storage.supabase.co/.../final_video.mp4",
  "duration": 185.3,
  "audio_duration": 185.3,
  "sync_drift": 0.05,
  "clips_used": 6,
  "clips_trimmed": 4,
  "clips_looped": 2,
  "transitions_applied": 5,
  "file_size_mb": 45.2,
  "composition_time": 60.5,
  "cost": 0.0,
  "status": "success"
}
```

### Success Criteria
✅ Duration matches audio (±0.1s)  
✅ Transitions at beat boundaries  
✅ No A/V drift (<100ms)  
✅ Valid MP4 output  
✅ Composition <90s  

---

## Data Flow Summary

```
User Input
  ↓
[1] Frontend: Upload → job_id
  ↓
[2] API Gateway: Queue job → audio_url, user_prompt
  ↓
[3] Audio Parser: Analyze → audio_data (beats, lyrics, structure, mood)
  ↓
[4] Scene Planner: Plan → plan (scripts, characters, scenes, style, transitions)
  ↓
[5] Reference Generator: Generate → scene_references + character_references (multiple images)
  ↓
[6] Prompt Generator: Optimize → clip_prompts (includes scene + character reference URLs)
  ↓
[7] Video Generator: Generate (parallel, using scene + character references) → clips (video files)
  ↓
[8] Composer: Stitch → final_video
  ↓
[1] Frontend: Display/Download → video_url
```

---

## Error Handling & Recovery

### Job Failure Modes
- **Module Failure**: Individual module fails after all retries → Job marked as failed, user notified via SSE
- **Budget Exceeded**: Cost tracking detects >$20 mid-execution → Abort immediately, mark as failed
- **Timeout**: Job exceeds 15-minute timeout → Mark as failed, cleanup resources
- **Partial Success**: Video Generator produces <3 clips → Job fails (minimum not met)

### User Notification
- **SSE Error Events**: Real-time error messages with retryable flag
- **Error Codes**: Standardized codes (GENERATION_ERROR, BUDGET_EXCEEDED, TIMEOUT, VALIDATION_ERROR)
- **Retryable vs Non-retryable**: User can retry non-retryable errors manually

### Cleanup & Storage
- **Failed Jobs**: Intermediate files deleted after 7 days (for debugging)
- **Completed Jobs**: Final video retained 14 days, intermediate files deleted immediately
- **Storage Limits**: 10GB per user (post-MVP: configurable tiers)

---

## Success Criteria (MVP)

### Functional
✅ User uploads audio + prompt and receives complete video  
✅ Minimum 3 clips per video  
✅ Beat-aligned transitions  
✅ Audio synced perfectly (±100ms)  
✅ Real-time progress updates  
✅ Download final MP4  

### Quality
✅ 1080p, 30 FPS  
✅ Consistent visual style  
✅ Professional-looking (director knowledge applied)  
✅ No A/V drift  

### Performance
✅ 30s video: <5 min generation  
✅ 3-min video: <10 min generation  
✅ Progress updates <1s latency  

### Cost
✅ <$2/minute ($0.60-$1.20 typical)  
✅ Hard limit: $20/job  

### Reliability
✅ 90%+ success rate  
✅ Individual failures don't stop pipeline  
✅ Graceful error recovery  
✅ Budget enforcement prevents cost overruns  
✅ Storage cleanup prevents accumulation  
✅ Rate limiting prevents abuse  

---

## Future Enhancements (Post-MVP)

**Performance**
- GPU acceleration for local processing
- Batch prompt generation with LLM caching
- Multiple reference images (character, scene, object)

**Quality**
- LoRA models for character consistency
- Previous clip context for narrative continuity
- Advanced transitions (wipe, dissolve, zoom)
- Beat timing within clips (micro-beats)

**Features**
- Multiple aspect ratios (16:9, 1:1, 9:16)
- Text overlays synced to lyrics
- Video editor UI with timeline
- Clip regeneration (regenerate specific clips)

**Analysis**
- Instrument detection and prominence
- Musical key extraction
- Genre classification
- Advanced mood analysis (valence, arousal)

---

## Development Roadmap

**Day 1 (Friday) - Foundation**
- Setup: Repository, database, Supabase, Railway
- Module 1: Frontend (upload, progress, player, auth)
- Module 2: API Gateway (REST + SSE, cost tracking, budget enforcement)
- Module 3: Audio Parser (BPM, beats, lyrics)

**Day 2 (Saturday) - Generation**
- Module 4: Scene Planner (LLM integration)
- Module 5: Reference Generator (SDXL)
- Module 6: Prompt Generator
- Module 7: Video Generator (parallel)
- Test: End-to-end (may fail at composition)

**Day 3 (Sunday) - Composition + Polish**
- Module 8: Composer (FFmpeg)
- Testing: Full pipeline with 3+ diverse genres (electronic, rock, ambient/calm)
- Polish: Error handling, auto-retry logic validation, loading states
- Deploy: Final deployment + documentation

---

**Document Status:** Ready for Implementation  
**Total Estimated Time:** 60-72 hours (3 days with 2-3 people)  
**Next Action:** Review Technical Spec PRD, then begin Module 1+2