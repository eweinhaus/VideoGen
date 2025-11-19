# Clip Chatbot Feature - Part 3: Integration & Polish

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** MVP - Part 3 of 3  
**Dependencies:** 
- Part 1: Foundation & Data Infrastructure ✅
- Part 2: Regeneration Core ✅
- `PRD_clip_chatbot_1_foundation.md` - Part 1 complete
- `PRD_clip_chatbot_2_regeneration.md` - Part 2 complete

**Related Documents:**
- `PRD_clip_chatbot_1_foundation.md` - Part 1: Foundation
- `PRD_clip_chatbot_2_regeneration.md` - Part 2: Regeneration Core

---

## Executive Summary

This PRD defines Part 3 of the MVP clip chatbot feature: integration with the Composer module for full video recomposition, job status management, comprehensive error handling, and end-to-end testing. This part completes the MVP by ensuring regenerated clips are properly integrated into the final video.

**Key Deliverables:**
- Composer integration (full recomposition with regenerated clip)
- Job status state machine
- Error handling and recovery
- End-to-end testing
- UI polish and optimization

**Timeline:** Week 3  
**Success Criteria:** Users can regenerate clips and receive updated final video

---

## Objectives

1. **Composer Integration:** Recompose full video with regenerated clip
2. **Status Management:** Handle job status transitions during regeneration
3. **Error Recovery:** Graceful error handling with retry capabilities
4. **Testing:** Comprehensive E2E testing of complete flow
5. **Polish:** UI improvements and performance optimization

---

## User Stories

**US-1: Full Video Update**
- As a user, I want to see the updated final video after regenerating a clip, so I can verify the changes.

**US-2: Error Recovery**
- As a user, I want to retry regeneration if it fails, so I don't lose my work.

**US-3: Status Visibility**
- As a user, I want to see the current status of regeneration, so I know what's happening.

---

## System Architecture

### Full Recomposition Flow

```
Regenerated Clip (from Part 2)
    ↓
Replace clip in Clips object
    ↓
Composer Module (full recomposition)
    ↓
Re-download all clips
    ↓
Re-normalize all clips
    ↓
Re-apply transitions
    ↓
Re-sync audio
    ↓
Re-encode final video
    ↓
Upload new final video
    ↓
Update job status
    ↓
User sees updated video
```

### Component Integration

```
Clip Regenerator (Part 2)
    ↓
[Replace clip in Clips object]
    ↓
Composer Module (existing)
    ↓
[Full recomposition]
    ↓
Updated VideoOutput
    ↓
Job Status Update
```

---

## Detailed Requirements

### 1. Composer Integration

#### 1.1 Overview

After regenerating a clip, we need to recompose the entire video with the new clip. The Composer module expects a complete `Clips` object, so we must reconstruct it with the regenerated clip.

#### 1.2 Process

**Location:** `modules/clip_regenerator/process.py` (extend from Part 2)

```python
async def regenerate_clip_with_recomposition(
    job_id: UUID,
    clip_index: int,
    user_instruction: str,
    conversation_history: List[Dict[str, str]] = None
) -> RegenerationResult:
    """
    Regenerate clip and recompose full video.
    
    Steps:
    1-5: Same as Part 2 (regenerate clip)
    6. Replace clip in Clips object
    7. Recompose video (full recomposition)
    8. Update job status
    """
    # Steps 1-5: Regenerate clip (from Part 2)
    regeneration_result = await regenerate_clip(...)
    new_clip = regeneration_result.clip
    
    # Step 6: Replace clip in Clips object
    clips = await load_clips_from_job_stages(job_id)
    clips.clips[clip_index] = new_clip
    
    # Update Clips metadata
    clips.successful_clips = len([c for c in clips.clips if c.status == "success"])
    clips.total_cost += regeneration_result.cost
    
    # Step 7: Recompose video (full recomposition)
    audio_url = await get_audio_url(job_id)
    transitions = await load_transitions(job_id)
    beat_timestamps = await load_beat_timestamps(job_id)
    aspect_ratio = await get_aspect_ratio(job_id)
    
    video_output = await composer.process(
        job_id=str(job_id),
        clips=clips,
        audio_url=audio_url,
        transitions=transitions,
        beat_timestamps=beat_timestamps,
        aspect_ratio=aspect_ratio
    )
    
    # Step 8: Update job status
    await update_job_status(job_id, "completed", video_output.video_url)
    
    return RegenerationResult(
        clip=new_clip,
        video_output=video_output,
        modified_prompt=regeneration_result.modified_prompt,
        cost=regeneration_result.cost
    )
```

#### 1.3 Full Recomposition Details

**What "Full Recomposition" Means:**
1. Re-download all clips from Supabase Storage (including regenerated one)
2. Re-normalize all clips to 1080p, 30 FPS
3. Re-apply transitions (recreate concat file)
4. Re-sync audio with video
5. Re-encode final video (H.264/AAC)
6. Upload new final video to Supabase Storage

**Why Full Recomposition:**
- Ensures all clips are properly synchronized
- Maintains audio sync accuracy
- Applies any transitions correctly
- Guarantees consistent output quality

**Performance:**
- Recomposition time: 60-120s (may be slightly slower than initial composition due to cache misses)
- No API costs (compute only)
- Document in UI: "Recomposition will take 1-2 minutes"
- **Note:** Recomposition may take longer if:
  - Clips need to be re-downloaded (cache miss)
  - Multiple clips were regenerated
  - System is under load

---

### 2. Job Status Management

#### 2.1 Status State Machine

```
completed (original video)
    ↓
[User clicks "Regenerate Clip"]
    ↓
regenerating (job status updated, lock acquired)
    ↓
[Template check / LLM modification]
    ↓
[Video generation]
    ↓
[Recomposition]
    ↓
completed (updated video) OR failed (error occurred)
    ↓
[Lock released]
```

**State Machine Diagram:**
```
┌──────────┐
│completed │◄─────────────────┐
└────┬─────┘                   │
     │ User initiates          │
     │ regeneration            │
     ↓                         │
┌──────────────┐              │
│regenerating  │              │
│(locked)      │              │
└────┬─────────┘              │
     │                         │
     ├─ Success ───────────────┘
     │
     └─ Failure
         ↓
     ┌───────┐
     │failed │
     └───┬───┘
         │ User retries
         └───► [back to regenerating]
```

#### 2.2 Status Transitions

**Transitions:**
- `completed` → `regenerating`: User initiates regeneration
  - **Lock:** Acquire database lock on job row
  - **Validation:** Check no concurrent regeneration (409 if locked)
- `regenerating` → `completed`: Regeneration successful
  - **Lock:** Release database lock
  - **Update:** Set new video_url
- `regenerating` → `failed`: Regeneration failed (user can retry)
  - **Lock:** Release database lock
  - **Preserve:** Keep original video_url
- `failed` → `regenerating`: User retries regeneration
  - **Lock:** Acquire database lock again
- `regenerating` → `cancelled`: User cancels regeneration (optional)
  - **Lock:** Release database lock
  - **Restore:** Keep original video_url
  - **Note:** Cancellation may be handled client-side (stop SSE connection)

**Concurrent Regeneration Prevention:**
- Use PostgreSQL `SELECT ... FOR UPDATE` to lock job row
- If lock cannot be acquired (another regeneration in progress): Return 409 Conflict
- Lock released when regeneration completes or fails

**Implementation:**
```python
async def update_job_status(
    job_id: UUID,
    status: str,
    video_url: Optional[str] = None
) -> None:
    """
    Update job status in database.
    
    Also updates video_url if provided.
    """
    update_data = {"status": status}
    if video_url:
        update_data["video_url"] = video_url
    
    await db_client.table("jobs").update(update_data).eq("id", job_id).execute()
```

#### 2.3 Status in UI

**Display:**
- Show current job status in ClipChatbot component
- Update status badge during regeneration
- Show "Regenerating..." indicator
- Update to "Completed" or "Failed" when done

---

### 3. Error Handling

#### 3.1 Failure Scenarios

**LLM Modification Failure:**
- Retry 3 times with exponential backoff
- If all retries fail: Return error, keep original clip
- **Job status:** `regenerating` → `failed`

**Video Generation Failure:**
- Retry 3 times (reuse Video Generator retry logic)
- If fails: Return error, keep original clip, allow retry
- **Job status:** Remains `regenerating` until success or user cancels

**Recomposition Failure:**
- Retry 3 times (reuse Composer retry logic)
- If fails: Return error, keep original video
- **Job status:** `regenerating` → `failed`

**Network/Storage Failures:**
- Retry with exponential backoff
- If persistent: Return error, allow manual retry
- **Job status:** `regenerating` → `failed` (retryable error)

#### 3.2 Error Recovery

**User Actions:**
- Retry button in UI (restart regeneration)
  - Clears previous error state
  - Re-initiates regeneration with same or different instruction
- Cancel button (stop regeneration, restore original)
  - Stops SSE connection
  - Releases database lock
  - Restores original video_url
  - Updates job status back to `completed`
- Error message display (user-friendly)
  - Shows actionable error message
  - Provides retry option
  - Logs technical details for debugging

**System Actions:**
- Keep original clip/video on failure
- Log detailed error for debugging
- Allow retry with same or different instruction

#### 3.3 Error Messages

**User-Friendly Messages:**
- "Regeneration failed. Please try again."
- "Video generation timed out. Please retry."
- "Recomposition failed. Original video preserved."

**Technical Details:**
- Log full error stack trace
- Include error code and context
- Store in `clip_regenerations` table

---

### 4. Cost Tracking

#### 4.1 Cost Calculation

**Components:**
1. LLM call (if no template): ~$0.01-0.02
2. Video generation: ~$0.10-0.15
3. Recomposition: $0.00 (compute only)

**Total:** ~$0.11-0.17 (with template: ~$0.10-0.15)

#### 4.2 Cost Tracking Implementation

**Store in Database:**
```python
await db_client.table("clip_regenerations").insert({
    "job_id": job_id,
    "clip_index": clip_index,
    "original_prompt": original_prompt,
    "modified_prompt": modified_prompt,
    "user_instruction": user_instruction,
    "conversation_history": conversation_history,  # JSONB: [{"role": "user", "content": "..."}, ...]
    "cost": actual_cost,
    "status": "completed",
    "created_at": now()
}).execute()
```

**Database Schema (clip_regenerations table):**
```sql
CREATE TABLE clip_regenerations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  original_prompt TEXT NOT NULL,
  modified_prompt TEXT NOT NULL,
  user_instruction TEXT NOT NULL,
  conversation_history JSONB,  -- Store conversation history
  cost DECIMAL(10, 4) NOT NULL,
  status TEXT NOT NULL,  -- "completed", "failed"
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(job_id, clip_index, created_at)  -- Allow multiple regenerations per clip
);

CREATE INDEX idx_clip_regenerations_job ON clip_regenerations(job_id, clip_index);
```

**Update Job Total:**
```python
await db_client.table("jobs").update({
    "total_cost": current_cost + regeneration_cost
}).eq("id", job_id).execute()
```

#### 4.3 Budget Enforcement

- Check job total cost + estimated regeneration cost
- Warn if approaching budget limit ($2000 production, $50 dev)
- Allow regeneration if under limit
- Track separately for transparency

---

### 5. End-to-End Testing

#### 5.1 Test Scenarios

**Happy Path:**
1. User selects clip
2. User enters instruction ("make it nighttime")
3. Template matches (or LLM modifies prompt)
4. Clip regenerates successfully
5. Video recomposes successfully
6. User sees updated video

**Error Scenarios:**
1. LLM modification fails → Retry → Success
2. Video generation fails → Retry → Success
3. Recomposition fails → Retry → Success
4. All retries fail → Show error, allow retry

**Edge Cases:**
1. Regenerate first clip
2. Regenerate last clip
3. Regenerate middle clip
4. Multiple regenerations on same clip
5. Regenerate after previous regeneration failed

#### 5.2 Test Implementation

**E2E Test Structure:**
```python
async def test_complete_regeneration_flow():
    # 1. Create job and generate video
    job_id = await create_test_job()
    await wait_for_video_completion(job_id)
    
    # 2. Select clip and regenerate
    clip_index = 0
    instruction = "make it nighttime"
    
    # 3. Trigger regeneration
    response = await regenerate_clip(job_id, clip_index, instruction)
    assert response.status == "queued"
    
    # 4. Wait for completion
    await wait_for_regeneration_completion(job_id, clip_index)
    
    # 5. Verify updated video
    job = await get_job(job_id)
    assert job.status == "completed"
    assert job.video_url is not None
```

---

### 6. UI Polish

#### 6.1 Loading States

**ClipSelector:**
- Skeleton loaders while fetching clips
- Placeholder for missing thumbnails
- Loading spinner during selection

**ClipChatbot:**
- Typing indicator when AI is processing
- Progress bar during regeneration
- Smooth transitions between states

#### 6.2 Error States

**Error Display:**
- Inline error messages in chat
- Retry button next to error
- Clear error descriptions

**Error Recovery:**
- "Try again" button
- "Cancel" button (restore original)
- Error details in expandable section

#### 6.3 Success States

**Completion:**
- Success message in chat
- Updated video preview
- "View updated video" button
- Celebration animation (optional)

#### 6.4 Performance Optimization

**Optimizations:**
- Lazy load thumbnails
- Debounce API calls
- Cache clip metadata
- Optimize re-renders

---

## Implementation Tasks

### Task 1: Composer Integration
- [ ] Extend `regenerate_clip()` to include recomposition
- [ ] Implement clip replacement in Clips object
- [ ] Call Composer with updated Clips
- [ ] Handle Composer errors
- [ ] Test recomposition with regenerated clip

### Task 2: Job Status Management
- [ ] Implement status update functions
- [ ] Add status transitions to regeneration flow
- [ ] Update UI to show status changes
- [ ] Test status state machine

### Task 3: Error Handling
- [ ] Add error handling for all failure scenarios
- [ ] Implement retry logic
- [ ] Add error recovery UI
- [ ] Test error scenarios

### Task 4: Cost Tracking
- [ ] Track actual costs in database
- [ ] Update job total cost
- [ ] Display cost breakdown in UI
- [ ] Test cost tracking accuracy

### Task 5: E2E Testing
- [ ] Create E2E test suite
- [ ] Test happy path
- [ ] Test error scenarios
- [ ] Test edge cases

### Task 6: UI Polish
- [ ] Add loading states
- [ ] Add error states
- [ ] Add success states
- [ ] Performance optimization
- [ ] Responsive design testing

---

## Testing Strategy

### Unit Tests
- Clip replacement logic
- Status update functions
- Error handling functions
- Cost tracking functions

### Integration Tests
- Composer integration
- Status state machine
- Error recovery flows
- Cost tracking integration

### E2E Tests
- Complete regeneration flow
- Error scenarios
- Multiple regenerations
- Edge cases

---

## Success Criteria

### Functional
- ✅ Regenerated clips properly integrated into final video
- ✅ Job status updates correctly during regeneration
- ✅ Error handling graceful with retry capability
- ✅ Cost tracking accurate
- ✅ E2E tests passing

### Performance
- ✅ Recomposition completes in 60-90s
- ✅ UI remains responsive during regeneration
- ✅ Status updates in real-time

### Quality
- ✅ Error messages helpful and actionable
- ✅ UI polished and professional
- ✅ No regressions in existing functionality

---

## Dependencies

### Internal Modules
- Composer (recomposition)
- Video Generator (single clip generation)
- Data Loader (from Part 1)
- Regeneration Core (from Part 2)

### External Services
- Supabase Storage (video storage)
- Supabase PostgreSQL (job status updates)

---

## Risks & Mitigations

### Risk 1: Recomposition Performance
**Risk:** Full recomposition takes too long (60-90s)  
**Mitigation:** Show progress, set expectations, optimize Composer if needed

### Risk 2: Status Race Conditions
**Risk:** Multiple regenerations cause status conflicts  
**Mitigation:** One regeneration at a time per job, proper locking

### Risk 3: Cost Tracking Accuracy
**Risk:** Costs not tracked correctly  
**Mitigation:** Comprehensive testing, validation, audit logs

---

## Next Steps

After completing Part 3, MVP is complete. Proceed to:
- **Post-MVP Part 1:** Batch Operations & Versioning
- **Post-MVP Part 2:** Style Transfer & Multi-Clip Intelligence
- **Post-MVP Part 3:** Comparison Tools & Analytics

