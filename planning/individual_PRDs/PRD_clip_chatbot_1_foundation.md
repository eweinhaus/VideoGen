# Clip Chatbot Feature - Part 1: Foundation & Data Infrastructure

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** MVP - Part 1 of 3  
**Dependencies:** 
- All 8 modules complete ✅
- Video generation pipeline working ✅
- Frontend job detail page ✅

**Related Documents:**
- `PRD_clip_chatbot_2_regeneration.md` - Part 2: Regeneration Core
- `PRD_clip_chatbot_3_integration.md` - Part 3: Integration & Polish
- `directions.md` (lines 213-218) - Iterative refinement requirements

---

## Executive Summary

This PRD defines Part 1 of the MVP clip chatbot feature: foundation infrastructure including thumbnail generation, data loading from existing job stages, clip list API, and the clip selector UI component. This part establishes the data infrastructure needed for clip regeneration.

**Key Deliverables:**
- Thumbnail generation (simplified first-frame extraction)
- Data loading infrastructure from `job_stages.metadata`
- Clip list API endpoint
- ClipSelector UI component
- Database schema for thumbnails

**Timeline:** Week 1  
**Success Criteria:** Users can view all clips with thumbnails and select a clip to edit

---

## Objectives

1. **Thumbnail Generation:** Generate clip thumbnails during video generation (async, non-blocking)
2. **Data Loading:** Load clip data from existing `job_stages` table (not separate table)
3. **Clip List API:** Expose clip metadata with thumbnails via REST API
4. **Clip Selector UI:** Display clips in grid with thumbnails, lyrics, and timestamps

---

## User Stories

**US-1: Clip Selection**
- As a user, I want to see all clips from my video with thumbnails and lyrics, so I can easily identify which clip to modify.

**US-2: Thumbnail Display**
- As a user, I want to see visual thumbnails for each clip, so I can quickly identify clips visually.

**US-3: Clip Metadata**
- As a user, I want to see clip timestamps and lyrics preview, so I can understand what each clip contains.

---

## System Architecture

### Data Flow

```
Video Generator (Module 7)
    ↓ (after clip upload)
Thumbnail Generator (first frame extraction)
    ↓
Supabase Storage (clip-thumbnails bucket)
    ↓
clip_thumbnails table
    ↓
GET /jobs/{id}/clips API
    ↓
ClipSelector UI Component
```

### Component Structure

```
Frontend:
  - ClipSelector.tsx (new component)

Backend:
  - modules/video_generator/process.py (thumbnail generation)
  - api_gateway/routes/clips.py (new route)
  - modules/clip_regenerator/data_loader.py (new module)

Database:
  - clip_thumbnails table (new)
```

---

## Detailed Requirements

### 1. Thumbnail Generation

#### 1.1 Generation Strategy

**When:** During initial video generation, after clip upload to Supabase Storage

**How (Simplified - Quick Win):**
1. After clip is generated and uploaded to Supabase Storage
2. Extract first frame from video using FFmpeg (reuse existing infrastructure)
3. Resize to 320x180 (16:9 aspect ratio) using FFmpeg or Pillow
4. Upload to `clip-thumbnails` bucket
5. Store URL in `clip_thumbnails` table
6. **Async operation** (don't block video generation pipeline)

**Rationale:** FFmpeg is already required by Composer module, so we reuse it for consistency and reliability. Performance difference is negligible for async operation.

#### 1.2 Implementation

**Location:** `modules/video_generator/process.py`

**Dependencies:**
- FFmpeg (already required by Composer module)
- `Pillow` for image resizing (optional, can use FFmpeg scale filter)

**Code Structure:**
```python
async def generate_clip_thumbnail(
    clip_url: str,
    job_id: UUID,
    clip_index: int
) -> Optional[str]:
    """
    Generate thumbnail for a clip (async, non-blocking).
    
    Uses FFmpeg to extract first frame and resize to 320x180.
    Returns thumbnail URL or None if generation fails.
    """
    try:
        # Download clip to temp file
        temp_clip_path = await download_to_temp(clip_url)
        
        # Extract first frame and resize using FFmpeg
        # ffmpeg -i clip.mp4 -vf "scale=320:180" -frames:v 1 thumbnail.jpg
        thumbnail_path = await extract_frame_with_ffmpeg(
            temp_clip_path,
            output_size=(320, 180)
        )
        
        # Upload to Supabase Storage
        thumbnail_url = await upload_thumbnail(thumbnail_path, job_id, clip_index)
        
        # Store in database
        await store_thumbnail_url(job_id, clip_index, thumbnail_url)
        
        # Cleanup temp files
        await cleanup_temp_files([temp_clip_path, thumbnail_path])
        
        return thumbnail_url
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
        return None  # Non-blocking failure
```

**Integration:**
- Call `asyncio.create_task(generate_clip_thumbnail(...))` after clip upload
- Fire-and-forget: Don't wait for completion
- Log errors but don't fail video generation

#### 1.3 Storage

**Bucket:** `clip-thumbnails` (private)
- Path: `{job_id}/clip_{clip_index}_thumbnail.jpg`
- TTL: Same as video clips (14 days)

**Performance:**
- First frame extraction: ~200-400ms (FFmpeg subprocess call)
- Async operation doesn't block video generation pipeline
- Reuses existing FFmpeg infrastructure (no additional dependencies)
- **Note:** Performance is acceptable for async, non-blocking operation

---

### 2. Data Loading Infrastructure

#### 2.1 Overview

Clips are stored in `job_stages.metadata` as JSON, not a separate table. We need to load and reconstruct Pydantic models from this JSON data.

#### 2.2 Module Structure

**Location:** `modules/clip_regenerator/data_loader.py`

**Functions:**
```python
async def load_clips_from_job_stages(
    job_id: UUID
) -> Optional[Clips]:
    """Load Clips object from job_stages.metadata"""
    
async def load_clip_prompts_from_job_stages(
    job_id: UUID
) -> Optional[ClipPrompts]:
    """Load ClipPrompts from job_stages.metadata"""
    
async def load_scene_plan_from_job_stages(
    job_id: UUID
) -> Optional[ScenePlan]:
    """Load ScenePlan from job_stages.metadata"""
    
async def load_reference_images_from_job_stages(
    job_id: UUID
) -> Optional[ReferenceImages]:
    """Load ReferenceImages from job_stages.metadata"""
```

#### 2.3 Data Structure

**job_stages.metadata format:**
```json
{
  "clips": {
    "clips": [
      {
        "clip_index": 0,
        "video_url": "https://...",
        "actual_duration": 12.5,
        "target_duration": 12.0,
        ...
      }
    ],
    "total_clips": 6,
    "successful_clips": 6,
    ...
  }
}
```

**Loading Process:**
1. Query `job_stages` table: `WHERE job_id={job_id} AND stage_name='video_generator'`
2. Extract `metadata` JSONB column
3. Parse JSON to dictionary
4. Access clips data: `metadata['clips']['clips']` (nested structure)
5. Reconstruct Pydantic model: `Clips(**metadata['clips'])`
6. Validate model (Pydantic will raise if invalid)

**Note:** Structure verified against actual orchestrator implementation. The metadata contains `{"clips": {"clips": [...], "total_clips": ..., "successful_clips": ..., "failed_clips": ...}}`.

#### 2.4 Error Handling

- If stage not found: Return `None` (job may not be completed)
- If metadata invalid: Log error, return `None`
- If Pydantic validation fails: Log error, return `None`

---

### 3. Clip List API

#### 3.1 Endpoint

**GET /api/v1/jobs/{job_id}/clips**

**Purpose:** List all clips for a job with thumbnails and metadata.

**Request:**
- Path: `/api/v1/jobs/{job_id}/clips`
- Method: GET
- Auth: Required (JWT token)
- Query params: None

**Response:**
```json
{
  "clips": [
    {
      "clip_index": 0,
      "thumbnail_url": "https://...",
      "timestamp_start": 0.0,
      "timestamp_end": 12.5,
      "lyrics_preview": "In the city of lights...",
      "duration": 12.5,
      "is_regenerated": false,
      "original_prompt": "A cyberpunk street scene..."
    },
    ...
  ],
  "total_clips": 6
}
```

#### 3.2 Implementation

**Location:** `api_gateway/routes/clips.py` (new file)

**Process:**
1. Verify job exists and belongs to user
2. Check job status (must be `completed`)
3. Load clips from `job_stages.metadata` using `data_loader.py`
4. **Validate clip_index bounds** (if provided in query params for future use)
   - Ensure `0 <= clip_index < total_clips`
   - Return 400 Bad Request if invalid
5. Load thumbnails from `clip_thumbnails` table
6. Load lyrics from `job_stages.metadata` (audio_parser stage)
   - **Reuse existing alignment:** Audio parser already aligns lyrics to clip boundaries
   - Load from `job_stages.metadata` where `stage_name='audio_parser'`
   - Extract `clip_lyrics` or reconstruct from `lyrics` + `clip_boundaries`
7. Combine data and return

**Error Handling:**
- 404: Job not found
- 403: Job belongs to different user
- 400: Job not completed yet
- 400: Invalid clip_index (if provided, out of bounds)

**Router Registration:**
- Register router in `api_gateway/main.py`
- Follow existing pattern: `app.include_router(clips_router, prefix="/api/v1", tags=["clips"])`

---

### 4. ClipSelector UI Component

#### 4.1 Component Structure

**Location:** `project/frontend/components/ClipSelector.tsx`

**Props:**
```typescript
interface ClipSelectorProps {
  jobId: string
  onClipSelect: (clipIndex: number) => void
  selectedClipIndex?: number
}
```

#### 4.2 Requirements

**Layout:**
- Grid layout (responsive: 2-4 columns)
- Each clip card shows:
  - Thumbnail image (320x180, lazy-loaded)
  - Clip index badge (e.g., "Clip 1", "Clip 2")
  - Timestamp range (e.g., "0:00 - 0:12")
  - Lyrics preview (first 2-3 lines, truncated with "...")
  - Duration overlay
  - "Regenerated" badge (if applicable)

**Interactions:**
- Click to select clip (highlighted border)
- Loading state during data fetch
- Error state if thumbnails unavailable (show placeholder)
- Empty state if no clips found

**Design:**
```
┌─────────────────────────────────────────┐
│  Select a Clip to Edit                 │
├─────────────────────────────────────────┤
│  ┌──────┐  ┌──────┐  ┌──────┐         │
│  │[IMG] │  │[IMG] │  │[IMG] │         │
│  │Clip 1│  │Clip 2│  │Clip 3│         │
│  │0-12s │  │12-24s│  │24-36s│         │
│  │"In the..."│"city of..."│"lights..."│
│  └──────┘  └──────┘  └──────┘         │
│                                         │
│  ┌──────┐  ┌──────┐  ┌──────┐         │
│  │[IMG] │  │[IMG] │  │[IMG] │         │
│  │Clip 4│  │Clip 5│  │Clip 6│         │
│  │36-48s│  │48-60s│  │60-72s│         │
│  │"shining..."│"bright..."│"tonight..."│
│  └──────┘  └──────┘  └──────┘         │
└─────────────────────────────────────────┘
```

#### 4.3 Data Fetching

**API Call:**
```typescript
const { data, error, loading } = useSWR(
  `/api/v1/jobs/${jobId}/clips`,
  fetcher
)
```

**State Management:**
- Store clips in component state
- Handle loading and error states
- Update selected clip index on click

---

### 5. Database Schema

#### 5.1 New Table

**clip_thumbnails:**
```sql
CREATE TABLE clip_thumbnails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  thumbnail_url TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(job_id, clip_index)
);

CREATE INDEX idx_clip_thumbnails_job_id ON clip_thumbnails(job_id);
```

**RLS Policies:**
- Users can only view thumbnails for their own jobs
- Service role can insert/update/delete

---

## Implementation Tasks

### Task 1: Thumbnail Generation
- [ ] Create `generate_clip_thumbnail()` function using FFmpeg
- [ ] Implement FFmpeg subprocess call for frame extraction
- [ ] Add image resizing (FFmpeg scale filter or Pillow)
- [ ] Integrate into `video_generator/process.py` (async task)
- [ ] Create `clip-thumbnails` Supabase Storage bucket
- [ ] Test thumbnail generation with real clips
- [ ] Verify async operation doesn't block pipeline

### Task 2: Data Loading Module
- [ ] Create `modules/clip_regenerator/data_loader.py`
- [ ] Implement `load_clips_from_job_stages()`
- [ ] Implement `load_clip_prompts_from_job_stages()`
- [ ] Implement `load_scene_plan_from_job_stages()`
- [ ] Implement `load_reference_images_from_job_stages()`
- [ ] Add unit tests for data loading

### Task 3: Clip List API
- [ ] Create `api_gateway/routes/clips.py`
- [ ] Implement `GET /api/v1/jobs/{job_id}/clips` endpoint
- [ ] Add authentication and authorization
- [ ] Integrate with `data_loader.py`
- [ ] Add lyrics alignment logic
- [ ] Add error handling
- [ ] Add API tests

### Task 4: ClipSelector UI
- [ ] Create `ClipSelector.tsx` component
- [ ] Implement grid layout (responsive)
- [ ] Add thumbnail display (lazy loading)
- [ ] Add clip metadata display
- [ ] Add selection highlighting
- [ ] Add loading and error states
- [ ] Add placeholder for missing thumbnails
- [ ] Test with real job data

### Task 5: Database Migration
- [ ] Create migration file for `clip_thumbnails` table
- [ ] Add RLS policies
- [ ] Test migration on staging

---

## Testing Strategy

### Unit Tests
- Data loader functions (load from job_stages)
- Thumbnail generation (frame extraction, resizing)
- Lyrics alignment to clip boundaries

### Integration Tests
- Clip list API endpoint
- Thumbnail generation integration
- Database operations

### E2E Tests
- Complete flow: Generate video → Thumbnails created → API returns clips → UI displays clips

---

## Success Criteria

### Functional
- ✅ Thumbnails generated for all clips during video generation
- ✅ Clip list API returns all clips with thumbnails and metadata
- ✅ ClipSelector UI displays clips in grid layout
- ✅ Users can select clips by clicking

### Performance
- ✅ Thumbnail generation: <200ms per clip (async, non-blocking)
- ✅ Clip list API: <500ms response time
- ✅ UI loads clips in <1s

### Quality
- ✅ Thumbnails are clear and representative of clip content
- ✅ Lyrics aligned correctly to clip boundaries
- ✅ Error handling graceful (missing thumbnails show placeholder)

---

## Dependencies

### External Services
- Supabase Storage (for thumbnail storage)
- Supabase PostgreSQL (for clip_thumbnails table)

### Internal Modules
- Video Generator (thumbnail generation integration)
- API Gateway (clip list endpoint)

### Frontend
- Next.js 14 (ClipSelector component)
- SWR or React Query (data fetching)

---

## Risks & Mitigations

### Risk 1: Thumbnail Generation Failure
**Risk:** Thumbnail generation fails, blocking video generation  
**Mitigation:** Async operation, non-blocking, log errors but continue

### Risk 2: Data Loading Complexity
**Risk:** Loading from job_stages.metadata is complex or error-prone  
**Mitigation:** Comprehensive error handling, validation, unit tests

### Risk 3: Performance Issues
**Risk:** Clip list API slow with many clips  
**Mitigation:** Optimize queries, add caching, pagination if needed

---

## Next Steps

After completing Part 1, proceed to:
- **Part 2:** Regeneration Core (template system, LLM modifier, regeneration API)
- **Part 3:** Integration & Polish (composer integration, error handling, E2E testing)

