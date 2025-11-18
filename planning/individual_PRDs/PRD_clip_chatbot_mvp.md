# Clip Chatbot Feature - MVP PRD

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** Post-MVP Enhancement  
**Dependencies:** 
- All 8 modules complete ✅
- Video generation pipeline working ✅
- Frontend job detail page ✅

**Related Documents:**
- `PRD_clip_chatbot_post_mvp.md` - Post-MVP enhancements
- `directions.md` (lines 213-218) - Iterative refinement requirements

---

## Executive Summary

This PRD defines the MVP implementation of an AI-powered chatbot feature that enables users to select individual clips from their generated videos and request modifications through natural language instructions. The chatbot regenerates only the selected clip (from prompt generation to video generation) and recomposes the final video with the updated clip.

**Key Features:**
- Clip selection UI with thumbnails and lyrics
- Conversational chatbot interface
- Single-clip regeneration pipeline
- Full recomposition after regeneration
- Cost tracking and transparency

**Timeline:** 2-3 weeks  
**Success Criteria:** Users can select a clip, chat with AI to modify it, and receive updated video within 5-10 minutes

---

## Objectives

1. **Enable Selective Editing:** Users can modify individual clips without regenerating entire video
2. **Natural Language Interface:** Users interact via conversational chatbot
3. **Maintain Style Consistency:** Regenerated clips match overall video style
4. **Cost Transparency:** Users see regeneration costs before proceeding
5. **Iterative Refinement:** Support multi-turn conversations for fine-tuning

---

## User Stories

### Primary User Stories

**US-1: Clip Selection**
- As a user, I want to see all clips from my video with thumbnails and lyrics, so I can easily identify which clip to modify.

**US-2: Chatbot Interaction**
- As a user, I want to tell the chatbot "make it nighttime" and have it regenerate the selected clip, so I can refine my video without starting over.

**US-3: Conversational Refinement**
- As a user, I want to have a conversation with the chatbot (e.g., "make it brighter" → "add more motion"), so I can iteratively refine the clip.

**US-4: Cost Awareness**
- As a user, I want to see the estimated cost before regenerating a clip, so I can make informed decisions.

**US-5: Progress Tracking**
- As a user, I want to see progress during clip regeneration, so I know how long it will take.

**US-6: Result Preview**
- As a user, I want to see the updated video after regeneration, so I can verify the changes.

---

## System Architecture

### High-Level Flow

```
User selects clip → Opens chatbot → Enters instruction
    ↓
LLM modifies prompt (with full context)
    ↓
Video Generator regenerates single clip
    ↓
Composer recomposes video (full recomposition)
    ↓
User sees updated video
```

### Component Architecture

```
┌─────────────────────────────────────────────────┐
│              Frontend (Next.js)                 │
│  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ClipSelector  │  │   ClipChatbot           │ │
│  │  Component   │  │   Component             │ │
│  └──────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────┘
                    │
                    ↓ HTTP/SSE
┌─────────────────────────────────────────────────┐
│            API Gateway (FastAPI)                │
│  ┌──────────────────────────────────────────┐  │
│  │  Clip Regeneration Endpoints              │  │
│  │  - GET /jobs/{id}/clips                  │  │
│  │  - POST /jobs/{id}/clips/{idx}/regenerate│  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────┐
│      Clip Regenerator Module (New)               │
│  ┌──────────────┐  ┌─────────────────────────┐ │
│  │LLM Modifier  │  │  Thumbnail Generator    │ │
│  │              │  │                         │ │
│  └──────────────┘  └─────────────────────────┘ │
│  ┌──────────────┐  ┌─────────────────────────┐ │
│  │Context       │  │  Process Orchestrator   │ │
│  │Builder       │  │                         │ │
│  └──────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────┐
│  Existing Modules (Reused)                      │
│  - Prompt Generator (modified prompt)            │
│  - Video Generator (single clip)                 │
│  - Composer (full recomposition)                │
└─────────────────────────────────────────────────┘
```

---

## Detailed Requirements

### 1. Clip Selection UI

#### 1.1 ClipSelector Component

**Purpose:** Display all clips from a completed video with visual identifiers.

**Requirements:**
- Grid layout (responsive: 2-4 columns)
- Each clip card shows:
  - Thumbnail image (generated during initial video generation)
  - Clip index badge (e.g., "Clip 1", "Clip 2")
  - Timestamp range (e.g., "0:00 - 0:12")
  - Lyrics preview (first 2-3 lines, truncated with "...")
  - Duration overlay
  - "Regenerated" badge (if applicable)
- Click to select clip (highlighted border)
- Loading state during thumbnail generation
- Error state if thumbnail unavailable

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

**Data Requirements:**
- Clip metadata from `job_stages.metadata` (where `stage_name='video_generator'`)
  - Load `Clips` object from JSON: `metadata['clips']`
  - Extract individual `Clip` objects from `clips.clips` list
- Thumbnail URLs from `clip_thumbnails` table
- Lyrics from `AudioAnalysis` (stored in `job_stages.metadata` where `stage_name='audio_parser'`)
  - Align lyrics to clip boundaries using `clip_boundaries` from audio analysis

**API Endpoint:**
- `GET /api/v1/jobs/{job_id}/clips`
- Returns: `List[ClipInfo]` where `ClipInfo` includes:
  - `clip_index: int`
  - `thumbnail_url: str`
  - `timestamp_start: float`
  - `timestamp_end: float`
  - `lyrics_preview: str`
  - `duration: float`
  - `is_regenerated: bool`

---

### 2. Chatbot Interface

#### 2.1 ClipChatbot Component

**Purpose:** Conversational interface for clip modification instructions.

**Requirements:**
- Chat message list (scrollable)
- Input field with send button
- Loading indicator during processing
- Cost estimate display (before regeneration)
- Cancel button (during regeneration)
- Error handling with retry option

**Design:**
```
┌─────────────────────────────────────────┐
│  Chat with AI                            │
├─────────────────────────────────────────┤
│  [Message History]                      │
│  ┌───────────────────────────────────┐ │
│  │ User: "make it nighttime"          │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ AI: "I'll modify the prompt to    │ │
│  │      make this clip nighttime.    │ │
│  │      Estimated cost: $0.15"       │ │
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ [Regenerating... 45%]              │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Type your instruction...          │ │
│  └───────────────────────────────────┘ │
│  [Send] [Cancel]                        │
└─────────────────────────────────────────┘
```

**Conversation Flow:**
1. User selects clip → Chatbot opens with greeting
2. User enters instruction → LLM processes
3. System shows cost estimate → User confirms
4. Regeneration starts → Progress updates
5. Completion → Updated video shown

**Message Types:**
- User messages (right-aligned, blue)
- AI responses (left-aligned, gray)
- System messages (centered, info/warning/error)
- Progress updates (centered, with progress bar)

**State Management:**
- Conversation history (in-memory, session-based)
- Current regeneration status
- Error state
- Cost estimate

---

### 3. Backend: Clip Regenerator Module

#### 3.1 Module Structure

```
modules/clip_regenerator/
├── __init__.py
├── process.py              # Main orchestration
├── llm_modifier.py         # LLM prompt modification
├── template_matcher.py     # Template matching for common modifications (NEW)
├── context_builder.py      # Build context for LLM
├── data_loader.py          # Load clips/prompts from job_stages (NEW)
└── config.py              # Configuration
```

**Note:** Thumbnail generation moved to Video Generator module (not in clip_regenerator)

#### 3.2 Process Flow

```python
async def regenerate_clip(
    job_id: UUID,
    clip_index: int,
    user_instruction: str,
    conversation_history: List[Dict[str, str]] = None
) -> RegenerationResult:
    """
    Regenerate a single clip based on user instruction.
    
    Steps:
    1. Load original clip data from job_stages.metadata:
       - Load Clips object from job_stages where stage_name='video_generator'
       - Extract ClipPrompt from job_stages where stage_name='prompt_generator'
       - Load ScenePlan from job_stages where stage_name='scene_planner'
       - Load ReferenceImages from job_stages where stage_name='reference_generator'
    2. Build context for LLM (original prompt + scene plan + style + instruction)
       - Limit conversation history to last 5 messages (summarize older)
    3. Check for template match (common modifications like "brighter", "nighttime")
       - If template match: use template transformation (skip LLM call)
       - If no match: Call LLM to modify prompt
    4. Generate new clip (reuse Video Generator module)
       - Create new ClipPrompt with modified prompt
       - Call video_generator.process() with single clip
    5. Replace clip in Clips object:
       - Update clips[clip_index] with new Clip
       - Reconstruct Clips object with updated clip
    6. Recompose video (full recomposition):
       - Re-download all clips from Supabase Storage
       - Re-normalize all clips to 1080p, 30 FPS
       - Re-apply transitions (recreate concat file)
       - Re-sync audio with video
       - Re-encode final video
       - Upload new final video to Supabase Storage
    7. Update job status and return updated video URL
    """
```

**Data Loading Details:**
- Clips are stored in `job_stages.metadata` as JSON (not separate table)
- Load from: `job_stages` table where `job_id={job_id}` AND `stage_name='video_generator'`
- Metadata structure: `{"clips": {"clips": [...], "total_clips": 6, ...}}`
- Reconstruct `Clips` Pydantic model from JSON data
- Original `ClipPrompt` stored in `job_stages` where `stage_name='prompt_generator'`

#### 3.3 LLM Prompt Modification

**System Prompt:**
```
You are a video editing assistant. Modify video generation prompts based on user instructions while preserving style consistency.

Your task:
1. Understand the user's instruction
2. Modify the original prompt to incorporate the instruction
3. Preserve visual style, character consistency, and scene coherence
4. Keep prompt under 200 words
5. Maintain reference image compatibility

Output only the modified prompt, no explanations.
```

**User Prompt Template:**
```
Original Prompt: {original_prompt}

Scene Plan Summary:
- Style: {style_info}
- Characters: {character_names}
- Scenes: {scene_locations}
- Overall Mood: {mood}

User Instruction: {user_instruction}

Recent Conversation (last 3 messages):
{recent_conversation}

Modify the prompt to incorporate the user's instruction while maintaining consistency.
```

**Conversation History Management:**
- Store only last 5 messages in active conversation (reduce storage)
- Include only last 2-3 messages in LLM prompt (reduce token usage by 40-60%)
- Summarize older messages if needed: "Previous requests: made clip brighter, added motion"

**Template System (Quick Win):**
- Check for common modifications before LLM call
- Templates: "brighter", "darker", "nighttime", "daytime", "more motion", "less motion"
- Template transformations: Direct prompt modifications (e.g., "nighttime" → add "dark sky, stars, night lighting")
- If template match: Skip LLM call, apply transformation directly
- Reduces LLM costs by 30-40% for common requests

**LLM Configuration:**
- Model: GPT-4o (for quality) or Claude 3.5 Sonnet
- Temperature: 0.7 (creative but consistent)
- Max tokens: 300
- Retry: 3 attempts with exponential backoff
- **Cost optimization:** Use templates when possible, limit conversation history in prompt

---

### 4. Thumbnail Generation

#### 4.1 Generation Strategy

**When:** During initial video generation (in Video Generator module), after clip upload to Supabase Storage

**How (Simplified - Quick Win):**
1. After clip is generated and uploaded to Supabase Storage
2. Extract first frame from video using lightweight method (no FFmpeg needed)
3. Resize to 320x180 (16:9 aspect ratio) using image library (Pillow)
4. Upload to `clip-thumbnails` bucket
5. Store URL in `clip_thumbnails` table
6. **Async operation** (don't block video generation pipeline)

**Implementation:**
- Add to `modules/video_generator/process.py` after clip upload
- Use `opencv-python` or `imageio` to extract first frame: `frame = extract_first_frame(video_url)`
- Resize with Pillow: `Image.resize((320, 180))`
- Async operation using `asyncio.create_task()` (fire-and-forget)
- Error handling: If thumbnail generation fails, use placeholder image or skip (non-blocking)

**Storage:**
- Bucket: `clip-thumbnails` (private)
- Path: `{job_id}/clip_{clip_index}_thumbnail.jpg`
- TTL: Same as video clips (14 days)

**Performance:**
- First frame extraction: ~100-200ms (vs 500-1000ms with FFmpeg)
- Reduces thumbnail generation time by 50-70%
- No FFmpeg dependency for thumbnails

---

### 5. API Endpoints

#### 5.1 GET /api/v1/jobs/{job_id}/clips

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

**Error Handling:**
- 404: Job not found
- 403: Job belongs to different user
- 400: Job not completed yet

#### 5.2 POST /api/v1/jobs/{job_id}/clips/{clip_index}/regenerate

**Purpose:** Regenerate a single clip based on user instruction.

**Request:**
- Path: `/api/v1/jobs/{job_id}/clips/{clip_index}/regenerate`
- Method: POST
- Auth: Required (JWT token)
- Body:
```json
{
  "instruction": "make it nighttime",
  "conversation_history": [
    {"role": "user", "content": "make it brighter"},
    {"role": "assistant", "content": "I'll make the clip brighter..."}
  ]
}
```

**Response:**
```json
{
  "regeneration_id": "uuid",
  "estimated_cost": 0.15,
  "estimated_time": 180,
  "status": "queued"
}
```

**Error Handling:**
- 404: Job or clip not found
- 403: Job belongs to different user
- 400: Invalid clip_index or instruction
- 429: Too many regenerations (rate limit)

**SSE Events:**
- `regeneration_started` - Regeneration queued (job status: `regenerating`)
- `template_matched` - Template transformation applied (skip LLM)
- `prompt_modified` - LLM modified prompt (or template applied)
- `video_generating` - Video generation in progress (with progress %)
- `recomposing` - Recomposing video (with progress %)
- `regeneration_complete` - New video URL available (job status: `completed`)
- `regeneration_failed` - Error occurred (job status: `failed`, with error message)

**Progress Tracking:**
- Template check: 0-5% progress
- LLM modification (if needed): 5-10% progress
- Video generation: 10-60% progress (single clip)
- Recomposition: 60-100% progress (full recomposition)

#### 5.3 GET /api/v1/jobs/{job_id}/clips/{clip_index}/thumbnail

**Purpose:** Get thumbnail for a specific clip.

**Request:**
- Path: `/api/v1/jobs/{job_id}/clips/{clip_index}/thumbnail`
- Method: GET
- Auth: Required (JWT token)

**Response:**
- 302 Redirect to signed URL (1 hour expiration)
- 404: Thumbnail not found

---

### 6. Database Schema

#### 6.1 New Tables

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

**clip_regenerations:**
```sql
CREATE TABLE clip_regenerations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  original_prompt TEXT NOT NULL,
  modified_prompt TEXT NOT NULL,
  user_instruction TEXT NOT NULL,
  conversation_history JSONB,
  cost DECIMAL(10, 4) NOT NULL,
  status TEXT NOT NULL, -- 'queued', 'processing', 'completed', 'failed'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_clip_regenerations_job_id ON clip_regenerations(job_id);
CREATE INDEX idx_clip_regenerations_status ON clip_regenerations(status);
```

#### 6.2 Jobs Table Updates

**Add column:**
```sql
ALTER TABLE jobs ADD COLUMN regenerated_clips JSONB DEFAULT '[]';
-- Format: [{"clip_index": 0, "regeneration_id": "uuid", "regenerated_at": "timestamp"}]
```

---

### 7. Cost Tracking

#### 7.1 Cost Calculation

**Components:**
1. LLM call (prompt modification): ~$0.01-0.02
   - **Template match:** $0.00 (skip LLM call)
   - **LLM call:** $0.01-0.02 (GPT-4o or Claude 3.5)
2. Video generation (single clip): ~$0.10-0.15
   - Model-dependent (kling_v21: ~$0.10, veo_31: ~$0.15)
   - Use actual cost from previous regenerations for better estimates
3. Recomposition: $0.00 (compute only, but adds 60-90s processing time)
   - No API costs, but significant compute time
   - Document in UI: "Recomposition will take 1-2 minutes"

**Total per regeneration:** ~$0.11-0.17 (with template: ~$0.10-0.15)

**Estimation Strategy:**
- Before regeneration: Show estimated cost based on:
  - Template match check (if yes: $0.00 for LLM)
  - Model-specific video generation cost (from actual costs)
  - Historical average if available
- After completion: Track actual cost in `clip_regenerations` table
- Add to job total cost (`jobs.total_cost`)
- Show breakdown in UI: "LLM: $0.01, Video: $0.12, Total: $0.13"
- **Improve estimates over time:** Use actual costs from previous regenerations to refine estimates

#### 7.2 Budget Enforcement

- Check job total cost + estimated regeneration cost
- Warn if approaching budget limit ($2000 production, $50 dev)
- Allow regeneration if under limit
- Track separately for transparency

---

### 8. Error Handling

#### 8.1 Failure Scenarios

**LLM Modification Failure:**
- Retry 3 times with exponential backoff
- If all retries fail: Return error, keep original clip
- **Job status:** `completed` → `regenerating` → `completed` (or `failed`)

**Video Generation Failure:**
- Retry 3 times (reuse Video Generator retry logic)
- If fails: Return error, keep original clip, allow retry
- **Job status:** Remains `regenerating` until success or user cancels

**Recomposition Failure:**
- Retry 3 times (reuse Composer retry logic)
- If fails: Return error, keep original video
- **Job status:** `regenerating` → `failed` (with error message)

**Network/Storage Failures:**
- Retry with exponential backoff
- If persistent: Return error, allow manual retry
- **Job status:** `regenerating` → `failed` (retryable error)

#### 8.2 Error Messages

- User-friendly error messages
- Technical details in logs
- Retry button in UI
- Support contact for persistent issues

#### 8.3 Job Status State Machine

```
completed (original video)
    ↓
[User clicks "Regenerate Clip"]
    ↓
regenerating (job status updated)
    ↓
[LLM modification] → [Video generation] → [Recomposition]
    ↓
completed (updated video) OR failed (error occurred)
```

**Status Transitions:**
- `completed` → `regenerating`: User initiates regeneration
- `regenerating` → `completed`: Regeneration successful
- `regenerating` → `failed`: Regeneration failed (user can retry)
- `failed` → `regenerating`: User retries regeneration

---

### 9. Performance Requirements

#### 9.1 Response Times

- Clip list API: <500ms
- Regeneration start: <2s (queue job)
- LLM prompt modification: <10s
- Video generation: 30-60s (single clip)
- Recomposition: 60-90s (full recomposition)
- **Total regeneration time:** 2-3 minutes

#### 9.2 Scalability

- Support concurrent regenerations (different jobs)
- Rate limit: 5 regenerations per job per hour
- Queue-based processing (reuse existing job queue)

---

### 10. Security & Privacy

#### 10.1 Authentication

- All endpoints require JWT authentication
- Verify job ownership before allowing regeneration
- Rate limiting per user

#### 10.2 Data Privacy

- Conversation history stored in database (user's data)
- No sharing of prompts or instructions
- Thumbnails stored in private bucket
- Signed URLs with expiration

---

## Implementation Phases

### Phase 1: Foundation (Week 1)

1. **Thumbnail Generation (Simplified)**
   - Add thumbnail generation to Video Generator (first frame extraction)
   - Create `clip_thumbnails` table
   - Test thumbnail extraction and storage (async, non-blocking)

2. **Data Loading Infrastructure**
   - Create `data_loader.py` in clip_regenerator module
   - Implement functions to load Clips, ClipPrompts, ScenePlan from job_stages
   - Test data loading with real job data

3. **Clip List API**
   - Create `GET /api/v1/jobs/{job_id}/clips` endpoint
   - Load clips from `job_stages.metadata` (not separate table)
   - Return clip metadata with thumbnails
   - Test with completed jobs

4. **ClipSelector UI**
   - Create `ClipSelector.tsx` component
   - Display clips in grid layout
   - Show thumbnails, lyrics, timestamps
   - Test selection and highlighting

### Phase 2: Chatbot & Regeneration (Week 2)

4. **Template System (Quick Win)**
   - Create `template_matcher.py` with common modifications
   - Implement template transformations (brighter, darker, nighttime, etc.)
   - Test template matching and transformation

5. **Clip Regenerator Module**
   - Create module structure
   - Implement `data_loader.py` (load from job_stages)
   - Implement `template_matcher.py` (check templates before LLM)
   - Implement `llm_modifier.py` (LLM prompt modification)
   - Implement `context_builder.py` (build LLM context with last 2-3 messages)
   - Implement `process.py` orchestration

6. **Regeneration API**
   - Create `POST /api/v1/jobs/{job_id}/clips/{clip_index}/regenerate` endpoint
   - Integrate with Clip Regenerator module
   - Add SSE events for progress
   - Update job status: `completed` → `regenerating` → `completed`

7. **ClipChatbot UI**
   - Create `ClipChatbot.tsx` component
   - Implement chat interface
   - Add cost estimation display (with template discount)
   - Add progress tracking
   - Show job status updates

### Phase 3: Integration & Testing (Week 3)

7. **Recomposition Integration**
   - Update Composer to handle regenerated clips
   - Replace clip in `Clips` object
   - Test full recomposition flow

8. **End-to-End Testing**
   - Test complete flow: select → chat → regenerate → recompose
   - Test error scenarios
   - Test cost tracking
   - Test concurrent regenerations

9. **UI Polish**
   - Add loading states
   - Add error handling
   - Add success animations
   - Responsive design testing

---

## Success Criteria

### Functional

- ✅ Users can view all clips with thumbnails and lyrics
- ✅ Users can select a clip and open chatbot
- ✅ Users can enter natural language instructions
- ✅ System regenerates selected clip correctly
- ✅ System recomposes video with updated clip
- ✅ Users see updated video within 5-10 minutes

### Quality

- ✅ Regenerated clips maintain style consistency
- ✅ Conversational interface feels natural
- ✅ Error handling is graceful
- ✅ Cost estimates are accurate (±20%)

### Performance

- ✅ Clip list loads in <500ms
- ✅ Regeneration completes in 2-3 minutes
- ✅ UI remains responsive during regeneration

### User Experience

- ✅ Intuitive clip selection
- ✅ Clear cost transparency
- ✅ Helpful error messages
- ✅ Smooth regeneration flow

---

## Open Questions & Decisions

### Q1: Should regenerations create a new job or update existing?

**Analysis:**
- **Option A: Update existing job**
  - Pros: Simpler, keeps history together, same job_id
  - Cons: Original video URL replaced, can't compare versions
- **Option B: Create new job**
  - Pros: Preserves original, can compare versions, clear history
  - Cons: More complex, separate job_id, harder to track

**Recommendation:** **Option A (Update existing job)** for MVP
- Simpler implementation
- Keeps all work on one job
- Can add versioning later if needed
- Original clips still in storage (can restore if needed)

### Q2: Can users regenerate multiple clips simultaneously?

**Analysis:**
- **Option A: One at a time**
  - Pros: Simpler, avoids conflicts, easier error handling
  - Cons: Slower for multiple changes
- **Option B: Multiple simultaneously**
  - Pros: Faster, better UX for bulk changes
  - Cons: Complex state management, potential conflicts

**Recommendation:** **Option A (One at a time)** for MVP
- Simpler to implement and test
- Avoids state conflicts
- Can add batch regeneration in post-MVP

### Q3: What happens if regeneration fails?

**Analysis:**
- **Option A: Keep original, show error**
  - Pros: Safe, no data loss, clear failure state
  - Cons: User needs to retry manually
- **Option B: Auto-retry with backoff**
  - Pros: Better UX, handles transient failures
  - Cons: May delay user feedback, more complex

**Recommendation:** **Option A (Keep original, show error)** for MVP
- Clear failure state
- User can retry with different instruction
- Can add auto-retry in post-MVP

### Q4: Should there be a limit on regenerations per clip?

**Analysis:**
- **Option A: No limit**
  - Pros: Maximum flexibility, no artificial constraints
  - Cons: Potential cost abuse, infinite loops
- **Option B: Hard limit (e.g., 10 per clip)**
  - Pros: Prevents abuse, cost control
  - Cons: May frustrate users who need more iterations
- **Option C: Soft limit with warning**
  - Pros: Flexibility with cost awareness
  - Cons: More complex UI

**Recommendation:** **Option C (Soft limit with warning)** for MVP
- Show warning after 3 regenerations: "This clip has been regenerated 3 times. Consider starting fresh if results aren't satisfactory."
- No hard limit (cost already controlled by budget)
- Helps users make informed decisions

### Q5: How to handle style consistency across regenerations?

**Analysis:**
- **Option A: Pass full context to LLM**
  - Pros: Best quality, maintains consistency
  - Cons: More tokens, higher cost
- **Option B: Pass minimal context**
  - Pros: Lower cost, faster
  - Cons: May lose consistency

**Recommendation:** **Option A (Pass full context)** for MVP
- Quality is priority
- Cost difference is minimal (~$0.01-0.02)
- Better user experience

---

## Testing Strategy

### Unit Tests

- Clip Regenerator module functions
- LLM prompt modification logic
- Context building logic
- Thumbnail generation

### Integration Tests

- API endpoints
- Regeneration flow (end-to-end)
- Recomposition with regenerated clip
- Error handling scenarios

### E2E Tests

- Complete user flow: select → chat → regenerate → view
- Multiple regenerations on same clip
- Error recovery
- Cost tracking accuracy

---

## Dependencies

### External Services

- OpenAI GPT-4o or Claude 3.5 Sonnet (for prompt modification)
- Replicate (for video generation, reused)
- Supabase Storage (for thumbnails and clips)
- FFmpeg (for thumbnail extraction)

### Internal Modules

- Video Generator (reused for single clip generation)
- Composer (reused for recomposition)
- Prompt Generator (context extraction)
- Scene Planner (scene plan data)

---

## Risks & Mitigations

### Risk 1: Style Inconsistency

**Risk:** Regenerated clip doesn't match rest of video  
**Mitigation:** Pass full context (scene plan, style, characters) to LLM

### Risk 2: High Costs

**Risk:** Users regenerate many times, exceeding budget  
**Mitigation:** Cost tracking, budget enforcement, warnings after 3 regenerations

### Risk 3: Poor LLM Modifications

**Risk:** LLM doesn't understand instructions correctly  
**Mitigation:** Clear system prompt, conversation history, retry logic

### Risk 4: Performance Issues

**Risk:** Regeneration takes too long  
**Mitigation:** Optimize recomposition, show progress, set expectations

---

## Future Enhancements (Post-MVP)

See `PRD_clip_chatbot_post_mvp.md` for:
- Batch regeneration
- Clip versioning/history
- Advanced style transfer
- Prompt suggestions
- Clip templates
- Multi-clip instructions

---

## Appendix

### A. Example Conversations

**Example 1: Simple Instruction**
```
User: "make it nighttime"
AI: "I'll modify the prompt to make this clip nighttime. Estimated cost: $0.15"
[Regenerating...]
AI: "Done! The clip is now set at night. Check the updated video."
```

**Example 2: Iterative Refinement**
```
User: "make it brighter"
AI: "I'll brighten the clip. Estimated cost: $0.15"
[Regenerating...]
AI: "Done! The clip is brighter now."
User: "add more motion"
AI: "I'll add more motion to the clip. Estimated cost: $0.15"
[Regenerating...]
AI: "Done! The clip now has more motion."
```

### B. Cost Breakdown Example

```
Initial Video Generation: $1.50
Clip 2 Regeneration #1: $0.15
Clip 2 Regeneration #2: $0.15
Clip 4 Regeneration #1: $0.15
Total: $1.95
```

### C. API Response Examples

See sections 5.1 and 5.2 for detailed API specifications.

