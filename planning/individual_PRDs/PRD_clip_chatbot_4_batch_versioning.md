# Clip Chatbot Feature - Part 4: Batch Operations & Versioning

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** Post-MVP - Part 1 of 3  
**Dependencies:** 
- MVP Clip Chatbot Feature complete ✅
- `PRD_clip_chatbot_1_foundation.md` - Part 1 complete
- `PRD_clip_chatbot_2_regeneration.md` - Part 2 complete
- `PRD_clip_chatbot_3_integration.md` - Part 3 complete

**Related Documents:**
- `PRD_clip_chatbot_5_style_intelligence.md` - Part 5: Style Transfer & Multi-Clip
- `PRD_clip_chatbot_6_comparison_analytics.md` - Part 6: Comparison & Analytics

---

## Executive Summary

This PRD defines Part 4 of the post-MVP clip chatbot enhancements: batch clip regeneration (sequential processing) and clip versioning with history. This part enables users to regenerate multiple clips efficiently and maintain version history for rollback capabilities.

**Key Features:**
- Batch clip regeneration (sequential processing for MVP+)
- Multi-select UI for clip selection
- Clip versioning and history (3 versions per clip)
- Version restore functionality
- Storage cost management

**Timeline:** Weeks 1-2  
**Success Criteria:** Users can regenerate multiple clips and restore previous versions

---

## Objectives

1. **Batch Operations:** Regenerate multiple clips with single or per-clip instructions
2. **Version Control:** Track and restore previous clip versions
3. **Storage Management:** Manage storage costs with archiving and compression
4. **Efficiency:** Enable bulk changes without individual regenerations

---

## User Stories

**US-1: Batch Regeneration**
- As a user, I want to select multiple clips and regenerate them all with one instruction, so I can make bulk changes efficiently.

**US-2: Version History**
- As a user, I want to see previous versions of a clip and restore them, so I can revert if a regeneration doesn't work out.

**US-3: Per-Clip Instructions**
- As a user, I want to provide different instructions for each selected clip, so I can customize bulk changes.

---

## System Architecture

### Batch Regeneration Flow

```
User selects multiple clips
    ↓
User enters instruction(s)
    ↓
Batch API endpoint
    ↓
Sequential Processing (one at a time)
    ├─ Clip 1: Regenerate
    ├─ Clip 2: Regenerate
    └─ Clip 3: Regenerate
    ↓
Recompose video (once, after all clips)
    ↓
Updated video
```

### Versioning Flow

```
Clip Regeneration
    ↓
Store current version as "previous"
    ↓
Store new version as "current"
    ↓
Archive old versions (>7 days)
    ↓
Version History UI
```

---

## Detailed Requirements

### 1. Batch Regeneration

#### 1.1 Overview

Allow users to select multiple clips and regenerate them all with a single instruction or per-clip instructions. Uses sequential processing for MVP+ (simpler, safer than parallel).

#### 1.2 User Interface

**Multi-Select Mode:**
- Checkbox selection for clips in ClipSelector
- "Select All" / "Deselect All" buttons
- Selected count indicator
- Batch instruction input (single instruction for all, or per-clip)

**Design:**
```
┌─────────────────────────────────────────┐
│  Select Multiple Clips (3 selected)     │
├─────────────────────────────────────────┤
│  ☑ Clip 1  ☑ Clip 2  ☐ Clip 3         │
│  ☑ Clip 4  ☐ Clip 5  ☐ Clip 6         │
│                                         │
│  Instruction for all clips:            │
│  ┌───────────────────────────────────┐ │
│  │ "make them all brighter"          │ │
│  └───────────────────────────────────┘ │
│                                         │
│  OR per-clip instructions:              │
│  Clip 1: "make it nighttime"           │
│  Clip 2: "add more motion"             │
│  Clip 4: "warmer colors"               │
│                                         │
│  [Regenerate All] [Cancel]             │
└─────────────────────────────────────────┘
```

#### 1.3 Backend Implementation

**API Endpoint:**
```
POST /api/v1/jobs/{job_id}/clips/batch-regenerate
```

**Request:**
```json
{
  "clips": [
    {
      "clip_index": 0,
      "instruction": "make it nighttime"
    },
    {
      "clip_index": 2,
      "instruction": "add more motion"
    },
    {
      "clip_index": 4,
      "instruction": "warmer colors"
    }
  ]
}
```

**Response:**
```json
{
  "batch_id": "uuid",
  "regenerations": [
    {
      "clip_index": 0,
      "regeneration_id": "uuid",
      "status": "queued"
    },
    ...
  ],
  "estimated_total_cost": 0.405,
  "estimated_total_time": 600
}
```

#### 1.4 Processing Strategy

**Sequential Processing (MVP+):**
- Regenerate clips one at a time (simpler, safer)
- Progress tracking per clip
- Partial success handling (some clips succeed, some fail)
- Single recomposition after all clips complete

**Implementation:**
```python
async def batch_regenerate_clips(
    job_id: UUID,
    clip_instructions: List[ClipInstruction]
) -> BatchRegenerationResult:
    """
    Regenerate multiple clips sequentially.
    
    Returns result with per-clip status.
    """
    results = []
    
    for clip_instruction in clip_instructions:
        try:
            result = await regenerate_clip(
                job_id=job_id,
                clip_index=clip_instruction.clip_index,
                user_instruction=clip_instruction.instruction
            )
            results.append(result)
        except Exception as e:
            results.append(RegenerationResult(
                clip_index=clip_instruction.clip_index,
                status="failed",
                error=str(e)
            ))
    
    # Recompose once after all clips
    if any(r.status == "success" for r in results):
        await recompose_video(job_id)
    
    return BatchRegenerationResult(results=results)
```

#### 1.5 Cost Optimization

**Batch Discount:**
- 10% off if regenerating 3+ clips
- Calculation:
  1. Calculate individual estimated costs per clip (accounting for different durations)
  2. Sum all individual costs: `sum(individual_costs)`
  3. Apply discount if `num_clips >= 3`: `total_cost = sum(individual_costs) * 0.9`
- Example: 
  - Clip 1 (12s): $0.15
  - Clip 2 (15s): $0.18
  - Clip 3 (10s): $0.12
  - Sum: $0.45
  - With discount (3 clips): $0.405

**Cost Breakdown:**
- Show per-clip cost (with duration)
- Show subtotal (sum of individual costs)
- Show batch discount (if applicable, 10% off)
- Show total cost (after discount)

---

### 2. Clip Versioning & History

#### 2.1 Overview

Track all versions of a clip and allow users to view, compare, and restore previous versions. Limit to 3 versions per clip for MVP+ to manage storage costs.

#### 2.2 Database Schema

**clip_versions:**
```sql
CREATE TABLE clip_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  version_number INTEGER NOT NULL,
  video_url TEXT NOT NULL,
  prompt TEXT NOT NULL,
  thumbnail_url TEXT,
  user_instruction TEXT,
  cost DECIMAL(10, 4) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_current BOOLEAN DEFAULT FALSE,
  UNIQUE(job_id, clip_index, version_number)
);

CREATE INDEX idx_clip_versions_job_clip ON clip_versions(job_id, clip_index);
CREATE INDEX idx_clip_versions_current ON clip_versions(job_id, clip_index, is_current) WHERE is_current = TRUE;
```

#### 2.3 Version Management

**Version Creation:**
```python
async def create_clip_version(
    job_id: UUID,
    clip_index: int,
    clip: Clip,
    user_instruction: str
) -> ClipVersion:
    """
    Create new version of clip.
    
    Marks previous version as not current.
    Limits to 3 versions per clip (archive oldest if needed).
    """
    # Get current version number
    current_version = await get_current_version(job_id, clip_index)
    new_version_number = (current_version.version_number + 1) if current_version else 1
    
    # Check version limit (3 versions)
    versions = await get_all_versions(job_id, clip_index)
    if len(versions) >= 3:
        # Archive oldest version (not current) to cold storage
        # Don't archive the current version
        non_current_versions = [v for v in versions if not v.is_current]
        if non_current_versions:
            oldest = min(non_current_versions, key=lambda v: v.created_at)
            await archive_version(oldest.id)
        else:
            # All versions are current (shouldn't happen, but handle gracefully)
            oldest = min(versions, key=lambda v: v.created_at)
            await archive_version(oldest.id)
    
    # Mark previous as not current
    if current_version:
        await update_version(current_version.id, is_current=False)
    
    # Create new version
    new_version = await db_client.table("clip_versions").insert({
        "job_id": job_id,
        "clip_index": clip_index,
        "version_number": new_version_number,
        "video_url": clip.video_url,
        "prompt": clip.prompt,
        "thumbnail_url": await get_thumbnail_url(job_id, clip_index),
        "user_instruction": user_instruction,
        "cost": clip.cost,
        "is_current": True
    }).execute()
    
    return new_version
```

#### 2.4 Storage Strategy

**Storage Cost Analysis:**
- Average clip size: ~5-10 MB
- 3 versions × 6 clips = 18 video files per job
- 100 jobs = 1,800 files = ~9-18 GB storage
- **Cost:** ~$0.20-0.40/month per 100 jobs (Supabase storage pricing)

**Storage Management:**
- Keep last 3 versions per clip (MVP+), expand to 5 later
- **Version Limit Enforcement:**
  - When creating version 4, archive oldest non-current version
  - Never archive the current version
  - Archive to cold storage (compressed, reduced cost)
- Archive versions older than 7 days to cold storage (reduce active storage by 70%)
- Compress old versions (reduce file size by 30-50%)
- Delete versions older than 30 days (configurable)

**Storage Monitoring:**
- Track storage usage per job/user
- Alert if approaching limits (e.g., >100GB per user)
- Dashboard for storage costs (admin view)
- Automatic cleanup of orphaned versions (job deleted but versions remain)

**Archiving Process:**
```python
async def archive_old_versions():
    """
    Archive versions older than 7 days to cold storage.
    
    Runs as background job (daily).
    """
    old_versions = await get_versions_older_than(days=7)
    
    for version in old_versions:
        # Compress video
        compressed_url = await compress_and_upload_to_cold_storage(version.video_url)
        
        # Update version record
        await update_version(version.id, {
            "archived_url": compressed_url,
            "archived_at": now()
        })
        
        # Delete from active storage
        await delete_from_active_storage(version.video_url)
```

#### 2.5 User Interface

**Version History Panel:**
```
┌─────────────────────────────────────────┐
│  Clip 2 - Version History               │
├─────────────────────────────────────────┤
│  Version 3 (Current) ✓                   │
│  "make it nighttime" - $0.15            │
│  [Thumbnail]                            │
│                                         │
│  Version 2                              │
│  "add more motion" - $0.15              │
│  [Thumbnail] [Restore] [Compare]        │
│                                         │
│  Version 1 (Original)                   │
│  Original generation - $0.12            │
│  [Thumbnail] [Restore] [Compare]        │
└─────────────────────────────────────────┘
```

**Features:**
- Visual timeline of versions
- Thumbnail for each version
- Cost per version
- Instruction that created version
- Restore button (replaces current version, triggers recomposition)
- Compare button (side-by-side view - Part 6)

---

### 3. API Endpoints

#### 3.1 Batch Regeneration

**POST /api/v1/jobs/{job_id}/clips/batch-regenerate**

**Request:**
```json
{
  "clips": [
    {"clip_index": 0, "instruction": "make it nighttime"},
    {"clip_index": 2, "instruction": "add more motion"}
  ]
}
```

**Response:**
```json
{
  "batch_id": "uuid",
  "regenerations": [
    {
      "clip_index": 0,
      "regeneration_id": "uuid",
      "status": "queued"
    },
    {
      "clip_index": 2,
      "regeneration_id": "uuid",
      "status": "queued"
    }
  ],
  "estimated_total_cost": 0.405,
  "estimated_total_time": 600
}
```

**SSE Events:**
- `batch_started` - Batch regeneration queued
- `clip_regenerating` - Individual clip regenerating (with clip_index)
- `clip_complete` - Individual clip complete
- `batch_complete` - All clips complete, recomposition starting
- `batch_failed` - Batch failed (with per-clip status)

#### 3.2 Version History

**GET /api/v1/jobs/{job_id}/clips/{clip_index}/versions**
- Returns all versions for a clip (ordered by version_number desc)

**POST /api/v1/jobs/{job_id}/clips/{clip_index}/versions/{version_id}/restore**
- Restores a previous version (becomes current)
- Triggers recomposition
- Returns updated video URL

**GET /api/v1/jobs/{job_id}/clips/{clip_index}/versions/compare**
- Returns comparison data (thumbnails, prompts, metadata)
- Used by comparison UI (Part 6)

---

## Implementation Tasks

### Task 1: Batch Regeneration Backend
- [ ] Create batch regeneration endpoint
- [ ] Implement sequential processing
- [ ] Add progress tracking per clip
- [ ] Add partial success handling
- [ ] Add batch discount calculation
- [ ] Add SSE events for batch progress

### Task 2: Multi-Select UI
- [ ] Add checkbox selection to ClipSelector
- [ ] Add "Select All" / "Deselect All" buttons
- [ ] Add batch instruction input
- [ ] Add per-clip instruction input (optional)
- [ ] Add batch regeneration button
- [ ] Add batch progress display

### Task 3: Version Management
- [ ] Create clip_versions table migration
- [ ] Implement version creation logic
- [ ] Implement version limit enforcement (3 versions)
- [ ] Implement version restore
- [ ] Add version history API endpoints

### Task 4: Storage Management
- [ ] Implement version limit enforcement (archive oldest when limit reached)
- [ ] Implement version archiving (7 days)
- [ ] Implement compression for old versions
- [ ] Create background job for archiving
- [ ] Add storage cost monitoring (per job/user)
- [ ] Add storage budget limits and alerts
- [ ] Add cleanup job for orphaned versions

### Task 5: Version History UI
- [ ] Create VersionHistory component
- [ ] Display version timeline
- [ ] Add restore functionality
- [ ] Add compare button (placeholder for Part 6)
- [ ] Test version restore flow

---

## Testing Strategy

### Unit Tests
- Batch processing logic
- Version creation and management
- Version limit enforcement
- Storage archiving logic

### Integration Tests
- Batch regeneration API
- Version restore API
- Sequential processing flow
- Partial success handling

### E2E Tests
- Complete batch regeneration flow
- Version restore flow
- Multiple batch operations
- Storage management

---

## Success Criteria

### Functional
- ✅ Users can select multiple clips and regenerate them
- ✅ Users can view version history for clips
- ✅ Users can restore previous versions
- ✅ Batch operations complete successfully

### Performance
- ✅ Batch regeneration: 5-8 minutes for 3 clips (sequential)
- ✅ Version history: <500ms load time
- ✅ Storage costs managed (archiving working)

### Quality
- ✅ Partial success handled gracefully
- ✅ Version restore works correctly
- ✅ Storage costs within budget

---

## Dependencies

### Internal Modules
- Clip Regenerator (from MVP)
- Composer (recomposition)
- Data Loader (from Part 1)

### External Services
- Supabase Storage (version storage)
- Supabase PostgreSQL (version metadata)

---

## Risks & Mitigations

### Risk 1: Storage Cost Explosion
**Risk:** Versioning increases storage costs significantly  
**Mitigation:** Limit to 3 versions, archive after 7 days, compress old versions

### Risk 2: Batch Processing Complexity
**Risk:** Sequential processing too slow for many clips  
**Mitigation:** Start with sequential, add parallel processing later if needed

### Risk 3: Version Limit Frustration
**Risk:** Users frustrated by 3-version limit  
**Mitigation:** Clear messaging, expand to 5 versions if needed

---

## Next Steps

After completing Part 4, proceed to:
- **Part 5:** Style Transfer & Multi-Clip Intelligence
- **Part 6:** Comparison Tools & Analytics

