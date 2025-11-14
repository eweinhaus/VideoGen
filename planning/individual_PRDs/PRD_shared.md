# Shared Components - Product Requirements Document

**Version:** 1.0 | **Date:** November 14, 2025  
**Priority:** CRITICAL - Must be built first before any module development

---

## Executive Summary

The shared components module provides foundational infrastructure, data models, and utilities required by all 8 pipeline modules. This module defines the "contract" between modules through standardized data structures, common services (database, storage, caching), and shared utilities (retry logic, cost tracking, error handling).

**Timeline:** 7-8 hours (Day 1 Morning)  
**Dependencies:** None (foundation layer)  
**Blocks:** All other modules (must complete first)

---

## Purpose

Enable parallel module development by providing:
1. **Standardized Interfaces**: Pydantic models that define data structures passed between modules
2. **Common Services**: Database, Redis, and storage clients used across all modules
3. **Shared Utilities**: Retry logic, cost tracking, error handling, logging
4. **Configuration Management**: Centralized environment variable handling

---

## Component Specifications

### 1. Configuration (`config.py`)

**Purpose**: Centralized environment variable management and validation.

**Requirements**:
- Load environment variables from `.env` file
- Validate required variables are present at startup
- Provide type-safe access to configuration values
- Support development, staging, and production environments

**Environment Variables**:
```python
SUPABASE_URL: str                    # Supabase project URL
SUPABASE_SERVICE_KEY: str            # Service role key (full access)
SUPABASE_ANON_KEY: str               # Anon key (for frontend)
REDIS_URL: str                       # Redis connection string
OPENAI_API_KEY: str                  # OpenAI API key
REPLICATE_API_TOKEN: str             # Replicate API token
JWT_SECRET_KEY: str                  # JWT signing secret
ENVIRONMENT: str                     # "development" | "staging" | "production"
LOG_LEVEL: str                       # "DEBUG" | "INFO" | "WARNING" | "ERROR"
```

**API**:
```python
from shared.config import settings

settings.supabase_url
settings.redis_url
settings.openai_api_key
# etc.
```

**Validation**:
- Raise `ConfigError` if required variables missing
- Validate URL formats (Supabase, Redis)
- Validate API key formats (basic checks)

**Success Criteria**:
✅ All required env vars validated at import  
✅ Type-safe access to all settings  
✅ Clear error messages for missing/invalid config  
✅ Works in all environments

---

### 2. Database Client (`database.py`)

**Purpose**: Supabase PostgreSQL client with connection pooling and query utilities.

**Requirements**:
- Connection pool management (max 10 connections)
- Async query support
- Transaction helpers
- Connection health checks
- Automatic reconnection on failure

**Implementation**: Uses Supabase Python client (`supabase-py` >= 2.0) which provides async support and connection pooling. The client wraps Supabase's REST API and PostgREST query builder.

**API**:
```python
from shared.database import db

# Query using Supabase client (recommended)
result = await db.table("jobs").select("*").eq("id", job_id).execute()

# Insert
await db.table("jobs").insert({
    "id": job_id,
    "user_id": user_id,
    "status": "queued",
    "audio_url": audio_url,
    "user_prompt": prompt
}).execute()

# Transaction (using Supabase RPC or multiple operations)
# Note: Supabase uses PostgREST which doesn't support traditional transactions
# Use RPC functions for atomic operations or handle at application level
async with db.transaction():
    await db.table("jobs").insert(...).execute()
    await db.table("job_stages").insert(...).execute()

# Health check
is_healthy = await db.health_check()
```

**Features**:
- Connection pooling (handled by Supabase client)
- Query builder API (type-safe, prevents SQL injection)
- Transaction support via RPC functions or application-level handling
- Connection retry logic (3 attempts, exponential backoff)
- Direct access to Supabase client for advanced queries

**Success Criteria**:
✅ Connection pool works correctly  
✅ Queries execute successfully  
✅ Transactions rollback on error  
✅ Health check returns accurate status  
✅ Handles connection failures gracefully

---

### 3. Redis Client (`redis_client.py`)

**Purpose**: Redis connection and caching utilities.

**Requirements**:
- Connection pool management
- Get/set/delete operations
- TTL management
- JSON serialization/deserialization
- Connection health checks

**Implementation**: Uses `redis` (redis-py) >= 5.0 with async support via `asyncio`. The library provides native async/await support.

**API**:
```python
from shared.redis_client import redis

# String operations
await redis.set("key", "value", ex=3600)  # ex = expiration in seconds
value = await redis.get("key")

# JSON operations
await redis.set_json("key", {"data": "value"}, ttl=3600)
data = await redis.get_json("key")

# Delete
await redis.delete("key")

# Health check
is_healthy = await redis.health_check()
```

**Features**:
- Connection pooling (handled by redis-py async client)
- Automatic JSON serialization (using `json.dumps`/`json.loads`)
- TTL support (expires after specified seconds)
- Key prefixing (namespace: `videogen:cache:{key}`)
- Async-compatible (uses `asyncio` for non-blocking operations)

**Success Criteria**:
✅ Get/set/delete operations work  
✅ TTL expiration works correctly  
✅ JSON serialization handles complex objects  
✅ Health check returns accurate status  
✅ Handles connection failures gracefully

---

### 4. Data Models (`models/`)

**Purpose**: Pydantic models that define data structures passed between modules.

**Structure**:
```
models/
├── __init__.py          # Export all models
├── job.py               # Job, JobStage, JobCost
├── audio.py             # AudioAnalysis and related
├── scene.py             # ScenePlan, Character, Scene, ReferenceImages
└── video.py             # ClipPrompts, Clips, VideoOutput
```

#### 4.1 Job Models (`models/job.py`)

**Models**:
```python
class Job(BaseModel):
    id: UUID
    user_id: UUID
    status: Literal["queued", "processing", "completed", "failed"]
    audio_url: str
    user_prompt: str
    current_stage: Optional[str]
    progress: int = 0  # 0-100
    estimated_remaining: Optional[int]  # seconds
    total_cost: Decimal = Decimal("0.00")
    video_url: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

class JobStage(BaseModel):
    id: UUID
    job_id: UUID
    stage_name: str
    status: Literal["pending", "processing", "completed", "failed"]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    cost: Decimal
    metadata: Optional[dict]  # JSONB

class JobCost(BaseModel):
    id: UUID
    job_id: UUID
    stage_name: str
    api_name: str  # "whisper", "gpt-4o", "sdxl", "svd"
    cost: Decimal
    timestamp: datetime
```

#### 4.2 Audio Models (`models/audio.py`)

**Models**:
```python
class SongStructure(BaseModel):
    type: Literal["intro", "verse", "chorus", "bridge", "outro"]
    start: float  # seconds
    end: float
    energy: Literal["low", "medium", "high"]

class Lyric(BaseModel):
    text: str
    timestamp: float  # seconds

class Mood(BaseModel):
    primary: str  # "energetic", "calm", "dark", "bright"
    secondary: Optional[str]
    energy_level: Literal["low", "medium", "high"]
    confidence: float  # 0.0-1.0

class ClipBoundary(BaseModel):
    start: float
    end: float
    duration: float

class AudioAnalysis(BaseModel):
    job_id: UUID
    bpm: float
    duration: float
    beat_timestamps: List[float]
    song_structure: List[SongStructure]
    lyrics: List[Lyric]
    mood: Mood
    clip_boundaries: List[ClipBoundary]
    metadata: dict  # processing_time, cache_hit, confidence, etc.
```

#### 4.3 Scene Models (`models/scene.py`)

**Models**:
```python
class Character(BaseModel):
    id: str
    description: str
    role: str  # "main character", "background", etc.

class Scene(BaseModel):
    id: str
    description: str
    time_of_day: Optional[str]

class Style(BaseModel):
    color_palette: List[str]  # hex colors
    visual_style: str
    mood: str
    lighting: str
    cinematography: str

class ClipScript(BaseModel):
    clip_index: int
    start: float
    end: float
    visual_description: str
    motion: str
    camera_angle: str
    characters: List[str]  # character IDs
    scenes: List[str]  # scene IDs
    lyrics_context: Optional[str]
    beat_intensity: Literal["low", "medium", "high"]

class Transition(BaseModel):
    from_clip: int
    to_clip: int
    type: Literal["cut", "crossfade", "fade"]
    duration: float  # seconds
    rationale: str

class ScenePlan(BaseModel):
    job_id: UUID
    video_summary: str
    characters: List[Character]
    scenes: List[Scene]
    style: Style
    clip_scripts: List[ClipScript]
    transitions: List[Transition]

class ReferenceImage(BaseModel):
    scene_id: Optional[str]  # None if character reference
    character_id: Optional[str]  # None if scene reference
    image_url: str
    prompt_used: str
    generation_time: float
    cost: Decimal

class ReferenceImages(BaseModel):
    job_id: UUID
    scene_references: List[ReferenceImage]
    character_references: List[ReferenceImage]
    total_references: int
    total_generation_time: float
    total_cost: Decimal
    status: Literal["success", "partial", "failed"]
    metadata: dict
```

#### 4.4 Video Models (`models/video.py`)

**Models**:
```python
class ClipPrompt(BaseModel):
    clip_index: int
    prompt: str
    negative_prompt: str
    duration: float
    scene_reference_url: Optional[str]
    character_reference_urls: List[str]
    metadata: dict  # word_count, style_keywords, etc.

class ClipPrompts(BaseModel):
    job_id: UUID
    clip_prompts: List[ClipPrompt]
    total_clips: int
    generation_time: float

class Clip(BaseModel):
    clip_index: int
    video_url: str
    actual_duration: float
    target_duration: float
    duration_diff: float
    status: Literal["success", "failed"]
    cost: Decimal
    retry_count: int
    generation_time: float

class Clips(BaseModel):
    job_id: UUID
    clips: List[Clip]
    total_clips: int
    successful_clips: int
    failed_clips: int
    total_cost: Decimal
    total_generation_time: float

class VideoOutput(BaseModel):
    job_id: UUID
    video_url: str
    duration: float
    audio_duration: float
    sync_drift: float  # seconds
    clips_used: int
    clips_trimmed: int
    clips_looped: int
    transitions_applied: int
    file_size_mb: float
    composition_time: float
    cost: Decimal
    status: Literal["success", "failed"]
```

**Success Criteria**:
✅ All models validate input correctly  
✅ Models serialize/deserialize to/from JSON  
✅ Type hints are accurate  
✅ Models match database schema  
✅ Models can be used in FastAPI request/response

---

### 5. Storage Utilities (`storage.py`)

**Purpose**: Supabase Storage operations for file upload/download.

**Requirements**:
- Upload files to Supabase Storage buckets
- Download files from buckets
- Generate signed URLs with expiration
- Delete files
- Handle errors gracefully

**API**:
```python
from shared.storage import storage

# Upload
url = await storage.upload_file(
    bucket="audio-uploads",
    path="user_id/job_id/file.mp3",
    file_data: bytes,
    content_type: str
)

# Download
file_data = await storage.download_file(
    bucket="audio-uploads",
    path="user_id/job_id/file.mp3"
)

# Signed URL
signed_url = await storage.get_signed_url(
    bucket="video-outputs",
    path="job_id/final_video.mp4",
    expires_in: int = 3600  # seconds
)

# Delete
await storage.delete_file(
    bucket="video-clips",
    path="job_id/clip_0.mp4"
)
```

**Buckets**:
- `audio-uploads`: User-uploaded audio files
- `reference-images`: Generated reference images
- `video-clips`: Generated video clips
- `video-outputs`: Final composed videos

**Features**:
- Automatic content-type detection
- File size validation
- Error handling (network errors, permission errors)
- Retry logic for transient failures
- Permission handling: Uses Supabase service key which bypasses RLS policies. Bucket-level permissions are configured in Supabase dashboard (private buckets with service key access).

**Success Criteria**:
✅ Upload/download works for all file types  
✅ Signed URLs expire correctly  
✅ File deletion works  
✅ Handles errors gracefully  
✅ Respects bucket permissions (service key access)

---

### 6. Error Handling (`errors.py`)

**Purpose**: Custom exception classes for consistent error handling.

**Exception Hierarchy**:
```python
class PipelineError(Exception):
    """Base exception for all pipeline errors"""
    def __init__(self, message: str, job_id: Optional[UUID] = None, code: Optional[str] = None):
        self.message = message
        self.job_id = job_id
        self.code = code
        super().__init__(self.message)

class ConfigError(PipelineError):
    """Configuration errors (missing env vars, invalid settings)"""
    pass

class AudioAnalysisError(PipelineError):
    """Audio analysis failures"""
    pass

class GenerationError(PipelineError):
    """AI generation failures (images, video)"""
    pass

class CompositionError(PipelineError):
    """Video composition failures"""
    pass

class BudgetExceededError(PipelineError):
    """Cost exceeds budget limit"""
    pass

class RetryableError(PipelineError):
    """Error that can be retried"""
    pass

class ValidationError(PipelineError):
    """Input validation errors"""
    pass
```

**Features**:
- Base exception with common attributes (job_id, message, code)
- Specific exceptions for different failure types
- Retryable flag for error classification

**Success Criteria**:
✅ All exceptions inherit from PipelineError  
✅ Exceptions include job_id when available  
✅ Retryable errors are properly marked  
✅ Error messages are clear and actionable

---

### 7. Retry Logic (`retry.py`)

**Purpose**: Decorator for automatic retry with exponential backoff.

**Requirements**:
- Exponential backoff (2s, 4s, 8s)
- Configurable max attempts
- Retry only on specific exceptions
- Log retry attempts

**API**:
```python
from shared.retry import retry_with_backoff
from shared.errors import RetryableError

@retry_with_backoff(max_attempts=3, base_delay=2)
async def call_openai_api():
    # Will retry on RetryableError
    response = await openai_client.call(...)
    return response
```

**Features**:
- Exponential backoff: `delay = base_delay * (2 ** attempt_number)`
- Only retries on `RetryableError` or specified exceptions
- Logs each retry attempt with attempt number
- Raises last exception if all retries fail

**Success Criteria**:
✅ Retries correct number of times  
✅ Backoff delay increases correctly  
✅ Only retries on specified exceptions  
✅ Logs retry attempts  
✅ Raises exception after max attempts

---

### 8. Cost Tracking (`cost_tracking.py`)

**Purpose**: Track API costs per job and enforce budget limits.

**Requirements**:
- Track costs per API call
- Aggregate costs per stage/job
- Enforce $20/job budget limit
- Store costs in database

**API**:
```python
from shared.cost_tracking import cost_tracker

# Track cost
await cost_tracker.track_cost(
    job_id=job_id,
    stage="video_generation",
    api_name="svd",
    cost=Decimal("0.06")
)

# Get total cost
total = await cost_tracker.get_total_cost(job_id)

# Check budget
can_proceed = await cost_tracker.check_budget(
    job_id=job_id,
    new_cost=Decimal("0.10"),
    limit=Decimal("20.00")
)

# Enforce budget (raises BudgetExceededError if exceeded)
await cost_tracker.enforce_budget_limit(
    job_id=job_id,
    limit=Decimal("20.00")
)
```

**Features**:
- Stores costs in `job_costs` table
- Updates `jobs.total_cost` field
- Raises `BudgetExceededError` if limit exceeded
- Async-safe (uses `asyncio.Lock` for concurrent video generation operations)
- Database-level atomic operations for cost updates

**Success Criteria**:
✅ Costs tracked accurately  
✅ Total cost calculated correctly  
✅ Budget limit enforced  
✅ Costs stored in database  
✅ Async-safe for concurrent operations (parallel video generation)

---

### 9. Logging (`logging.py`)

**Purpose**: Structured logging setup for all modules.

**Requirements**:
- Structured JSON logging
- Include job_id, module, stage in logs
- Configurable log level
- Console and file output

**API**:
```python
from shared.logging import get_logger

logger = get_logger("audio_parser")

logger.info("Processing audio", extra={"job_id": job_id, "duration": 180})
logger.error("Failed to detect beats", extra={"job_id": job_id, "error": str(e)})
```

**Log Format**:
```json
{
  "timestamp": "2025-11-14T10:30:00Z",
  "level": "INFO",
  "module": "audio_parser",
  "job_id": "550e8400-...",
  "message": "Processing audio",
  "duration": 180
}
```

**Features**:
- JSON structured logging
- Automatic job_id injection (if available in context)
- Log level from environment variable
- File rotation (max 100MB, keep 5 files)

**Success Criteria**:
✅ Logs include all required fields  
✅ Log level configurable  
✅ JSON format is valid  
✅ File rotation works  
✅ Job_id automatically included

---

### 10. Validation Utilities (`validation.py`)

**Purpose**: Shared validation utilities for common input validation tasks.

**Requirements**:
- File validation (size, MIME type)
- Prompt validation (length, content)
- Audio file specific validation
- Consistent error messages

**API**:
```python
from shared.validation import (
    validate_audio_file,
    validate_prompt,
    validate_file_size
)

# Validate audio file
try:
    validate_audio_file(file, max_size_mb=10)
except ValidationError as e:
    # Handle error

# Validate prompt
try:
    validate_prompt(prompt, min_length=50, max_length=500)
except ValidationError as e:
    # Handle error

# Generic file size validation
validate_file_size(file_size_bytes, max_size_bytes=10 * 1024 * 1024)
```

**Features**:
- Audio file validation (MP3, WAV, FLAC, max 10MB)
- Prompt length validation (50-500 characters)
- MIME type checking
- File size validation
- Clear error messages with ValidationError

**Success Criteria**:
✅ All validation functions work correctly  
✅ Error messages are clear and actionable  
✅ Handles edge cases (empty files, invalid types)  
✅ Consistent validation across modules

---

## Implementation Order

1. **config.py** (30 min) - Foundation for everything
2. **errors.py** (30 min) - Error handling (needed by other components)
3. **database.py** (30 min) - Needed for models and cost tracking
4. **redis_client.py** (30 min) - Needed for caching
5. **models/** (2 hours) - Define all interfaces
6. **storage.py** (1 hour) - File operations
7. **retry.py** (1 hour) - Retry logic
8. **cost_tracking.py** (1 hour) - Cost tracking (depends on database.py)
9. **logging.py** (30 min) - Logging setup
10. **validation.py** (30 min) - Validation utilities

**Total: 8-9 hours**

**Note**: `cost_tracking.py` depends on `database.py`, so database must be completed first.

---

## Testing Requirements

Each component must have:
- Unit tests (test in isolation)
- Integration tests (test with real services)
- Error handling tests (test failure scenarios)

**Test Coverage Target**: 80%+

---

## Success Criteria (Overall)

✅ All components can be imported without errors  
✅ All components work with real services (Supabase, Redis)  
✅ Data models validate correctly  
✅ Error handling is consistent  
✅ Cost tracking is accurate  
✅ Logging provides useful information  
✅ Components are async-safe where needed (for concurrent operations)  
✅ Documentation is complete  
✅ Validation utilities prevent invalid inputs  

---

## Dependencies

**Python Packages**:
- `pydantic` >= 2.0 (data models)
- `supabase` >= 2.0 (database, storage - includes async support)
- `redis` >= 5.0 (caching - includes async support via asyncio)
- `python-dotenv` >= 1.0 (config loading)

**Note**: Supabase Python client handles database connections internally. No need for `asyncpg` or `psycopg2` as direct dependencies.

**External Services**:
- Supabase project (database + storage + auth)
- Redis instance (caching + BullMQ queue)

---

## Notes

- All components must be async-compatible (use `async/await`)
- All components must be type-hinted (mypy compliance)
- All components must handle errors gracefully
- All components must be documented (docstrings)
- All components must be testable (dependency injection)
- Database client uses Supabase Python client (not raw PostgreSQL drivers)
- Redis client uses redis-py 5.0+ with async support
- Cost tracking uses `asyncio.Lock` for concurrent-safe operations
- Storage uses Supabase service key (bypasses RLS for backend operations)

**Database API Design**: The database client wraps Supabase's query builder API. For complex queries, modules can access the underlying Supabase client directly via `db.client` if needed.

**Next Steps**: Once shared components are complete, modules can be developed in parallel using these standardized interfaces.

