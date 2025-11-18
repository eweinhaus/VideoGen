# PRD 5 & 6 Additional Review & Recommendations

**Date:** January 2025  
**Status:** Review Complete

---

## PRD 5 (Style Transfer & Multi-Clip Intelligence) - Issues Found

### 1. Style Transfer Keyword Extraction Fallback

**Issue:** PRD 5 assumes keyword extraction will always work, but some prompts may not contain clear style keywords.

**Example Problem:**
- Source prompt: "A person walking down a street" (no style keywords)
- Target prompt: "A car driving on a highway"
- Result: No style keywords extracted, style transfer fails silently

**Recommendation:**
- Add LLM fallback if keyword extraction finds <2 style keywords
- Use LLM to analyze source clip prompt and extract style elements
- Cost: Additional $0.01-0.02 per style transfer

**Fix Needed:**
```python
def extract_style_keywords(prompt: str) -> StyleKeywords:
    keywords = extract_keywords_from_prompt(prompt)
    
    # If insufficient keywords, use LLM fallback
    if len(keywords.color) + len(keywords.lighting) + len(keywords.mood) < 2:
        logger.info("Insufficient keywords, using LLM fallback")
        return await extract_style_with_llm(prompt)
    
    return keywords
```

---

### 2. Style Transfer Character Consistency

**Issue:** PRD 5 doesn't mention preserving character references (LoRA URLs) when transferring style.

**Problem:**
- If source clip has character_reference_urls, should they be preserved in target?
- Style transfer might break character consistency

**Recommendation:**
- Add `preserve_characters` option (default: true)
- If enabled, keep target clip's character_reference_urls
- Only transfer visual style (color, lighting, mood), not character identity

**Fix Needed:** Add to style transfer options:
```python
transfer_options = {
    "color_palette": true,
    "lighting": true,
    "mood": true,
    "preserve_characters": true  # NEW
}
```

---

### 3. Style Transfer Validation

**Issue:** No validation that source and target clips are from the same job.

**Problem:**
- User could accidentally select clips from different jobs
- Would cause errors or inconsistent results

**Recommendation:**
- Validate both clips belong to same job_id
- Return 400 Bad Request if validation fails
- Clear error message: "Source and target clips must be from the same video"

**Fix Needed:** Add validation in API endpoint:
```python
# Validate clips are from same job
source_clip = await get_clip(job_id, source_clip_index)
target_clip = await get_clip(job_id, target_clip_index)

if not source_clip or not target_clip:
    raise HTTPException(400, "Clips not found or from different jobs")
```

---

### 4. Multi-Clip Instruction Parsing Edge Cases

**Issue:** PRD 5's parser doesn't handle all instruction formats.

**Missing Patterns:**
- "make clips 1-3 brighter" (range notation)
- "make all clips except clip 2 brighter" (exclusion)
- "make the first half brighter" (relative positioning)
- "make clips with low energy brighter" (conditional, future)

**Recommendation:**
- Add range parsing: `re.findall(r'clips?\s+(\d+)\s*-\s*(\d+)', instruction)`
- Add exclusion parsing: `"except clip X"` → exclude from "all clips"
- Add relative positioning: `"first half"` → first 50% of clips
- Document limitations clearly

**Fix Needed:** Enhance parser:
```python
# Range notation: "clips 1-3"
range_match = re.search(r'clips?\s+(\d+)\s*-\s*(\d+)', instruction_lower)
if range_match:
    start_idx = int(range_match.group(1)) - 1
    end_idx = int(range_match.group(2)) - 1
    return [ClipInstruction(clip_index=i, instruction=modification) 
            for i in range(start_idx, end_idx + 1)]

# Exclusion: "all clips except clip 2"
if "all clips" in instruction_lower and "except" in instruction_lower:
    excluded = re.findall(r'except\s+clip[s]?\s+(\d+)', instruction_lower)
    excluded_indices = [int(x) - 1 for x in excluded]
    return [ClipInstruction(clip_index=i, instruction=modification)
            for i in range(total_clips) if i not in excluded_indices]
```

---

### 5. Suggestions API Rate Limiting

**Issue:** PRD 5 doesn't mention rate limiting for suggestions API.

**Problem:**
- Suggestions require LLM call ($0.01-0.02 each)
- User could spam suggestions API, causing high costs
- No protection against abuse

**Recommendation:**
- Rate limit: 10 suggestions per job per hour
- Cache suggestions for 5 minutes (same clip, same context)
- Return cached result if available

**Fix Needed:** Add rate limiting:
```python
# Check rate limit
suggestion_count = await get_suggestion_count(job_id, clip_index, last_hour=True)
if suggestion_count >= 10:
    raise HTTPException(429, "Rate limit exceeded. Please wait before requesting more suggestions.")

# Check cache
cached = await get_cached_suggestions(job_id, clip_index)
if cached and cached.age < 300:  # 5 minutes
    return cached.suggestions
```

---

### 6. Audio Context Matching Verification

**Status:** ✅ Verified - Audio parser does provide `song_structure` with `type` field (chorus, verse, etc.)

**Note:** PRD 5's `identify_chorus_clips()` function is correct and will work with existing audio parser output.

---

## PRD 6 (Comparison Tools & Analytics) - Issues Found

### 1. Comparison Mode - Different Durations

**Issue:** PRD 6 doesn't address what happens if original and regenerated clips have different durations.

**Problem:**
- Original clip: 12 seconds
- Regenerated clip: 15 seconds
- Side-by-side playback will desync after 12 seconds

**Recommendation:**
- Sync playback to shorter duration
- Show duration difference indicator
- Allow independent playback controls
- Option to loop shorter clip

**Fix Needed:** Add duration handling:
```typescript
const minDuration = Math.min(originalClip.duration, regeneratedClip.duration);
const maxDuration = Math.max(originalClip.duration, regeneratedClip.duration);

// Sync to shorter duration
if (originalClip.duration !== regeneratedClip.duration) {
  showDurationWarning(`Duration mismatch: ${originalClip.duration}s vs ${regeneratedClip.duration}s`);
  syncToDuration = minDuration;
}
```

---

### 2. Comparison - Missing/Failed Versions

**Issue:** PRD 6 doesn't handle cases where one version is missing or failed.

**Problem:**
- User tries to compare version 2 (current) with version 1 (original)
- Version 1 video file was deleted or failed to generate
- Comparison fails

**Recommendation:**
- Check both versions exist before allowing comparison
- Show error if version missing: "Version not available for comparison"
- Allow comparison with thumbnail only (if video missing)
- Graceful degradation

**Fix Needed:** Add validation:
```python
async def get_comparison_data(job_id, clip_index, version1_id, version2_id):
    v1 = await get_version(version1_id)
    v2 = await get_version(version2_id)
    
    if not v1 or not v2:
        raise HTTPException(404, "One or both versions not found")
    
    if not v1.video_url or not v2.video_url:
        # Return thumbnail-only comparison
        return {
            "mode": "thumbnail_only",
            "v1_thumbnail": v1.thumbnail_url,
            "v2_thumbnail": v2.thumbnail_url
        }
```

---

### 3. Comparison - Thumbnail Preview

**Issue:** PRD 6 doesn't mention using thumbnails for faster loading.

**Recommendation:**
- Show thumbnails immediately while videos load
- Lazy load full videos
- Allow thumbnail-only comparison mode (faster, less bandwidth)

**Fix Needed:** Add thumbnail support to comparison component.

---

### 4. Analytics Data Retention & Privacy

**Issue:** PRD 6 doesn't specify data retention policy or privacy considerations.

**Problem:**
- Analytics table grows indefinitely
- User data stored indefinitely
- No GDPR/privacy compliance mentioned

**Recommendation:**
- Retain analytics for 90 days (configurable)
- Archive older data to cold storage
- Allow users to delete their analytics data
- Anonymize system-wide analytics (remove user_id)

**Fix Needed:** Add retention policy:
```sql
-- Archive analytics older than 90 days
CREATE OR REPLACE FUNCTION archive_old_analytics()
RETURNS void AS $$
BEGIN
  INSERT INTO regeneration_analytics_archive
  SELECT * FROM regeneration_analytics
  WHERE created_at < NOW() - INTERVAL '90 days';
  
  DELETE FROM regeneration_analytics
  WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;
```

---

### 5. Analytics Aggregation Strategy

**Issue:** PRD 6 doesn't specify real-time vs batch aggregation.

**Problem:**
- Real-time aggregation: Slow queries on large tables
- Batch aggregation: Stale data

**Recommendation:**
- **Hybrid approach:**
  - Real-time for last 7 days (fast, small dataset)
  - Batch aggregation for older data (daily job, store in materialized view)
  - Cache aggregated results for 1 hour

**Fix Needed:** Add aggregation strategy:
```python
# Real-time for recent data
recent_analytics = await get_analytics(job_id, days=7)

# Batch for older data (from materialized view)
if days > 7:
    older_analytics = await get_cached_analytics(job_id, days=days)
    return combine(recent_analytics, older_analytics)
```

---

### 6. Analytics Export Functionality

**Issue:** PRD 6 doesn't mention export functionality.

**Recommendation:**
- Add export button: "Export Analytics (CSV)"
- Include: regenerations, costs, success rates, timestamps
- Useful for users tracking their usage

**Fix Needed:** Add export endpoint:
```python
@router.get("/jobs/{job_id}/analytics/export")
async def export_analytics(job_id: UUID, format: str = "csv"):
    analytics = await get_analytics(job_id)
    if format == "csv":
        return generate_csv(analytics)
    # ... other formats
```

---

### 7. Analytics Cost Tracking Per User

**Issue:** PRD 6 tracks analytics but doesn't mention cost budget enforcement.

**Recommendation:**
- Track total regeneration costs per user
- Alert if approaching budget limit
- Show cost breakdown in analytics dashboard
- Link to budget management (if exists)

**Fix Needed:** Add cost tracking:
```python
user_total_cost = await get_user_regeneration_cost(user_id, period="month")
if user_total_cost > user_budget_limit * 0.8:
    send_budget_alert(user_id, user_total_cost, user_budget_limit)
```

---

## Additional Cross-PRD Issues

### 1. Database Migration Order

**Issue:** PRDs mention new tables but don't specify migration order.

**Tables to Create:**
1. `clip_thumbnails` (PRD 1)
2. `clip_regenerations` (PRD 3)
3. `clip_versions` (PRD 4)
4. `regeneration_analytics` (PRD 6)

**Recommendation:**
- Create migration file with all tables in dependency order
- Test migrations on staging first
- Document rollback procedures

---

### 2. API Versioning

**Issue:** All PRDs use `/api/v1/` but no versioning strategy mentioned.

**Recommendation:**
- Document API versioning policy
- Plan for v2 if breaking changes needed
- Use version headers for future compatibility

---

### 3. Error Message Consistency

**Issue:** Different PRDs use different error message formats.

**Recommendation:**
- Standardize error response format:
```json
{
  "error": "error_code",
  "message": "User-friendly message",
  "details": {...},
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## Summary of Required Fixes

### PRD 5 Fixes:
1. ✅ Add LLM fallback for style keyword extraction
2. ✅ Add character consistency preservation option
3. ✅ Add validation for same-job clips
4. ✅ Enhance multi-clip instruction parser (ranges, exclusions)
5. ✅ Add rate limiting for suggestions API
6. ✅ Add caching for suggestions

### PRD 6 Fixes:
1. ✅ Handle different clip durations in comparison
2. ✅ Handle missing/failed versions gracefully
3. ✅ Add thumbnail preview for faster loading
4. ✅ Add data retention policy (90 days)
5. ✅ Add aggregation strategy (hybrid real-time/batch)
6. ✅ Add export functionality
7. ✅ Add cost tracking per user

### Cross-PRD Fixes:
1. ✅ Document migration order
2. ✅ Document API versioning strategy
3. ✅ Standardize error message format

---

## Priority Ranking

### High Priority (Must Fix Before Implementation):
1. Style transfer validation (same job)
2. Comparison duration handling
3. Analytics data retention policy
4. Multi-clip parser edge cases (ranges)

### Medium Priority (Should Fix):
1. Style transfer LLM fallback
2. Suggestions rate limiting
3. Comparison missing version handling
4. Analytics aggregation strategy

### Low Priority (Nice to Have):
1. Character consistency preservation
2. Thumbnail preview in comparison
3. Analytics export
4. Cost tracking per user

---

## Next Steps

1. Update PRD 5 with fixes 1-6
2. Update PRD 6 with fixes 1-7
3. Create migration file with all tables
4. Document API versioning strategy
5. Create error response standard

