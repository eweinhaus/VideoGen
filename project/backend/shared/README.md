# Shared Components

Common utilities, data models, and services shared across all pipeline modules.

## Overview

This module provides foundational infrastructure required by all 8 pipeline modules:

- **Configuration Management**: Centralized environment variable handling
- **Error Handling**: Custom exception hierarchy
- **Database Client**: Supabase PostgreSQL wrapper
- **Redis Client**: Async caching utilities
- **Data Models**: Pydantic models defining module interfaces
- **Storage Utilities**: Supabase Storage operations
- **Retry Logic**: Exponential backoff decorator
- **Cost Tracking**: API cost tracking with budget enforcement
- **Logging**: Structured JSON logging
- **Validation Utilities**: Input validation functions

## Installation

```bash
pip install -r requirements.txt
```

## Dependencies

- `pydantic >= 2.0.0` - Data models and settings
- `pydantic-settings >= 2.0.0` - Settings management
- `supabase >= 2.0.0` - Database and storage
- `redis >= 5.0.0` - Caching
- `python-dotenv >= 1.0.0` - Environment variable loading

## Usage

### Configuration Management

```python
from shared.config import settings

# Access configuration values
supabase_url = settings.supabase_url
openai_api_key = settings.openai_api_key
log_level = settings.log_level
```

**Environment Variables Required:**
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_KEY` - Service role key
- `SUPABASE_ANON_KEY` - Anon key
- `REDIS_URL` - Redis connection string
- `OPENAI_API_KEY` - OpenAI API key
- `REPLICATE_API_TOKEN` - Replicate API token
- `JWT_SECRET_KEY` - JWT signing secret (min 32 chars)
- `ENVIRONMENT` - "development" | "staging" | "production"
- `LOG_LEVEL` - "DEBUG" | "INFO" | "WARNING" | "ERROR"

### Error Handling

```python
from shared.errors import (
    PipelineError,
    ConfigError,
    AudioAnalysisError,
    GenerationError,
    BudgetExceededError,
    RetryableError,
    ValidationError
)
from uuid import UUID

# Raise error with job_id
job_id = UUID("...")
raise GenerationError("Failed to generate video", job_id=job_id, code="GEN_FAILED")
```

### Database Client

```python
from shared.database import db

# Query using Supabase client
result = await db.client.table("jobs").select("*").eq("id", job_id).execute()

# Insert
await db.client.table("jobs").insert({
    "id": str(job_id),
    "user_id": str(user_id),
    "status": "queued",
    "audio_url": audio_url,
    "user_prompt": prompt
}).execute()

# Health check
is_healthy = await db.health_check()
```

### Redis Client

```python
from shared.redis_client import redis

# String operations
await redis.set("key", "value", ex=3600)  # TTL in seconds
value = await redis.get("key")

# JSON operations
await redis.set_json("key", {"data": "value"}, ttl=3600)
data = await redis.get_json("key")

# Delete
await redis.delete("key")

# Health check
is_healthy = await redis.health_check()
```

### Data Models

```python
from shared.models import Job, AudioAnalysis, ScenePlan, VideoOutput
from uuid import uuid4
from datetime import datetime

# Create a job
job = Job(
    id=uuid4(),
    user_id=uuid4(),
    status="queued",
    audio_url="https://example.com/audio.mp3",
    user_prompt="Create a cyberpunk music video",
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow()
)

# Serialize to JSON
json_data = job.model_dump_json()

# Deserialize from JSON
job = Job.model_validate_json(json_data)
```

### Storage Utilities

```python
from shared.storage import storage

# Upload file
url = await storage.upload_file(
    bucket="audio-uploads",
    path="user_id/job_id/file.mp3",
    file_data=file_bytes,
    content_type="audio/mpeg"
)

# Download file
file_data = await storage.download_file(
    bucket="audio-uploads",
    path="user_id/job_id/file.mp3"
)

# Generate signed URL
signed_url = await storage.get_signed_url(
    bucket="video-outputs",
    path="job_id/final_video.mp4",
    expires_in=3600  # 1 hour
)

# Delete file
await storage.delete_file(
    bucket="video-clips",
    path="job_id/clip_0.mp4"
)
```

### Retry Logic

```python
from shared.retry import retry_with_backoff
from shared.errors import RetryableError

@retry_with_backoff(max_attempts=3, base_delay=2)
async def call_openai_api():
    # Will retry on RetryableError with exponential backoff (2s, 4s, 8s)
    response = await openai_client.call(...)
    return response

# Custom retryable exceptions
@retry_with_backoff(
    max_attempts=5,
    base_delay=1,
    retryable_exceptions=(RetryableError, ConnectionError)
)
async def unreliable_operation():
    # Retries on RetryableError or ConnectionError
    pass
```

### Cost Tracking

```python
from shared.cost_tracking import cost_tracker
from decimal import Decimal
from uuid import uuid4

job_id = uuid4()

# Track cost
await cost_tracker.track_cost(
    job_id=job_id,
    stage="video_generation",
    api_name="svd",
    cost=Decimal("0.06")
)

# Get total cost
total = await cost_tracker.get_total_cost(job_id)

# Check budget before expensive operation
can_proceed = await cost_tracker.check_budget(
    job_id=job_id,
    new_cost=Decimal("10.00"),
    limit=Decimal("2000.00")
)

if not can_proceed:
    raise BudgetExceededError("Would exceed budget")

# Enforce budget limit (raises BudgetExceededError if exceeded)
await cost_tracker.enforce_budget_limit(job_id, limit=Decimal("2000.00"))
```

### Logging

```python
from shared.logging import get_logger, set_job_id
from uuid import uuid4

logger = get_logger("audio_parser")

# Set job_id in context for automatic injection
job_id = uuid4()
set_job_id(job_id)

# Log with job_id automatically included
logger.info("Processing audio", extra={"duration": 180})
logger.error("Failed to detect beats", extra={"error": str(e)})

# Log without job_id
set_job_id(None)
logger.info("System started")
```

**Log Format (JSON):**
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

### Validation Utilities

```python
from shared.validation import (
    validate_audio_file,
    validate_prompt,
    validate_file_size
)
from shared.errors import ValidationError
import io

# Validate audio file
try:
    with open("audio.mp3", "rb") as file:
        validate_audio_file(file, max_size_mb=10)
except ValidationError as e:
    print(f"Invalid audio file: {e}")

# Validate prompt
try:
    validate_prompt(prompt, min_length=50, max_length=500)
except ValidationError as e:
    print(f"Invalid prompt: {e}")

# Validate file size
validate_file_size(file_size_bytes, max_size_bytes=10 * 1024 * 1024)
```

## Testing

Run tests with pytest:

```bash
# Run all tests
pytest backend/shared/tests/

# Run with coverage
pytest backend/shared/tests/ --cov=backend/shared --cov-report=html

# Run specific test file
pytest backend/shared/tests/test_models.py
```

## Type Checking

Run mypy for type checking:

```bash
mypy backend/shared/
```

## Linting

Run ruff for linting:

```bash
ruff check backend/shared/
```

## Architecture Notes

### Async Compatibility

All components are async-compatible:
- Database operations use async wrappers for Supabase's sync client
- Redis client uses `redis.asyncio` for native async support
- Storage operations are async
- All I/O operations use `async/await`

### Concurrency Safety

- **Cost Tracking**: Uses `asyncio.Lock` per job_id for thread-safe concurrent operations
- **Redis**: Connection pooling handles concurrent requests
- **Database**: Supabase client handles connection pooling

### Error Handling

All exceptions inherit from `PipelineError` and can include:
- `message`: Error message
- `job_id`: Optional job ID for tracing
- `code`: Optional error code for categorization

### Data Models

All models use Pydantic v2:
- Automatic validation
- JSON serialization/deserialization
- Type hints for IDE support
- Field validators for constraints

## Storage Buckets

Configure these buckets in Supabase dashboard:

- `audio-uploads` - User-uploaded audio files (private)
- `reference-images` - Generated reference images (private)
- `video-clips` - Generated video clips (private)
- `video-outputs` - Final composed videos (private)

All buckets use service key access (bypasses RLS for backend operations).

## Next Steps

Once shared components are complete, modules can be developed in parallel using these standardized interfaces. See `PRD_shared.md` for detailed specifications.
