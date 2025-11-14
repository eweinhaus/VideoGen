# Module 2: API Gateway

**Tech Stack:** FastAPI (Python)  
**Status:** ✅ Implementation Complete

## Purpose
REST API server and SSE handler that orchestrates pipeline execution via job queue. The API Gateway is the central orchestration layer that coordinates the entire video generation pipeline.

## Key Features
- ✅ REST Endpoints (7 endpoints: upload, job status, job list, cancel, health, SSE stream, download)
- ✅ SSE Streaming for real-time progress events (Redis pub/sub)
- ✅ Job Queue (Redis-based queue with worker process)
- ✅ Pipeline Orchestrator (executes modules 3-8 sequentially)
- ✅ Cost Tracking (real-time tracking with $2000/job budget limit)
- ✅ Rate Limiting (5 jobs/hour/user, Redis sliding window)
- ✅ JWT Authentication (Supabase Auth integration with Redis caching)

## REST Endpoints

### `POST /api/v1/upload-audio`
Upload audio file and create video generation job.
- Validates file (≤10MB, MP3/WAV/FLAC)
- Validates prompt (50-500 characters)
- Pre-flight cost check (rejects if >$2000)
- Rate limit check (5 jobs/hour/user)
- Returns: `job_id`, `status`, `estimated_cost`

### `GET /api/v1/jobs/{job_id}`
Get job status (polling fallback, SSE preferred).
- Redis caching (30s TTL)
- Returns: Full job status with progress, cost, video_url

### `GET /api/v1/jobs`
List user's jobs with pagination and filtering.
- Query params: `status`, `limit` (default: 10, max: 50), `offset` (default: 0)
- Returns: Jobs list with `total`, `limit`, `offset`

### `POST /api/v1/jobs/{job_id}/cancel`
Cancel a queued or processing job.
- Removes from queue if queued
- Sets Redis cancellation flag if processing
- Cleans up intermediate files

### `GET /api/v1/health`
Health check endpoint.
- Checks database, Redis, queue status
- Returns 200 if healthy, 503 if unhealthy

### `GET /api/v1/jobs/{job_id}/stream`
SSE stream for real-time progress updates.
- Supports multiple connections per job (max 10)
- Heartbeat every 30s
- Initial state sent on connection
- Events: `progress`, `stage_update`, `message`, `cost_update`, `completed`, `error`, `heartbeat`

### `GET /api/v1/jobs/{job_id}/download`
Download final video file via signed URL.
- Generates signed URL (1 hour expiration)
- Returns: `download_url`, `expires_in`, `filename`

## Architecture

```
Frontend → API Gateway (FastAPI)
    ↓
  [REST Endpoints] → Job Creation → Redis Queue
    ↓                                    ↓
  [SSE Stream] ← Progress Events ← [Worker Process]
    ↑                                    ↓
  [Redis Pub/Sub] ←──────────────────────┘
    ↓
  [Pipeline Orchestrator]
    ↓
  Modules 3-8 (Sequential)
```

## Setup

### Environment Variables
Add to `.env`:
```bash
FRONTEND_URL=https://your-frontend.com
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
# ... other variables from shared/config.py
```

### Install Dependencies
```bash
cd project/backend
pip install -r requirements.txt
```

### Run API Gateway
```bash
# Development
uvicorn api_gateway.main:app --reload --port 8000

# Production
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
```

### Run Worker Process
```bash
# In separate terminal/container
python -m api_gateway.worker
```

## Testing

### Run Tests
```bash
cd project/backend
PYTHONPATH=. pytest api_gateway/tests/ -v
```

### Test Coverage
```bash
PYTHONPATH=. pytest api_gateway/tests/ --cov=api_gateway --cov-report=term
```

## File Structure

```
api_gateway/
├── main.py              # FastAPI app, routes, middleware, CORS
├── worker.py            # Worker process (processes jobs from queue)
├── orchestrator.py      # Pipeline orchestration
├── dependencies.py      # FastAPI dependencies (auth, request ID)
├── routes/
│   ├── upload.py        # POST /upload-audio
│   ├── jobs.py          # GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel
│   ├── stream.py        # GET /jobs/{id}/stream (SSE)
│   ├── download.py       # GET /jobs/{id}/download
│   └── health.py        # GET /health
├── services/
│   ├── rate_limiter.py  # Rate limiting (Redis sliding window)
│   ├── queue_service.py # Queue management
│   ├── event_publisher.py # Redis pub/sub event publisher
│   ├── sse_manager.py   # SSE connection management
│   └── db_helpers.py    # Database helper functions
└── tests/
    ├── test_dependencies.py
    ├── test_rate_limiter.py
    ├── test_queue_service.py
    ├── test_event_publisher.py
    └── test_sse_manager.py
```

## Implementation Status

### ✅ Completed
- Project structure and dependencies
- FastAPI application setup (CORS, middleware, error handling)
- Authentication (JWT validation with Redis caching)
- All 7 REST endpoints
- Rate limiting service
- Queue service and worker process
- Pipeline orchestrator
- SSE manager and stream endpoint
- Database operations
- Event publisher (Redis pub/sub)

### ⏳ Remaining (Testing & Documentation)
- Unit tests (structure created, tests to be implemented)
- Integration tests
- E2E tests
- Performance testing
- Documentation updates

## Notes

- **Database Schema**: Uses `id` as primary key (not `job_id`). Generated UUID is stored as `id`.
- **Queue**: Currently using Redis list as queue (simplified implementation). Can be upgraded to BullMQ later.
- **Modules**: Orchestrator uses stub implementations until modules 3-8 are implemented.
- **SSE**: Uses Redis pub/sub for event distribution from workers to FastAPI SSE connections.

## Next Steps

1. Implement pipeline modules (3-8) to replace stubs
2. Add comprehensive unit and integration tests
3. Performance testing and optimization
4. Production deployment configuration

