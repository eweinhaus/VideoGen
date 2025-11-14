# Module 2: API Gateway - Product Requirements Document

**Version:** 1.0 | **Date:** November 14, 2025  
**Priority:** CRITICAL - Core infrastructure for pipeline orchestration  
**Budget:** 
- **Production/Final Submission:** $200 per video, $2000 per job hard limit
- **Development/Testing:** ~$2-5 per video (using cheaper models), $50 per job hard limit

---

## Executive Summary

The API Gateway is the central orchestration layer that coordinates the entire video generation pipeline. It provides REST endpoints for job submission, real-time progress streaming via SSE, background job processing via BullMQ, and enforces budget limits and rate limiting. The gateway orchestrates modules 3-8 sequentially, tracks costs in real-time, and delivers progress updates to the frontend.

**Timeline:** 8-10 hours (Day 1)  
**Dependencies:** Shared components (complete), Infrastructure setup (Supabase, Redis)  
**Blocks:** Frontend integration, all pipeline modules

---

## Purpose

The API Gateway serves as:
1. **Entry Point**: REST API for frontend to submit jobs and track progress
2. **Orchestrator**: Executes pipeline modules 3-8 in sequence with progress tracking
3. **Job Queue Manager**: BullMQ-based background processing with concurrency control
4. **Real-Time Updates**: SSE streaming for live progress updates
5. **Cost Guardian**: Enforces $2000/job budget limit with pre-flight checks
6. **Rate Limiter**: Prevents abuse (5 jobs/user/hour)

---

## Architecture Overview

```
Frontend → API Gateway (FastAPI)
    ↓
  [REST Endpoints] → Job Creation → BullMQ Queue
    ↓                                    ↓
  [SSE Stream] ← Progress Events ← [Worker Process]
    ↑                                    ↓
  [Redis Pub/Sub] ←──────────────────────┘
    ↓
  [Pipeline Orchestrator]
    ↓
  Modules 3-8 (Sequential)
```

**Components:**
- **FastAPI Application**: REST endpoints, middleware, SSE handler, Redis pub/sub subscriber
- **BullMQ Queue**: Background job processing (2 workers, 3 concurrent each)
- **Pipeline Orchestrator**: Executes modules sequentially with progress tracking
- **SSE Manager**: Manages multiple connections per job, broadcasts events via Redis pub/sub
- **Rate Limiter**: Redis-based sliding window with sorted set (5 jobs/hour/user)
- **Cost Tracker**: Real-time cost tracking with $2000 budget enforcement
- **Redis Pub/Sub**: Event distribution from workers to FastAPI SSE connections

---

## REST Endpoints

### `POST /api/v1/upload-audio`

**Purpose**: Upload audio file and create video generation job.

**Authentication**: Required (JWT token from Supabase Auth)

**Request**:
- `Content-Type`: `multipart/form-data`
- `audio_file`: File (MP3/WAV/FLAC, ≤10MB)
- `user_prompt`: string (50-500 characters)

**Validation**:
1. File size ≤10MB
2. MIME type: `audio/mpeg`, `audio/wav`, `audio/flac`
3. Prompt length: 50-500 characters
4. Rate limit check: ≤5 jobs/hour for user
5. Pre-flight cost check (mode-dependent):
   - **Production mode:** Target ~$200 per job, hard limit $2000 per job
   - **Development mode:** Target ~$2-5 per job, hard limit $50 per job
   - For very long videos (>10 minutes), consider warning or rejection

**Processing**:
1. Extract audio duration using `mutagen` library (quick metadata read, no full decode)
   - Example: `from mutagen import File; f = File(audio_file); duration = f.info.length`
2. Cost estimate (mode-dependent):
   - **Production:** ~$200 per job (hard limit $2000)
   - **Development:** ~$2-5 per job (hard limit $50)
   - Optional: Warn or reject if duration > 10 minutes
3. Validate rate limit (see Rate Limiting section)
4. Upload audio to Supabase Storage (`audio-uploads` bucket)
   - Path: `{user_id}/{job_id}/{original_filename}`
   - Use `shared.storage.upload_file()` helper
5. Create job record in database (`status: "queued"`)
   - Use `shared.database` client
   - Generate UUID for `job_id`
6. Enqueue job to BullMQ queue (see Job Queue section)
7. Return job_id

**Response** (201 Created):
```json
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_cost": 200.00,  // Production mode; dev mode: ~2-5
  "created_at": "2025-11-14T10:30:00Z"
}
```

**Errors**:
- `400`: Validation error (file size, prompt length, budget exceeded)
- `401`: Unauthorized (missing/invalid JWT)
- `429`: Rate limit exceeded
- `500`: Server error

---

### `GET /api/v1/jobs/{job_id}`

**Purpose**: Get job status (polling fallback, SSE preferred).

**Authentication**: Required (verify job ownership)

**Response** (200 OK):
```json
{
  "job_id": "uuid",
  "status": "processing",
  "current_stage": "video_generation",
  "progress": 85,
  "estimated_remaining": 120,
  "total_cost": 450.50,
  "video_url": null,
  "error_message": null,
  "created_at": "2025-11-14T10:30:00Z",
  "updated_at": "2025-11-14T10:35:00Z"
}
```

**Caching**: 
- Cache job status in Redis (30s TTL) to reduce database load
- Cache key: `job_status:{job_id}`
- Invalidate cache on status updates

**Errors**:
- `401`: Unauthorized
- `403`: Forbidden (job doesn't belong to user)
- `404`: Job not found
- `500`: Server error

---

### `GET /api/v1/jobs`

**Purpose**: List user's jobs with pagination and filtering.

**Authentication**: Required

**Query Parameters**:
- `status`: Filter by status (`queued`, `processing`, `completed`, `failed`)
- `limit`: Number of results (default: 10, max: 50)
- `offset`: Pagination offset (default: 0)

**Response** (200 OK):
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "status": "completed",
      "progress": 100,
      "total_cost": 180.75,
      "created_at": "2025-11-14T10:30:00Z",
      "completed_at": "2025-11-14T10:40:00Z"
    }
  ],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

**Errors**:
- `401`: Unauthorized
- `400`: Invalid query parameters

---

### `POST /api/v1/jobs/{job_id}/cancel`

**Purpose**: Cancel a queued or processing job.

**Authentication**: Required (verify job ownership)

**Processing**:
1. Verify job ownership
2. Check job status: Only allow cancellation if `queued` or `processing`
3. **If queued**: 
   - Remove job from BullMQ queue using `queue.remove(job_id)`
   - Mark job as `failed` in database
   - Set `error_message = "Job cancelled by user"`
4. **If processing**:
   - Set cancellation flag in Redis: `job_cancel:{job_id} = "1"` (TTL: 15min)
   - Worker checks this flag before each module execution
   - If flag exists, worker stops gracefully and marks job as `failed`
   - Mark job as `failed` in database immediately
   - Set `error_message = "Job cancelled by user"`
5. Cleanup: Delete intermediate files (reference images, video clips), keep audio file for 7 days

**Response** (200 OK):
```json
{
  "job_id": "uuid",
  "status": "failed",
  "message": "Job cancelled by user"
}
```

**Errors**:
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Job not found
- `400`: Job already completed or failed (cannot cancel)

---

### `GET /api/v1/health`

**Purpose**: Health check endpoint for monitoring and load balancers.

**Authentication**: Not required

**Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2025-11-14T10:35:00Z",
  "queue": {
    "size": 5,
    "active_jobs": 3,
    "workers": 2
  },
  "database": "connected",
  "redis": "connected"
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "timestamp": "2025-11-14T10:35:00Z",
  "issues": ["database connection failed", "redis connection failed"]
}
```

**Implementation**:
- Check database connection (ping query)
- Check Redis connection (ping command)
- Check queue status (BullMQ queue size)
- Return 503 if any critical service is down

---

### `GET /api/v1/jobs/{job_id}/stream`

**Purpose**: SSE stream for real-time progress updates.

**Authentication**: Required (verify job ownership)

**Response**: `text/event-stream`

**Event Types**:
```javascript
// Heartbeat (every 30s to detect dead connections)
event: heartbeat
data: {"timestamp": "2025-11-14T10:35:00Z"}

// Stage update
event: stage_update
data: {"stage": "audio_parser", "status": "completed", "duration": 45.2}

// Progress update
event: progress
data: {"progress": 30, "estimated_remaining": 300}

// Status message
event: message
data: {"text": "Generating reference images...", "stage": "reference_generator"}

// Cost update
event: cost_update
data: {"stage": "video_generation", "cost": 60.00, "total": 120.50}

// Completion
event: completed
data: {"video_url": "https://...", "total_cost": 180.75}

// Error
event: error
data: {"error": "Budget limit exceeded", "code": "BUDGET_EXCEEDED", "retryable": false}
```

**Connection Management**:
- Support multiple connections per job (multiple browser tabs)
- Store connections: `Dict[job_id, List[SSEConnection]]`
- Maximum 10 connections per job (prevent resource exhaustion)
- Broadcast events to all connections for job_id via Redis pub/sub
- **Heartbeat**: Send `heartbeat` event every 30s to detect dead connections
- **Initial State**: On connection, immediately send current job state (progress, stage, cost)
- **Cleanup**: Remove connection on disconnect, timeout after job completes + 30s
- **Reconnection**: Frontend auto-reconnects on disconnect, receives current state immediately

**SSE Event Distribution**:
- Worker process publishes events to Redis channel: `job_events:{job_id}`
- **Event Message Format** (JSON string):
  ```json
  {
    "event_type": "progress|stage_update|message|cost_update|completed|error",
    "data": {
      "progress": 30,
      "estimated_remaining": 300,
      "stage": "audio_parser",
      "status": "completed",
      "duration": 45.2,
      "cost": 60.00,
      "total": 120.50,
      "error": "Error message",
      "code": "ERROR_CODE",
      "retryable": false
    }
  }
  ```
- FastAPI SSE manager subscribes to Redis channel for active job connections
- Parse JSON message, extract `event_type` and `data`
- Format as SSE: `event: {event_type}\ndata: {json.dumps(data)}\n\n`
- Broadcast to all SSE connections for that job_id
- If no active connections, events are discarded (no persistence needed)

**Connection Health**:
- Detect dead connections: If heartbeat fails to send, remove connection
- Client-side: Frontend auto-reconnects with exponential backoff (2s, 4s, 8s)
- Server-side: Remove stale connections after 60s of no heartbeat response

**Errors**:
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Job not found
- `503`: Too many connections (if >10 per job)

---

### `GET /api/v1/jobs/{job_id}/download`

**Purpose**: Download final video file via signed URL.

**Authentication**: Required (verify job ownership)

**Processing**:
1. Verify job status is "completed"
2. Generate signed URL from Supabase Storage (1 hour expiration)
3. Return signed URL in JSON response

**Response** (200 OK):
```json
{
  "download_url": "https://storage.supabase.co/...?token=...",
  "expires_in": 3600,
  "filename": "music_video_{job_id}.mp4"
}
```

**Implementation**: 
- Use Supabase Storage `create_signed_url()` with 1 hour expiration
- Frontend handles download (better performance, direct CDN access)
- Signed URL provides secure, time-limited access

**Errors**:
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Job not found or not completed
- `410`: Video expired/deleted

---

## Authentication & Authorization

**Strategy**: Supabase Auth Direct Integration

**Implementation**:
- Frontend uses Supabase Auth SDK (`@supabase/supabase-js`)
- Frontend sends JWT token in `Authorization: Bearer <token>` header
- API Gateway validates JWT using Supabase's JWT secret
- Extract `user_id` from JWT claims for job ownership

**Protected Endpoints**:
- All endpoints except `/api/v1/health` require authentication
- Job endpoints verify ownership: `job.user_id == jwt.user_id`

**No Auth Endpoints in Gateway**:
- Frontend handles login/register via Supabase Auth SDK (`@supabase/supabase-js`)
- Gateway only validates JWT tokens (no `/auth/login`, `/auth/register`, `/auth/reset-password`)
- Frontend obtains JWT token from Supabase Auth, sends in `Authorization: Bearer <token>` header

**JWT Validation**:
- Validate token signature using Supabase JWT secret from `shared.config.SUPABASE_JWT_SECRET`
- Check token expiration
- Extract `user_id` from token claims (`sub` field in JWT payload)
- Cache valid tokens in Redis (5min TTL) to reduce validation overhead
- Cache key: `jwt_valid:{token_hash}` (hash of token for key)
- **Implementation**: Use `jose` library or `pyjwt` for JWT validation

---

## Pipeline Orchestrator

**Purpose**: Execute modules 3-8 sequentially with progress tracking and error handling.

**Module Execution Order**:
```python
1. Audio Parser (10% progress)
   Input: job_id, audio_url
   Output: AudioAnalysis (beats, lyrics, structure, mood)
   
2. Scene Planner (20% progress)
   Input: job_id, user_prompt, audio_data
   Output: ScenePlan (characters, scenes, clip_scripts, transitions)
   
3. Reference Generator (30% progress)
   Input: job_id, plan
   Output: ReferenceImages (scene_references, character_references)
   
4. Prompt Generator (40% progress)
   Input: job_id, plan, references
   Output: ClipPrompts (optimized prompts with reference URLs)
   
5. Video Generator (85% progress)
   Input: job_id, clip_prompts
   Output: Clips (video files, parallel: 5 concurrent)
   
6. Composer (100% progress)
   Input: job_id, clips, audio_url, transitions (from ScenePlan), beat_timestamps (from AudioAnalysis)
   Output: VideoOutput (final video)
   Note: Orchestrator extracts `transitions` from `ScenePlan.transitions` and `beat_timestamps` from `AudioAnalysis.beat_timestamps`
```

**Progress Tracking**:
- Fixed percentages (not time-weighted): 10%, 20%, 30%, 40%, 85%, 100%
- Update `jobs.progress` field after each stage
- Send `progress` event via SSE

**Module Communication**:
- Direct Python function calls (modules imported as packages)
- Each module exports: `async def process(job_id, input_data) -> output_model`
- **Import Paths** (exact structure):
  ```python
  from modules.audio_parser.process import process as parse_audio
  from modules.scene_planner.process import process as plan_scene
  from modules.reference_generator.process import process as generate_references
  from modules.prompt_generator.process import process as generate_prompts
  from modules.video_generator.process import process as generate_videos
  from modules.composer.process import process as compose_video
  ```
- **Model Imports**: All models available from `shared.models`:
  ```python
  from shared.models import AudioAnalysis, ScenePlan, ReferenceImages, ClipPrompts, Clips, VideoOutput
  ```
- **Error Handling**: Modules raise exceptions from `shared.errors`:
  - `RetryableError` - Transient failures (will be retried)
  - `PipelineError` - Non-retryable failures
  - `BudgetExceededError` - Cost limit exceeded

**Cost Tracking**:
- Track costs per API call using `shared.cost_tracking`
- Check budget before expensive operations (Video Generator, Reference Generator)
- Enforce $2000 limit: `cost_tracker.enforce_budget_limit(job_id, limit=2000.00)`
- Abort immediately if budget exceeded (raise `BudgetExceededError`)

**Error Recovery** (Selective):
- **Critical failures (fail immediately)**:
  - Audio Parser fails → Can't proceed, fail job
  - Video Generator produces <3 clips → Minimum not met, fail job
  - Composer fails → Can't produce final video, fail job
- **Non-critical failures (continue with fallback)**:
  - Reference Generator fails → Use text-only prompts (fallback)
  - One clip fails in Video Generator → Accept if ≥3 clips total
  - Scene Planner fails → Use simple scene descriptions (fallback)

**Fallback State Communication**:
- Store fallback flags in `job_stages` table: `fallback_mode: bool`, `fallback_reason: str` (in `metadata` JSONB field)
- **Orchestrator Logic**:
  ```python
  # After Reference Generator stage
  if reference_generator_failed:
      await db.update_job_stage(job_id, "reference_generator", {
          "fallback_mode": True,
          "fallback_reason": "Image generation failed, using text-only mode"
      })
  
  # Before Prompt Generator
  prev_stage = await db.get_job_stage(job_id, "reference_generator")
  use_fallback = prev_stage.get("metadata", {}).get("fallback_mode", False)
  ```
- **Module Implementation**: Modules check `job_stages` table via `shared.database`:
  ```python
  # In Prompt Generator
  ref_stage = await db.query("SELECT metadata FROM job_stages WHERE job_id = ? AND stage_name = 'reference_generator'")
  fallback_mode = ref_stage.get("metadata", {}).get("fallback_mode", False)
  if fallback_mode:
      # Use text-only prompts (no reference image URLs)
  ```
- Example: If Reference Generator fails, orchestrator sets `fallback_mode=true` in `job_stages.metadata`, Prompt Generator reads this and uses text-only prompts

**Database Transaction Handling**:
- Use database transactions for critical updates (job status, progress)
- Retry transient database errors (connection pool exhaustion, timeouts)
- Idempotent operations where possible (e.g., progress updates can be safely retried)
- Transaction timeout: 5 seconds per operation

---

## Job Queue (BullMQ)

**Configuration**:
- Queue name: `video_generation`
- Workers: 2 (separate processes/containers)
- Concurrency: 3 jobs per worker (6 total system-wide)
- Timeout: 15 minutes per job
- Retry: 3 attempts with exponential backoff (2s, 4s, 8s)

**Job Data Structure**:
```json
{
  "job_id": "uuid",
  "user_id": "uuid",
  "audio_url": "https://storage.supabase.co/...",
  "user_prompt": "Create a cyberpunk music video...",
  "created_at": "2025-11-14T10:30:00Z"
}
```

**Worker Process**:
- Separate process/container from FastAPI app
- Connects to same Redis instance
- Processes jobs from queue (max 3 concurrent per worker)
- Calls orchestrator to execute pipeline
- Updates job status in database
- **SSE Event Distribution**: Publishes events to Redis pub/sub channel `job_events:{job_id}`
- FastAPI SSE manager subscribes to Redis channels and broadcasts to connections

**Concurrency Enforcement**:
- BullMQ worker configured with `concurrency: 3` (3 jobs per worker)
- BullMQ handles job locking automatically (prevents duplicate processing)
- If worker crashes: BullMQ automatically retries job (up to 3 attempts)
- Worker health: Monitor worker heartbeat (every 30s), restart if no heartbeat for 2 minutes

**Monitoring**:
- Bull Board UI at `/admin/queues` (development only, requires authentication)
- Monitor: active jobs, failed jobs, processing time, queue size
- Metrics: Success rate, average processing time, cost per job

---

## Rate Limiting

**Strategy**: Redis-based sliding window with sorted set

**Limit**: 5 jobs per user per hour

**Implementation**:
- Use Redis sorted set: Key `rate_limit:{user_id}`, score = timestamp (Unix epoch)
- On job creation: Add current timestamp to sorted set
- Remove entries older than 1 hour: `ZREMRANGEBYSCORE rate_limit:{user_id} 0 {current_time - 3600}`
- Count entries in last hour: `ZCARD rate_limit:{user_id}`
- If count ≥ 5: Return `429 Too Many Requests` with `Retry-After` header
- Timezone: All timestamps in UTC to avoid timezone issues
- Edge case handling: Hour boundaries handled correctly (sliding window, not fixed hour)

**Response** (429 Too Many Requests):
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 3600,
  "limit": 5,
  "window": "1 hour"
}
```

**Retry-After Header**:
- Calculate seconds until oldest entry expires
- Example: If oldest entry is 30 minutes old, `Retry-After: 1800`

---

## Cost Tracking & Budget Enforcement

**Mode Configuration**:
- **Production Mode:** `ENVIRONMENT=production` (or `ENVIRONMENT=staging`)
  - Target cost: ~$200 per job (regardless of video length)
  - Hard limit: $2000 per job (safety cap)
- **Development Mode:** `ENVIRONMENT=development`
  - Target cost: ~$2-5 per job (using cheaper models)
  - Hard limit: $50 per job (safety cap)

**Pre-Flight Check**:
- Check `ENVIRONMENT` variable to determine mode
- Production: Target ~$200, hard limit $2000
- Development: Target ~$2-5, hard limit $50
- Optional: Warn or reject if duration > 10 minutes (very long songs)

**Real-Time Tracking**:
- Track costs per API call: `cost_tracker.track_cost(job_id, stage, api_name, cost)`
- Update `jobs.total_cost` field
- Check budget before expensive operations:
  ```python
  # Mode-dependent limit
  limit = 2000.00 if ENVIRONMENT == "production" else 50.00
  can_proceed = await cost_tracker.check_budget(job_id, new_cost=100.00, limit=limit)
  if not can_proceed:
      raise BudgetExceededError("Would exceed budget")
  ```

**Budget Enforcement**:
- Enforce before Video Generator (most expensive)
- Enforce before Reference Generator
- Abort immediately if exceeded (mode-dependent):
  - Production: `cost_tracker.enforce_budget_limit(job_id, limit=2000.00)`
  - Development: `cost_tracker.enforce_budget_limit(job_id, limit=50.00)`
- Send `error` event via SSE: `{"error": "Budget limit exceeded", "code": "BUDGET_EXCEEDED", "retryable": false}`

**Cost Accuracy**: 
- Production: ±$10 tolerance acceptable
- Development: ±$0.50 tolerance acceptable

---

## Error Handling

**Error Types**:
- `ValidationError` (400): Invalid input (file size, prompt length)
- `BudgetExceededError` (402): Cost limit exceeded
- `RateLimitError` (429): Too many requests
- `RetryableError` (500): Transient failure (can retry)
- `PipelineError` (500): Module failure (non-retryable)

**Error Response Format**:
```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "retryable": true/false,
  "job_id": "uuid"
}
```

**SSE Error Events**:
- Send `error` event via SSE with error details
- Include `retryable` flag for frontend to show retry button
- Mark job as `failed` in database

**Error Codes**:
- `VALIDATION_ERROR`: Input validation failed
- `BUDGET_EXCEEDED`: Cost limit exceeded
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `GENERATION_ERROR`: AI generation failed
- `TIMEOUT`: Job exceeded 15-minute timeout
- `MODULE_FAILURE`: Pipeline module failed

---

## Database Operations

**Schema Reference**: Complete database schema is documented in `planning/high-level/Tech.md`. This section covers only the operations required by the API Gateway.

**Required Tables** (see Tech.md for full schema):
- `jobs` - Job tracking and status
- `job_stages` - Stage progress and fallback flags
- `job_costs` - Cost tracking per API call

**Key Operations**:
1. **Job Creation**: Insert new job record with `status='queued'`
2. **Status Updates**: Update `status`, `current_stage`, `progress` fields
3. **Progress Tracking**: Update `progress` (0-100%) after each stage completion
4. **Cost Tracking**: Insert into `job_costs` table via `shared.cost_tracking`
5. **Fallback Flags**: Store `fallback_mode` and `fallback_reason` in `job_stages.metadata`
6. **Completion**: Update `video_url`, `total_cost`, `completed_at` on success
7. **Failure**: Update `error_message`, `status='failed'` on error
8. **Job Retrieval**: Query by `job_id` with ownership verification (`user_id`)

**Note**: Database schema is managed separately. API Gateway assumes schema exists and is accessible via `shared.database` client.

**Storage Path Examples**:
- Audio upload: `audio-uploads/550e8400-e29b-41d4-a716-446655440000/123e4567-e89b-12d3-a456-426614174000/song.mp3`
- Reference image: `reference-images/123e4567-e89b-12d3-a456-426614174000/scene_city_street.png`
- Video clip: `video-clips/123e4567-e89b-12d3-a456-426614174000/clip_0.mp4`
- Final video: `video-outputs/123e4567-e89b-12d3-a456-426614174000/final_video.mp4`

---

## Job Cleanup Strategy

**Immediate Cleanup** (after job status becomes final):
- **On successful completion**:
  - Delete reference images (`reference-images` bucket) immediately
  - Delete video clips (`video-clips` bucket) immediately
  - Keep final video (`video-outputs` bucket) for 14 days
- **On failure**:
  - Keep all intermediate files for 7 days (for debugging)
  - Keep audio file for 7 days
  - After 7 days: Delete all files (scheduled cleanup)

**Scheduled Cleanup** (daily cron job):
- Delete final videos older than 14 days from `video-outputs` bucket
- Delete failed job intermediate files older than 7 days
- Delete audio files from failed jobs older than 7 days
- Cleanup orphaned files (no associated job record)

**Implementation**:
- Use Supabase Storage API: `storage.delete_file(bucket, path)`
- Scheduled job: Separate worker process or Railway cron job
- Track cleanup in database: `job_cleanup_log` table (optional, for auditing)
- Error handling: Log cleanup failures, retry next day

---

## Module Integration

**Module Interfaces** (to be implemented by modules):

```python
# Module 3: Audio Parser
async def process(job_id: UUID, audio_url: str) -> AudioAnalysis:
    """Extract beats, lyrics, structure, mood from audio."""
    pass

# Module 4: Scene Planner
async def process(job_id: UUID, user_prompt: str, audio_data: AudioAnalysis) -> ScenePlan:
    """Generate video plan with characters, scenes, clip scripts."""
    pass

# Module 5: Reference Generator
async def process(job_id: UUID, plan: ScenePlan) -> ReferenceImages:
    """Generate reference images for scenes and characters."""
    pass

# Module 6: Prompt Generator
async def process(job_id: UUID, plan: ScenePlan, references: ReferenceImages) -> ClipPrompts:
    """Optimize prompts for video generation."""
    pass

# Module 7: Video Generator
async def process(job_id: UUID, clip_prompts: ClipPrompts) -> Clips:
    """Generate video clips in parallel (5 concurrent)."""
    pass

# Module 8: Composer
async def process(job_id: UUID, clips: Clips, audio_url: str, 
                  transitions: List[Transition], beats: List[float]) -> VideoOutput:
    """Stitch clips with audio and transitions."""
    pass
```

**Orchestrator Implementation**:
```python
async def execute_pipeline(job_id: UUID, audio_url: str, user_prompt: str):
    try:
        # Stage 1: Audio Parser (10%)
        await publish_event(job_id, "stage_update", {"stage": "audio_parser", "status": "started"})
        audio_data = await parse_audio(job_id, audio_url)
        await update_progress(job_id, 10, "audio_parser")
        await publish_event(job_id, "stage_update", {"stage": "audio_parser", "status": "completed"})
        
        # Stage 2: Scene Planner (20%)
        await publish_event(job_id, "stage_update", {"stage": "scene_planner", "status": "started"})
        plan = await plan_scene(job_id, user_prompt, audio_data)
        await update_progress(job_id, 20, "scene_planner")
        await publish_event(job_id, "stage_update", {"stage": "scene_planner", "status": "completed"})
        
        # Stage 3: Reference Generator (30%)
        await publish_event(job_id, "stage_update", {"stage": "reference_generator", "status": "started"})
        try:
            references = await generate_references(job_id, plan)
            await update_progress(job_id, 30, "reference_generator")
        except Exception as e:
            # Set fallback flag
            await db.update_job_stage(job_id, "reference_generator", {
                "fallback_mode": True,
                "fallback_reason": str(e)
            })
            references = None  # Prompt Generator will handle None
        await publish_event(job_id, "stage_update", {"stage": "reference_generator", "status": "completed"})
        
        # Stage 4: Prompt Generator (40%)
        await publish_event(job_id, "stage_update", {"stage": "prompt_generator", "status": "started"})
        clip_prompts = await generate_prompts(job_id, plan, references)
        await update_progress(job_id, 40, "prompt_generator")
        await publish_event(job_id, "stage_update", {"stage": "prompt_generator", "status": "completed"})
        
        # Stage 5: Video Generator (85%)
        await publish_event(job_id, "stage_update", {"stage": "video_generator", "status": "started"})
        clips = await generate_videos(job_id, clip_prompts)
        if len(clips.clips) < 3:
            raise PipelineError("Insufficient clips generated")
        await update_progress(job_id, 85, "video_generator")
        await publish_event(job_id, "stage_update", {"stage": "video_generator", "status": "completed"})
        
        # Stage 6: Composer (100%)
        await publish_event(job_id, "stage_update", {"stage": "composer", "status": "started"})
        video_output = await compose_video(
            job_id, 
            clips, 
            audio_url, 
            plan.transitions,  # From ScenePlan
            audio_data.beat_timestamps  # From AudioAnalysis
        )
        await update_progress(job_id, 100, "composer")
        await publish_event(job_id, "completed", {"video_url": video_output.video_url, "total_cost": job.total_cost})
        
    except Exception as e:
        await handle_pipeline_error(job_id, e)
```

**Helper Functions**:
- `publish_event(job_id, event_type, data)`: Publishes to Redis pub/sub channel
- `update_progress(job_id, progress, stage_name)`: Updates database and publishes progress event
- `handle_pipeline_error(job_id, error)`: Marks job as failed, publishes error event

---

## Success Criteria

### Functional
✅ Jobs created and enqueued successfully  
✅ SSE delivers real-time updates (<1s latency)  
✅ Background processing works (BullMQ queue)  
✅ Pipeline executes modules sequentially  
✅ Progress updates accurate (10%, 20%, 30%, 40%, 85%, 100%)  
✅ Video download works (signed URL)  
✅ Multiple SSE connections per job supported

### Performance
✅ Upload endpoint responds in <2s  
✅ SSE events delivered <1s after stage completion  
✅ Queue processing handles 6 concurrent jobs  
✅ Rate limiting prevents abuse (5 jobs/hour/user)

### Cost & Budget
✅ Pre-flight cost check validates job (production: $200/job target, $2000/job hard limit; dev: $5/job target, $50/job hard limit)  
✅ Real-time cost tracking accurate (±$10 production, ±$0.50 dev)  
✅ Budget limit enforced (mode-dependent: production >$2000, dev >$50)  
✅ Cost updates sent via SSE

### Reliability
✅ Errors handled gracefully with clear messages  
✅ Failed jobs marked correctly in database  
✅ Partial success handling works (≥3 clips)  
✅ Connection cleanup works (SSE, storage)
✅ SSE reconnection works (frontend auto-reconnects)
✅ Heartbeat mechanism detects dead connections
✅ Database transactions prevent inconsistent state
✅ Worker health monitoring and auto-restart

### Security
✅ JWT validation works correctly  
✅ Job ownership verified on all endpoints  
✅ Rate limiting prevents abuse  
✅ Signed URLs expire correctly (1 hour)
✅ CORS configured correctly
✅ Request ID tracking for security auditing

---

## Implementation Notes

**File Structure**:
```
api_gateway/
├── main.py              # FastAPI app, routes, middleware, CORS
├── worker.py            # BullMQ worker process
├── orchestrator.py     # Pipeline orchestration
├── routes/
│   ├── jobs.py          # Job endpoints (GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel)
│   ├── upload.py        # Upload endpoint (POST /upload-audio)
│   ├── stream.py        # SSE handler (GET /jobs/{id}/stream)
│   ├── download.py      # Download endpoint (GET /jobs/{id}/download)
│   └── health.py        # Health check (GET /health)
├── services/
│   ├── queue_service.py # BullMQ queue management
│   ├── rate_limiter.py  # Rate limiting logic (Redis sorted set)
│   ├── sse_manager.py   # SSE connection management + Redis pub/sub subscriber
│   └── event_publisher.py # Redis pub/sub event publisher (used by worker)
└── dependencies.py      # FastAPI dependencies (auth, request ID)
```

**Dependencies**:
- `fastapi` >= 0.104.0
- `bullmq-py` >= 0.1.0 (Python client for BullMQ, requires Redis)
- `mutagen` >= 1.47.0 (for quick audio duration extraction)
- `shared` (all components available from `project/backend/shared/`)

**Environment Variables**:
- All from `shared.config` (Supabase, Redis, OpenAI, Replicate)
- Additional required:
  - `FRONTEND_URL`: Frontend domain for CORS (e.g., `https://app.example.com`)
  - `SUPABASE_JWT_SECRET`: JWT secret for token validation (from Supabase dashboard)

**CORS Configuration**:
- Allow origin: Frontend domain (from environment variable `FRONTEND_URL`)
- Allow methods: `GET`, `POST`, `OPTIONS`
- Allow headers: `Authorization`, `Content-Type`
- Credentials: `true` (for JWT cookies if needed)
- Max age: 3600 seconds

**Request ID Tracking**:
- Generate unique `X-Request-ID` header for each request
- Include in logs for request tracing
- Return in response headers for debugging
- Format: UUID v4

**Timeout Specifications**:
- **SSE Connection**: 30s heartbeat interval, 60s stale connection timeout
- **Job Processing**: 15 minutes per job (enforced by BullMQ)
- **Database Queries**: 5 seconds per query
- **Redis Operations**: 2 seconds per operation
- **HTTP Request**: 30 seconds (FastAPI default)
- **File Upload**: 60 seconds (for 10MB audio file)

---

---

## Critical Implementation Details

**Quick Reference for Developers**:

1. **BullMQ Python Package**: Use `bullmq-py` (not `bullmq`). Install: `pip install bullmq-py`
2. **Audio Duration**: Use `mutagen.File(audio_file).info.length` for quick metadata read
3. **JWT Validation**: Use `pyjwt` or `python-jose` with `SUPABASE_JWT_SECRET` from config
4. **Module Imports**: All modules export `process` function from `modules.{module_name}.process`
5. **Models**: Import from `shared.models` (already implemented)
6. **Storage Paths**: Follow pattern `{bucket}/{user_id or job_id}/{filename}`
7. **Redis Pub/Sub**: Channel format `job_events:{job_id}`, message is JSON string
8. **Job Cancellation**: Set Redis key `job_cancel:{job_id} = "1"`, worker checks before each stage
9. **Fallback Mode**: Store in `job_stages.metadata` JSONB field, modules query before execution
10. **Composer Inputs**: Extract `transitions` from `ScenePlan.transitions`, `beats` from `AudioAnalysis.beat_timestamps`

**Common Pitfalls to Avoid**:
- ❌ Don't use `bullmq` package (Node.js only), use `bullmq-py`
- ❌ Don't decode full audio file for duration (use `mutagen` metadata)
- ❌ Don't forget to check cancellation flag in worker before each module
- ❌ Don't forget to set fallback flags in `job_stages.metadata` (not top-level)
- ❌ Don't publish SSE events directly from modules (use orchestrator's `publish_event`)

---

**Document Status:** Ready for Implementation  
**Version:** 1.2 (Added critical implementation details and clarifications)  
**Next Action:** Begin implementation with FastAPI app structure, BullMQ setup, and Redis pub/sub integration

