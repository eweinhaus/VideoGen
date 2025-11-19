# Clip Chatbot Feature - Part 6: Comparison Tools & Analytics

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** Post-MVP - Part 3 of 3  
**Dependencies:** 
- Part 5: Style Transfer & Multi-Clip Intelligence ✅
- `PRD_clip_chatbot_5_style_intelligence.md` - Part 5 complete

**Related Documents:**
- `PRD_clip_chatbot_4_batch_versioning.md` - Part 4: Batch & Versioning
- `PRD_clip_chatbot_5_style_intelligence.md` - Part 5: Style & Intelligence

---

## Executive Summary

This PRD defines Part 6 of the post-MVP clip chatbot enhancements: comparison tools for before/after visualization and regeneration analytics. This part enables users to evaluate changes and understand their usage patterns.

**Key Features:**
- Side-by-side comparison mode
- Regeneration analytics dashboard
- Usage insights and patterns
- Performance metrics

**Timeline:** Weeks 5-6  
**Success Criteria:** Users can compare clip versions and view regeneration analytics

---

## Objectives

1. **Comparison Tools:** Visualize differences between clip versions
2. **Analytics:** Track regeneration patterns and success rates
3. **Insights:** Provide actionable usage insights
4. **Metrics:** Display performance and cost metrics

---

## User Stories

**US-1: Version Comparison**
- As a user, I want to see side-by-side comparison of original and regenerated clips, so I can evaluate changes easily.

**US-2: Regeneration Analytics**
- As a user, I want to see statistics about my regenerations (success rate, average cost, most common modifications), so I can understand my usage patterns.

---

## System Architecture

### Comparison Flow

```
User clicks "Compare" on version
    ↓
Load original and regenerated clips
    ↓
Display side-by-side
    ↓
Synchronized playback
```

### Analytics Flow

```
Regeneration events
    ↓
Store in regeneration_analytics table
    ↓
Aggregate metrics
    ↓
Display in analytics dashboard
```

---

## Detailed Requirements

### 1. Comparison Tools

#### 1.1 Overview

Enhanced before/after comparison with side-by-side mode for MVP+. Future enhancements include split screen, fade transition, and difference highlight.

#### 1.2 Comparison Modes

**MVP+ (Phase 1):**
- **Side-by-Side:** Original on left, regenerated on right
  - Synchronized playback
  - Toggle between versions
  - **Start with this mode only** (simpler implementation)

**Future Enhancements (Phase 2+):**
- **Split Screen:** Split at midpoint, drag to adjust
- **Fade Transition:** Fade between versions with speed control
- **Difference Highlight:** Highlight changed areas (requires ML analysis)

#### 1.3 Implementation

**Component:**
```typescript
<ClipComparison
  originalClip={originalClip}
  regeneratedClip={regeneratedClip}
  mode="side-by-side"
  syncPlayback={true}
/>
```

**Features:**
- Two video players side-by-side
- Synchronized play/pause (syncs to shorter duration if different)
- Toggle between versions (swap left/right)
- Timestamp display
- Duration mismatch indicator (if clips have different durations)
- Independent playback controls (optional, for different durations)
- Thumbnail preview while videos load
- Fullscreen mode

**Duration Handling:**
- If clips have different durations, sync to shorter duration
- Show warning: "Duration mismatch: 12s vs 15s"
- Allow independent playback if user prefers
- Option to loop shorter clip

#### 1.4 API Endpoint

**GET /api/v1/jobs/{job_id}/clips/{clip_index}/versions/compare**
- Returns comparison data (thumbnails, prompts, metadata)
- **Validation:** Checks both versions exist before comparison
- **Graceful Degradation:** Returns thumbnail-only comparison if video missing
- Error: 404 if one or both versions not found

---

### 2. Regeneration Analytics

#### 2.1 Overview

Track and display statistics about clip regenerations to help users understand usage patterns and optimize their workflow.

#### 2.2 Metrics Tracked

**Per Job:**
- Total regenerations
- Success rate
- Average cost per regeneration
- Most common modifications
- Average time per regeneration

**Per User:**
- Total regenerations across all jobs
- Most used templates
- Success rate
- Cost efficiency

**System-Wide:**
- Most common instructions
- Most effective templates
- Average iterations per clip
- Cost trends

#### 2.3 Database Schema

**regeneration_analytics:**
```sql
CREATE TABLE regeneration_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  clip_index INTEGER NOT NULL,
  instruction TEXT NOT NULL,
  template_id TEXT,
  cost DECIMAL(10, 4) NOT NULL,
  success BOOLEAN NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_regeneration_analytics_user ON regeneration_analytics(user_id);
CREATE INDEX idx_regeneration_analytics_job ON regeneration_analytics(job_id);
CREATE INDEX idx_regeneration_analytics_instruction ON regeneration_analytics(instruction);
CREATE INDEX idx_regeneration_analytics_created ON regeneration_analytics(created_at DESC);
```

**Data Retention:**
- Retain analytics for 90 days (configurable)
- Archive older data to `regeneration_analytics_archive` table
- Daily cleanup job removes data older than 90 days
- Users can request deletion of their analytics data (GDPR compliance)

#### 2.4 Analytics Collection

**Data Collection:**
```python
async def track_regeneration(
    job_id: UUID,
    user_id: UUID,
    clip_index: int,
    instruction: str,
    template_id: Optional[str],
    cost: Decimal,
    success: bool
) -> None:
    """
    Track regeneration event for analytics.
    """
    await db_client.table("regeneration_analytics").insert({
        "job_id": job_id,
        "user_id": user_id,
        "clip_index": clip_index,
        "instruction": instruction,
        "template_id": template_id,
        "cost": cost,
        "success": success
    }).execute()
```

#### 2.5 Analytics Dashboard

**UI Component:**
```
┌─────────────────────────────────────────┐
│  Regeneration Analytics                  │
├─────────────────────────────────────────┤
│  This Job:                              │
│  • Total Regenerations: 8                │
│  • Success Rate: 87.5%                  │
│  • Average Cost: $0.14                   │
│  • Most Common: "make it brighter"      │
│                                         │
│  Your Usage:                            │
│  • Total Regenerations: 45               │
│  • Most Used Template: "Nighttime"      │
│  • Average Iterations: 2.3 per clip     │
│                                         │
│  Insights:                               │
│  💡 "You regenerate clips an average of │
│     2.3 times - consider using templates│
│     for faster results"                 │
└─────────────────────────────────────────┘
```

#### 2.6 API Endpoints

**GET /api/v1/jobs/{job_id}/analytics**
- Get regeneration analytics for a job
- **Aggregation Strategy:**
  - Real-time for last 7 days (fast queries)
  - Cached batch aggregation for older data (1 hour cache)
  - Materialized view for system-wide analytics

**GET /api/v1/users/{user_id}/analytics**
- Get user-wide analytics
- Includes cost tracking per user
- Shows budget usage if budget limits enabled

**GET /api/v1/jobs/{job_id}/analytics/export**
- Export analytics as CSV
- Includes: regenerations, costs, success rates, timestamps
- Useful for users tracking their usage

---

## Implementation Tasks

### Task 1: Comparison Tools
- [ ] Create ClipComparison component
- [ ] Implement side-by-side mode
- [ ] Add synchronized playback (handle different durations)
- [ ] Add duration mismatch handling
- [ ] Add thumbnail preview while videos load
- [ ] Add validation for missing versions
- [ ] Add graceful degradation (thumbnail-only if video missing)
- [ ] Add toggle functionality
- [ ] Test with real clips (including different durations)

### Task 2: Analytics Collection
- [ ] Create regeneration_analytics table
- [ ] Implement tracking function
- [ ] Integrate tracking into regeneration flow
- [ ] Add data retention policy (90 days)
- [ ] Create archive table and cleanup job
- [ ] Add data collection tests

### Task 3: Analytics Dashboard
- [ ] Create AnalyticsDashboard component
- [ ] Implement metric calculations
- [ ] Add charts/visualizations
- [ ] Add insights generation
- [ ] Test with real data

### Task 4: Analytics API
- [ ] Create analytics endpoints
- [ ] Implement hybrid aggregation (real-time + batch)
- [ ] Add materialized view for system-wide analytics
- [ ] Add caching for performance (1 hour cache)
- [ ] Add export functionality (CSV)
- [ ] Add cost tracking per user
- [ ] Add API tests

---

## Testing Strategy

### Unit Tests
- Comparison component logic
- Analytics aggregation
- Metric calculations

### Integration Tests
- Comparison API
- Analytics API
- Data collection

### E2E Tests
- Complete comparison flow
- Analytics dashboard display

---

## Success Criteria

### Functional
- ✅ Users can compare clip versions side-by-side
- ✅ Users can view regeneration analytics
- ✅ Analytics data accurate and up-to-date

### Performance
- ✅ Comparison: <1s load time
- ✅ Analytics dashboard: <500ms load time

### Quality
- ✅ Comparison synchronized correctly
- ✅ Analytics insights helpful and actionable

---

## Dependencies

### Internal Modules
- Clip Regenerator (from MVP)
- Version Management (from Part 4)

### External Services
- Supabase PostgreSQL (analytics storage)

---

## Risks & Mitigations

### Risk 1: Comparison Performance
**Risk:** Side-by-side playback performance issues  
**Mitigation:** Optimize video loading, use thumbnails for preview

### Risk 2: Analytics Data Volume
**Risk:** Analytics table grows large  
**Mitigation:** Archive old data, add indexes, optimize queries

---

## Next Steps

After completing Part 6, all post-MVP enhancements are complete. Consider:
- Advanced comparison modes (split screen, fade, difference highlight)
- ML-based style analysis
- Parallel batch processing
- Template marketplace

