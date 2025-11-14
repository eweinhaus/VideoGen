# AI Music Video Generation Pipeline - Technical Specification

**Version:** 1.0 | **Date:** November 14, 2025

---

## Tech Stack Decisions

### Backend
- **Framework**: FastAPI 0.104+ (async support, type safety, fast development)
- **Queue**: BullMQ + Redis (Bull Board UI for monitoring, better than Celery)
- **Database**: Supabase PostgreSQL (managed, auto REST API, RLS policies)
- **Storage**: Supabase Storage (S3-compatible, signed URLs, integrated auth)
- **Auth**: Supabase Auth (JWT tokens, built-in, no custom logic)

### Frontend
- **Framework**: Next.js 14 App Router (file-based routing, SSR, Vercel deploy)
- **Language**: TypeScript 5.3+ (type safety)
- **UI**: shadcn/ui (Radix primitives + Tailwind)
- **State**: Zustand (simple, performant)
- **Real-time**: Server-Sent Events (SSE, simpler than WebSocket for one-way updates)

### AI/ML Services
- **Audio Analysis**: Librosa 0.10.1 + Aubio 0.4.9
- **Lyrics**: OpenAI Whisper API
- **Planning**: OpenAI GPT-4o or Claude 3.5 Sonnet
- **Image Gen**: Stable Diffusion XL via Replicate
- **Video Gen**: Stable Video Diffusion or CogVideoX via Replicate
- **Video Processing**: FFmpeg (industry standard, free)

### Deployment
- **Backend**: Railway (better DX than Render, built-in Redis)
- **Frontend**: Vercel (zero-config Next.js deployment)
- **Database/Storage**: Supabase (managed)

---

## API Specifications

### Base URL
```
Production: https://api.musicvideo.app/api/v1
Development: http://localhost:8000/api/v1
```

### Authentication
JWT Bearer token (all endpoints except `/auth/login`):
```
Authorization: Bearer <jwt_token>
```

---

### POST /api/v1/upload-audio

**Request**:
```
Content-Type: multipart/form-data

Body:
  audio_file: File (required, MP3/WAV/FLAC, ≤10MB)
  user_prompt: string (required, 50-500 chars)
```

**Response 200**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "audio_url": "https://storage.supabase.co/...",
  "status": "queued",
  "estimated_time": 600
}
```

**Implementation**:
1. Validate: MIME type (audio/*), size ≤10MB
2. Upload to Supabase Storage: `audio-uploads/{user_id}/{job_id}/{file}`
3. Generate signed URL (24h expiration)
4. Create job record (status='queued')
5. Add to BullMQ queue
6. Return job_id

---

### GET /api/v1/jobs/{job_id}

**Response 200**:
```json
{
  "job_id": "550e8400-...",
  "status": "processing",
  "current_stage": "video_generation",
  "progress": 65,
  "stages": {
    "audio_analysis": {"status": "completed", "duration": 45},
    "scene_planning": {"status": "completed", "duration": 30},
    "video_generation": {"status": "processing", "progress": "3/6"}
  },
  "estimated_remaining": 180,
  "costs": {"total": 0.85},
  "video_url": null
}
```

**Purpose**: Polling fallback if SSE unavailable

---

### GET /api/v1/jobs/{job_id}/stream (SSE)

**Request**:
```
Accept: text/event-stream
```

**Event Types**:
```
event: stage_update
data: {"stage": "audio_analysis", "status": "completed", "duration": 45}

event: progress
data: {"progress": 25, "estimated_remaining": 450}

event: message
data: {"text": "Generating clip 3/6", "stage": "video_generation"}

event: cost_update
data: {"stage": "video_generation", "cost": 0.06, "total": 0.85}

event: completed
data: {"video_url": "https://storage...", "total_cost": 1.20}

event: error
data: {"error": "Generation failed", "code": "GENERATION_ERROR", "retryable": true}
```

**Connection**: Keep-alive 30s, client auto-reconnects

---

### GET /api/v1/jobs/{job_id}/download

**Response 200**:
```
Content-Type: video/mp4
Content-Disposition: attachment; filename="music_video_{timestamp}.mp4"
[Binary video data]
```

---

### POST /api/v1/auth/login

**Request**:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response 200**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**Implementation**: Supabase Auth `sign_in_with_password()`

---

### POST /api/v1/auth/register

**Request**:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response 200**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**Implementation**: Supabase Auth `sign_up()`

---

### POST /api/v1/auth/reset-password

**Request**:
```json
{
  "email": "user@example.com"
}
```

**Response 200**:
```json
{
  "message": "Password reset email sent"
}
```

**Implementation**: Supabase Auth `reset_password_for_email()`

---

## Database Schema

### jobs
```sql
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  status VARCHAR(20) CHECK (IN ('queued', 'processing', 'completed', 'failed')),
  audio_url TEXT NOT NULL,
  user_prompt TEXT NOT NULL,
  current_stage VARCHAR(50),
  progress INTEGER DEFAULT 0 CHECK (0-100),
  estimated_remaining INTEGER,
  total_cost DECIMAL(10,2) DEFAULT 0.00,
  video_url TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at DESC);
```

### job_stages
```sql
CREATE TABLE job_stages (
  id UUID PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  stage_name VARCHAR(50),
  status VARCHAR(20),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  duration_seconds INTEGER,
  cost DECIMAL(10,4),
  metadata JSONB
);

CREATE INDEX idx_job_stages_job ON job_stages(job_id);
```

### job_costs
```sql
CREATE TABLE job_costs (
  id UUID PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  stage_name VARCHAR(50),
  api_name VARCHAR(50),  -- whisper, sdxl, svd
  cost DECIMAL(10,4),
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_job_costs_job ON job_costs(job_id);
```

### audio_analysis_cache
```sql
CREATE TABLE audio_analysis_cache (
  file_hash VARCHAR(32) PRIMARY KEY,  -- MD5
  analysis_data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE INDEX idx_audio_cache_expires ON audio_analysis_cache(expires_at);
```

---

## Storage Configuration

### Supabase Buckets

**audio-uploads** (private):
- Path: `{user_id}/{job_id}/{filename}`
- Max size: 10MB
- Retention: 14 days
- CORS: Allow from frontend domain
- Auto-cleanup: Delete after 14 days or immediately after job completion (if failed)

**reference-images** (private):
- Path: `{job_id}/scene_{scene_id}.png` or `{job_id}/char_{character_id}.png`
- Retention: 14 days

**video-clips** (private):
- Path: `{job_id}/clip_{index}.mp4`
- Retention: Delete immediately after successful composition (intermediate files)
- Failed jobs: Retain for 7 days for debugging

**video-outputs** (private):
- Path: `{job_id}/final_video.mp4`
- Retention: 14 days
- Signed URLs: 1 hour expiration
- Storage limits: 10GB per user (post-MVP: configurable tiers)

---

## Key Implementation Patterns

### Audio Parser (Module 3)
- **Beat Detection**: librosa.beat.beat_track + aubio onset detector → merge → deduplicate (50ms threshold)
- **Fallback**: If confidence <0.6, use tempo-based boundaries (4-beat intervals)
- **Lyrics**: OpenAI Whisper API with word timestamps
- **Structure**: Chroma features → recurrence matrix → agglomerative clustering → heuristic classification
- **Caching**: Redis key = MD5(audio_file), TTL = 24h
- **Clip Boundaries**: Generates initial beat-aligned boundaries (4-8s clips, min 3)
- **Boundary Ownership**: Audio Parser generates initial boundaries; Scene Planner can refine within ±2s for narrative needs

### Scene Planner (Module 4)
- **LLM Prompt**: System context with director knowledge + user prompt + audio analysis → JSON output
- **Validation**: Pydantic models for all output structures
- **Director Knowledge**: Visual metaphors, color palettes, camera movements, transition styles, lighting

### Reference Generator (Module 5)
- **Multiple References**: Generates one image per scene and one per character
- **Parallel Generation**: All reference images generated concurrently for speed
- **Scene References**: Capture setting, lighting, color palette for each unique location
- **Character References**: Ensure character consistency across all clips
- **Fallback**: Text-only mode (no reference images, style keywords in prompts only)
- **Retry**: 3 attempts per image with exponential backoff (2s, 4s, 8s)
- **Typical Count**: 2-4 reference images per video (e.g., 2 scenes + 2 characters)

### Video Generator (Module 7)
- **Parallel**: asyncio.Semaphore(5) for 5 concurrent clips
- **Retry**: 3 attempts with exponential backoff (2s, 4s, 8s)
- **Replicate API**: Stable Video Diffusion (primary) with motion_bucket_id=127, steps=25, CogVideoX (fallback)
- **Reference Images**: Uses scene_reference_url as primary reference (one image per model call)
- **Multi-reference Strategy**: 
  - Primary: scene_reference_url used as main reference image
  - Character consistency: Character descriptions included in text prompt
  - Character reference URLs stored in metadata for potential future multi-reference support
  - Post-MVP: Image compositing for multiple character references
- **Resolution**: Generate at 1024x576 (16:9) for optimal upscaling to 1080p
- **Fallback**: If no reference images available, use text-to-video mode with prompts only
- **Partial Success**: Accept ≥3 clips, fail if <3

### Composer (Module 8)
- **FFmpeg Pipeline**: Process clips (trim/loop/normalize/upscale) → build filter_complex → concatenate with audio
- **Resolution & Upscaling**: 
  - Input: 1024x576 (16:9) clips from Video Generator
  - Upscale: 1920x1080 using lanczos filter (high quality)
  - Normalize: All clips to 30 FPS, 1080p before composition
- **Transitions**: Cut (concat), Crossfade (xfade), Fade (fade in/out)
- **Duration**: 
  - Trim if long (from end, stay on beat)
  - Loop if short: Repeat entire clip until target duration (e.g., 2.5s clip → loop 2x for 5s)
  - Never extend without looping

---

## Frontend Architecture

**Stack**: Next.js 14 + TypeScript + shadcn/ui + Zustand + SSE

**Directory**:
```
frontend/
├── app/(auth)/login, upload, jobs/[jobId]
├── components/AudioUploader, ProgressTracker, VideoPlayer
├── lib/api.ts, stores/, hooks/useSSE.ts
```

**useSSE Hook**:
```typescript
useEffect(() => {
  const eventSource = new EventSource(url, { withCredentials: true })
  eventSource.onopen = () => setConnected(true)
  ;['progress', 'stage_update', 'completed', 'error'].forEach(event => {
    eventSource.addEventListener(event, (e) => handlers.onMessage(event, JSON.parse(e.data)))
  })
  return () => eventSource.close()
}, [url])
```

**Zustand Store**: jobStore (job, setJob, updateJob), authStore (token, login, logout)

---

## Error Handling

**Strategies**:
- Validation (400): Return immediately, no retries
- API errors (5xx): Retry 3x with exponential backoff (2s, 4s, 8s)
- Timeouts:
  - Whisper API: 60s per request
  - GPT-4o/Claude: 90s per request
  - SDXL: 30s per image
  - Video generation: 120s per clip
  - FFmpeg composition: 120s
  - Pipeline total: 15 minutes
- Fallbacks: 
  - Beat detection → tempo-based boundaries
  - Lyrics extraction → empty array (instrumental)
  - Scene planning LLM → simple mood-based descriptions
  - Reference generation → text-only prompts (no image)
  - <3 clips generated → fail job
  - FFmpeg errors → retry once, then fail

**Retry Details**:
- **Audio Parser**: Whisper API - 3 attempts with exponential backoff
- **Scene Planner**: LLM - 3 attempts with exponential backoff
- **Reference Generator**: SDXL - 3 attempts with exponential backoff
- **Video Generator**: Per-clip - 3 attempts with exponential backoff
- **Composer**: FFmpeg - 1 retry on failure

**Budget Guard**: 
- Pre-flight cost estimate before job starts (based on audio duration)
- Real-time cost tracking per API call
- Abort immediately if total cost >$20/job mid-execution
- Mark job as failed with BUDGET_EXCEEDED error code

---

## Cost Tracking

**Implementation**: Track per-API-call, aggregate per stage/job, enforce $20 budget limit

**Estimated Costs**:
- Audio: $0.02 (Whisper) | Scene: $0.05 (GPT-4o) | Reference: $0.02-0.04 (SDXL, 2-4 images)
- Video: $0.60 (6 clips × $0.10) | Composer: $0
- **Total**: ~$0.69-$0.71 per 3-min video = $0.23-$0.24/min ✅

---

## Deployment

**Railway**: FastAPI + BullMQ worker + Redis (Bull Board at /admin/queues)  
**Vercel**: Next.js frontend (auto-deploy on push to main)  
**Supabase**: PostgreSQL + Storage + Auth (managed)

**BullMQ Configuration**:
- Workers: 2 workers for job processing
- Concurrency: Max 3 concurrent jobs per worker (6 total system-wide)
- Redis connection pooling: 10 connections
- Job timeout: 15 minutes per job
- Failed job retention: 7 days for debugging

**Rate Limiting**:
- Per-user: 5 jobs per hour (configurable)
- Implementation: Redis-based sliding window counter
- Response: 429 Too Many Requests with retry-after header

**Env Variables**:
- Backend: SUPABASE_URL/SERVICE_KEY, REDIS_URL, OPENAI_API_KEY, REPLICATE_API_TOKEN, JWT_SECRET_KEY
- Frontend: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL/ANON_KEY

---

## Testing

**Unit**: Audio (BPM, beat deduplication), Scene (JSON validation), Prompt (length), Composer (duration calc)  
**Integration**: Full pipeline, API endpoints, SSE streaming, error handling  
**Manual E2E**: Upload → progress → download, test 3+ diverse genres (electronic, rock, ambient) to validate pipeline flexibility across different music styles

---

## Performance & Monitoring

**Optimization**: Parallel video generation (70% time savings), audio analysis caching (20-30% hit rate), progressive rendering  
**Logging**: Structured with job_id, stage, duration, cost, success  
**Metrics**: Pipeline success rate (90%+), avg generation time, cost/video, API error rates

---

**Document Status:** Ready for Implementation  
**Estimated Setup Time:** 4-6 hours (infrastructure + deployment)  
**Next Action:** Setup Railway + Supabase + Vercel, then begin coding