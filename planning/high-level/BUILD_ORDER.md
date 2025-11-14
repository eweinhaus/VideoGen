# Build Order & Dependencies

## Critical Path Analysis

### Phase 0: Foundation (MUST BUILD FIRST) ⚠️

**Shared Components** - Required by ALL modules:
1. **`backend/shared/`** - Build this FIRST
   - Supabase client configuration
   - Redis client configuration  
   - Database models/schemas (Pydantic models)
   - Common types/interfaces
   - Error handling utilities
   - Retry logic (exponential backoff)
   - Cost tracking utilities
   - Logging configuration
   - Environment variable management

2. **Infrastructure Setup**
   - Database schema (Supabase migrations)
   - Storage buckets configuration
   - Redis setup
   - Environment variables template

**Why First?** Every module depends on these shared utilities.

---

### Phase 1: Core Infrastructure (Parallel with Phase 0)

**API Gateway (Module 2)** - Partial implementation
- Basic REST endpoints structure
- Job queue setup (BullMQ + Redis)
- Database connection
- SSE handler skeleton
- **Can be built in parallel with shared components**

**Why Early?** Frontend needs API endpoints to connect to, even if they're stubs.

---

### Phase 2: Independent Modules (Can Build in Parallel)

**Audio Parser (Module 3)**
- **Dependencies**: Shared utilities, Supabase Storage
- **No dependencies on other modules**
- **Can be built independently**
- **Testable in isolation** (just needs audio file)

**Frontend (Module 1)**
- **Dependencies**: API Gateway endpoints (can use stubs initially)
- **Can be built in parallel** with backend modules
- Start with UI components, connect to API later

---

### Phase 3: Sequential Pipeline Modules

**Scene Planner (Module 4)**
- **Dependencies**: Audio Parser output (audio_data JSON)
- **Must wait for**: Audio Parser to be complete
- **Can be tested** with mock audio_data

**Reference Generator (Module 5)**
- **Dependencies**: Scene Planner output (plan JSON with scenes/characters)
- **Must wait for**: Scene Planner
- **Can be tested** with mock plan data

**Prompt Generator (Module 6)**
- **Dependencies**: Scene Planner (plan) + Reference Generator (reference images)
- **Must wait for**: Both Module 4 and 5
- **Can be tested** with mock plan + reference data

**Video Generator (Module 7)**
- **Dependencies**: Prompt Generator output (clip_prompts with reference URLs)
- **Must wait for**: Prompt Generator
- **Can be tested** with mock prompts

**Composer (Module 8)**
- **Dependencies**: 
  - Video Generator (clips)
  - Audio Parser (beat_timestamps, audio_url)
  - Scene Planner (transitions)
- **Must wait for**: Modules 3, 4, and 7
- **Final step** - brings everything together

---

## Recommended Build Order

### Day 1 Morning: Foundation
```
1. Infrastructure setup (Supabase, Redis, Railway)
2. backend/shared/ (all utilities)
3. Database schema migrations
4. API Gateway skeleton (endpoints, queue setup)
```

### Day 1 Afternoon: Independent Modules
```
5. Audio Parser (Module 3) - Test with sample audio
6. Frontend basic structure (upload UI, progress skeleton)
```

### Day 2 Morning: Planning & Generation
```
7. Scene Planner (Module 4) - Test with mock audio_data
8. Reference Generator (Module 5) - Test with mock plan
9. Prompt Generator (Module 6) - Test with mock plan + references
```

### Day 2 Afternoon: Video Generation
```
10. Video Generator (Module 7) - Test with mock prompts
11. Connect API Gateway orchestrator (wire modules 3-7 together)
```

### Day 3: Composition & Integration
```
12. Composer (Module 8) - Test with mock clips
13. Full end-to-end integration
14. Frontend completion (SSE, video player)
15. Error handling, retry logic, polish
```

---

## Dependency Graph

```
Infrastructure
    ↓
Shared Components (Phase 0)
    ↓
┌─────────────────┬──────────────────┐
│                 │                  │
API Gateway    Audio Parser      Frontend
(Phase 1)      (Phase 2)        (Phase 2)
    │                 │                  │
    │                 ↓                  │
    │          Scene Planner             │
    │          (Phase 3)                 │
    │                 ↓                  │
    │          Reference Generator       │
    │          (Phase 3)                 │
    │                 ↓                  │
    │          Prompt Generator          │
    │          (Phase 3)                 │
    │                 ↓                  │
    │          Video Generator           │
    │          (Phase 3)                 │
    │                 ↓                  │
    └──────────→ Composer ←──────────────┘
                (Phase 3)
```

---

## Shared Components Breakdown

### `backend/shared/` Structure

```
shared/
├── __init__.py
├── config.py              # Environment variables, settings
├── database.py            # Supabase client, connection pool
├── redis_client.py        # Redis connection, cache utilities
├── models/
│   ├── job.py            # Job, JobStage, JobCost Pydantic models
│   ├── audio.py          # AudioAnalysis Pydantic model
│   ├── scene.py          # ScenePlan, Character, Scene Pydantic models
│   └── video.py          # Clip, VideoOutput Pydantic models
├── storage.py             # Supabase Storage utilities (upload, download, signed URLs)
├── errors.py              # Custom exceptions, error handling
├── retry.py               # Retry decorator with exponential backoff
├── cost_tracking.py       # Cost tracking, budget enforcement
└── logging.py             # Structured logging setup
```

**Build Priority:**
1. `config.py` - Environment variables
2. `database.py` - Supabase connection
3. `redis_client.py` - Redis connection
4. `models/` - All Pydantic models (needed by all modules)
5. `storage.py` - File upload/download
6. `errors.py` - Error handling
7. `retry.py` - Retry logic
8. `cost_tracking.py` - Cost tracking
9. `logging.py` - Logging

---

## Testing Strategy by Phase

### Phase 0-1: Unit Tests
- Shared utilities (retry, cost tracking, storage)
- Database models validation
- API Gateway endpoints (with mocks)

### Phase 2: Integration Tests
- Audio Parser with real audio files
- Frontend with API Gateway (stubbed responses)

### Phase 3: Pipeline Tests
- Each module with mock inputs from previous module
- End-to-end with real data (start with short audio clips)

---

## Parallel Development Opportunities

**Can work in parallel:**
- Frontend + Backend modules (once API Gateway has stubs)
- Audio Parser + Scene Planner (once Audio Parser interface is defined)
- Reference Generator + Prompt Generator (once Scene Planner interface is defined)

**Must be sequential:**
- Scene Planner → Reference Generator → Prompt Generator → Video Generator → Composer

---

## Critical Interfaces (Define Early)

These interfaces should be defined in `shared/models/` before building dependent modules:

1. **Audio Parser Output** (`audio.py`)
   - AudioAnalysis model with beats, structure, lyrics, mood

2. **Scene Planner Output** (`scene.py`)
   - ScenePlan model with characters, scenes, clip_scripts, transitions

3. **Reference Generator Output** (`scene.py`)
   - ReferenceImages model with scene_references, character_references

4. **Prompt Generator Output** (`video.py`)
   - ClipPrompts model with prompts, reference URLs

5. **Video Generator Output** (`video.py`)
   - Clips model with video URLs, durations

---

## Key Takeaways

✅ **Build First**: Shared components, infrastructure, database schema  
✅ **Build Early**: API Gateway skeleton, Audio Parser  
✅ **Build in Parallel**: Frontend + Backend (once API stubs exist)  
✅ **Build Sequentially**: Scene Planner → Reference → Prompt → Video → Composer  
✅ **Define Interfaces Early**: Pydantic models in `shared/models/` before dependent modules

**The order DOES matter** - following this sequence prevents blocking and allows parallel work where possible.

