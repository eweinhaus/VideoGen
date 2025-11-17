# LoRA Module - Part 4: Operations & Monitoring

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning - Ready for Implementation  
**Dependencies:** PRD 1 (Overview) - Complete First, PRD 2 (Training) - Complete First, PRD 3 (Application) - Complete First  
**Phase:** Post-MVP Enhancement  
**Order:** 4 of 4 (Complete Last)

**Related Documents:**
- `PRD_lora_1_overview.md` - Overview and architecture
- `PRD_lora_2_training.md` - Training infrastructure
- `PRD_lora_3_application.md` - LoRA application to video generation

---

## Executive Summary

This document specifies operational concerns for the LoRA module, including comprehensive error handling, monitoring, alerting, background jobs, circuit breakers, instance cleanup, storage management, and security. These operations ensure reliability, cost control, and system health.

**Key Components:**
- Error scenario handling (all failure points)
- Monitoring and alerting (stuck jobs, orphaned instances, costs)
- Background jobs (cleanup, retry, reset)
- Circuit breakers (RunPod failure handling)
- Storage management (validation image cleanup)
- Security and privacy

---

## Error Scenarios & Handling

### Training Error Scenarios

**Scenario 1: RunPod Instance Creation Fails**
- **Error:** RunPod API returns error when creating instance
- **Handling:** 
  - Retry 3 times with exponential backoff (2s, 4s, 8s)
  - If all retries fail: Mark LoRA as "failed", notify user, try Replicate fallback (if available)
  - If Replicate also unavailable: Mark as "failed", user can retry later
  - Trigger circuit breaker if 3+ failures in 10 minutes (see Circuit Breaker section)

**Scenario 2: Training Images Corrupted During Download**
- **Error:** Downloaded image is corrupted or invalid
- **Handling:**
  - Re-download image (3 attempts with exponential backoff)
  - If re-download fails: Mark LoRA as "failed" with error "Invalid training images"
  - Don't count toward user limit (user can retry with different images)
  - Store error in `lora_training_jobs.error_message`

**Scenario 3: LoRA File Upload to Supabase Fails After Training**
- **Error:** Training completes but upload to Supabase Storage fails
- **Handling:**
  - Retry upload 3 times with exponential backoff
  - If all retries fail: Mark LoRA as "failed", store error, cleanup RunPod instance
  - **Critical:** Don't lose trained LoRA file - store temporarily, retry upload later
  - Background job retries failed uploads every hour (see Background Jobs section)

**Scenario 4: RunPod Instance Orphaned (Cleanup Failed)**
- **Error:** Instance cleanup fails, instance remains running
- **Handling:**
  - Background monitoring job detects orphaned instances (check every hour)
  - Retry cleanup with exponential backoff (3 attempts)
  - Alert admin if cleanup fails after 3 attempts
  - Track orphaned instances in database for manual cleanup
  - **Cost Impact:** Orphaned instances continue charging (~$0.30-$1/hour)

**Scenario 5: Quality Validation Fails**
- **Error:** Validation test images fail or don't show character features
- **Handling:**
  - Mark LoRA as "failed" with error "Quality validation failed"
  - Store validation results (which images failed, why) in `lora_models.validation_image_urls`
  - Don't count toward user limit (user can retry)
  - User can see validation results in UI (Phase 2+)
  - Store error in `lora_training_jobs.error_message`

**Scenario 6: Training Timeout (Exceeds 2 Hours)**
- **Error:** Training takes longer than 2 hours
- **Handling:**
  - Cancel training job, cleanup RunPod instance
  - Mark LoRA as "failed" with error "Training timeout"
  - Don't count toward user limit (user can retry)
  - Log timeout for monitoring (may indicate training parameter issues)
  - Alert admin if timeout occurs (indicates infrastructure or parameter problem)

### Application Error Scenarios

**Scenario 7: LoRA Not Ready During Video Generation**
- **Error:** LoRA still training, validating, or failed when video generation starts
- **Handling:**
  - Use original reference images (graceful fallback)
  - Log warning, continue pipeline (don't fail video generation)
  - User can regenerate video with LoRA once training completes
  - **Known Limitation:** If LoRA completes mid-generation, it won't be used (acceptable for Phase 1)

**Scenario 8: LoRA File Missing from Storage**
- **Error:** LoRA file deleted or inaccessible from Supabase Storage
- **Handling:**
  - Use original reference images (fallback)
  - Log error, continue pipeline
  - Alert admin (indicates storage issue)
  - Mark LoRA as "failed" if file permanently missing

**Scenario 9: Direct LoRA Application Failure**
- **Error:** Direct LoRA parameter fails (unsupported, invalid, API error)
- **Handling:**
  - Fallback to pre-processing path automatically
  - Retry direct application (1 attempt)
  - If retry fails: Use pre-processing path
  - Log warning, continue pipeline

**Scenario 10: Pre-processing SDXL Generation Failure**
- **Error:** SDXL generation fails when creating LoRA-enhanced image
- **Handling:**
  - Retry SDXL generation (3 attempts with exponential backoff)
  - If all retries fail: Use original reference image (don't fail video generation)
  - Log error, continue pipeline
  - Track failure rate for monitoring

---

## Circuit Breaker

### RunPod Circuit Breaker

**Purpose:** Prevent cascading failures if RunPod API is down or experiencing issues

**Configuration:**
- **Failure Threshold:** 3 failures in 10 minutes
- **Action:** Disable RunPod, use Replicate fallback (if available)
- **Recovery:** Automatic recovery after 30 minutes (try RunPod again)
- **Monitoring:** Track circuit breaker state, alert admin when triggered

**Implementation:**
- Store circuit breaker state in Redis (shared across workers)
- `check()` - Return False if circuit breaker open (3 failures in 10 minutes)
- `record_failure()` - Increment failure count, open circuit breaker if threshold reached
- `record_success()` - Reset failure count
- Automatic recovery after 30 minutes
- **Usage:** Check before creating RunPod instance, use fallback if open, record all failures

---

## Background Jobs

### 1. Orphaned Instance Monitoring

**Purpose:** Detect and cleanup RunPod instances that weren't properly cleaned up

**Frequency:** Every hour

**Process:**
1. Query `lora_training_jobs` for jobs with `runpod_pod_id` but status != "completed" or "failed"
2. Check RunPod API for instance status
3. If instance still running but job is old (>2 hours): Attempt cleanup
4. If cleanup fails after 3 attempts: Alert admin, track in database
5. Update job record with cleanup status

**Implementation:**
- Query `lora_training_jobs` for jobs with `runpod_pod_id` but status != "completed"/"failed"
- Check RunPod API for instance status, cleanup if instance still running but job >2 hours old
- Alert admin if cleanup fails after 3 attempts

### 2. Failed Upload Retry

**Purpose:** Retry failed LoRA file uploads to Supabase Storage

**Frequency:** Every hour

**Process:**
1. Query `lora_models` for LoRAs with status "failed" and error indicating upload failure
2. Check if LoRA file exists locally (temporary storage)
3. Retry upload to Supabase Storage
4. If successful: Update status to "validating" and continue quality validation
5. If fails after 3 attempts: Alert admin

### 3. Monthly Limit Reset

**Purpose:** Reset per-user LoRA creation counts on first of each month

**Frequency:** First of each month at 00:00 UTC

**Process:**
1. Query `user_training_limits` for all users
2. Check if `month_reset_date` is in previous month
3. Reset `loras_created_this_month` to 0
4. Update `month_reset_date` to current date
5. Log reset for monitoring

**Implementation:**
- Check if today is first of month (safety check)
- Query all `user_training_limits`, check if `month_reset_date` is in previous month
- Reset `loras_created_this_month` to 0, update `month_reset_date` to current date
- Handle date parsing (DATE and TIMESTAMPTZ formats), initialize missing dates
- **Cron Job:** Runs first of month at 00:00 UTC (crontab or Supabase Edge Function)

### 4. Validation Image Cleanup

**Purpose:** Delete validation test images older than 30 days

**Frequency:** Daily

**Process:**
1. Query `lora_models` for LoRAs with `validation_image_urls`
2. Check creation date of validation images
3. Delete images older than 30 days from Supabase Storage
4. Update `validation_image_urls` array in database
5. Log cleanup for monitoring

**Implementation:**
```python
# api_gateway/services/lora_cleanup.py

async def cleanup_validation_images():
    """Delete validation images older than 30 days."""
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # Find LoRAs with validation images
    loras = await db_client.table("lora_models").select(
        "id, validation_image_urls, created_at"
    ).not_.is_("validation_image_urls", "null").execute()
    
    for lora in loras.data:
        if datetime.fromisoformat(lora["created_at"]) < cutoff_date:
            # Delete validation images
            for url in lora["validation_image_urls"]:
                await storage.delete_file("lora-validation-images", extract_path_from_url(url))
            
            # Clear validation_image_urls
            await db_client.table("lora_models").update({
                "validation_image_urls": []
            }).eq("id", lora["id"]).execute()
```

---

## Monitoring & Alerting

### Training Job Monitoring

**Stuck Jobs:**
- **Detection:** Training jobs >2 hours old with status "training"
- **Action:** Alert admin, attempt cancellation
- **Threshold:** >2 hours
- **Alert:** "LoRA training job {job_id} has been running for >2 hours"

**Orphaned Instances:**
- **Detection:** RunPod instances not cleaned up (background job detects)
- **Action:** Retry cleanup, alert admin if fails
- **Threshold:** Instance running but job completed/failed
- **Alert:** "Orphaned RunPod instance detected: {pod_id}"

**Failure Rate:**
- **Detection:** Training failure rate >10% in last 24 hours
- **Action:** Alert admin (indicates infrastructure issue)
- **Threshold:** >10% failure rate
- **Alert:** "LoRA training failure rate is {rate}% (threshold: 10%)"

**Cost Monitoring:**
- **Detection:** Average cost per LoRA >$2.50
- **Action:** Alert admin (indicates optimization needed)
- **Threshold:** >$2.50 average
- **Alert:** "Average LoRA training cost is ${cost} (threshold: $2.50)"

**System-Wide Training Budget:**
- **Detection:** System-wide training costs >$150/month (75% of $200/month budget)
- **Action:** Alert admin (approaching budget limit)
- **Threshold:** >$150/month
- **Alert:** "System-wide LoRA training costs are ${cost}/month (75% of $200/month budget)"
- **Hard Limit:** Reject new training jobs if system budget exceeded (after current month's training completes)

### Storage Monitoring

**Growth Rate:**
- **Tracking:** LoRA count growth, project storage needs
- **Alert:** If growth rate exceeds projection (1000 LoRAs/month = ~50GB/month)
- **Action:** Monitor and plan for archival strategy if needed

**Cost Tracking:**
- **Monitoring:** Supabase Storage costs for LoRAs
- **Alert:** If storage costs >$100/month
- **Action:** Trigger archival strategy review (move old/unused LoRAs to cheaper storage)
- **Archival Strategy:**
  - Move LoRAs unused for 6+ months to cheaper storage (e.g., S3 Glacier)
  - Keep metadata in database, restore on-demand
  - Background job identifies candidates (no usage for 6+ months)
  - Manual approval before archival (Phase 3)

**Validation Image Cleanup:**
- **Monitoring:** Ensure validation images deleted after 30 days
- **Alert:** If cleanup job fails
- **Action:** Manual cleanup if needed

### Application Monitoring

**Usage Rate:**
- **Tracking:** % of videos using LoRAs
- **Metric:** LoRA usage vs. reference images only
- **Goal:** Track adoption and effectiveness

**Character Consistency:**
- **Tracking:** Improved vs. reference images alone (qualitative)
- **Metric:** User feedback, quality assessments
- **Goal:** Verify LoRA improves character consistency

**Quality Impact:**
- **Tracking:** No degradation in video quality
- **Metric:** Video quality metrics, user feedback
- **Goal:** Ensure LoRA doesn't degrade video quality

**Performance Impact:**
- **Tracking:** Latency added by LoRA application
- **Metric:** <5s latency per clip target
- **Goal:** Ensure LoRA doesn't significantly slow down generation

---

## Security & Privacy

### LoRA Sharing

**Public Library:**
- All LoRAs visible to all users
- No private LoRAs (Phase 1)
- User attribution (creator email/ID)
- Creator display in UI ("Name (by creator)")

**Future: Private LoRAs (optional):**
- Allow users to mark LoRAs as private (Phase 3)
- Only creator can use private LoRAs
- Defer to Phase 3

### Content Moderation

**Phase 1: Basic**
- No moderation (trust users)
- Monitor for abuse
- Track usage patterns

**Phase 3: Enhanced**
- Report inappropriate LoRAs
- Admin review system
- Content filtering

### Storage Security

**Supabase Storage:**
- **LoRA Models Bucket:** `lora-models` (private)
  - Stores trained LoRA files (permanent, never deleted)
  - Signed URLs for access (1 hour expiration)
  - Structure: `{user_id}/{lora_id}/model.safetensors`
- **Validation Images Bucket:** `lora-validation-images` (private)
  - Stores validation test images (temporary, 30-day TTL)
  - Signed URLs for access (1 hour expiration)
  - Structure: `{user_id}/{lora_id}/validation/{image_index}.jpg`
  - **Cleanup:** Background job deletes images older than 30 days
  - **Cost:** ~$0.0001 per image (negligible, ~$0.0003 per LoRA for 3 images)
- **RLS Policies:** Database access controlled by RLS policies

---

## Success Metrics

### Training Metrics
- **Success Rate:** 90%+ training completion
- **Training Time:** 30-60 minutes average
- **Cost per LoRA:** <$2.02 average (includes validation)
- **Storage Growth:** Monitor (no deletion policy)
  - **Projection:** 1000 LoRAs = ~50GB, 10,000 LoRAs = ~500GB
  - **Cost:** ~$0.001 per LoRA (Supabase Storage pricing)
  - **Alert Threshold:** If storage costs >$100/month, consider archival strategy

### Application Metrics
- **Usage Rate:** % of videos using LoRAs
- **Character Consistency:** Improved vs. reference images alone
- **Quality Impact:** No degradation in video quality
- **Performance Impact:** <5s latency per clip

### User Metrics
- **LoRA Creation:** Number of LoRAs created per user
- **LoRA Reuse:** Number of times LoRAs are reused
- **User Satisfaction:** Feedback on character consistency

### Operational Metrics
- **Orphaned Instances:** 0 (all instances cleaned up)
- **Failed Uploads:** <1% (retry job handles most)
- **Circuit Breaker Triggers:** <1 per week (indicates infrastructure stability)
- **Storage Cleanup:** 100% validation images deleted after 30 days

---

## Implementation Checklist

**Background Jobs:**
- [ ] Implement orphaned instance monitoring (checks every hour)
- [ ] Implement failed upload retry job (retries every hour)
- [ ] Implement monthly limit reset job (runs first of month at 00:00 UTC, timezone-aware)
- [ ] Implement validation image cleanup job (runs daily)
- [ ] Implement storage archival review job (runs monthly, identifies candidates for archival)
- [ ] Set up cron jobs or scheduled tasks

**Circuit Breaker:**
- [ ] Implement RunPod circuit breaker (3 failures in 10 min = disable RunPod)
- [ ] Integrate with training flow
- [ ] Add automatic recovery (30 minutes)
- [ ] Add admin alerts when triggered

**Monitoring & Alerting:**
- [ ] Implement stuck job detection (>2 hours)
- [ ] Implement orphaned instance detection
- [ ] Implement failure rate monitoring (>10%)
- [ ] Implement cost monitoring (>$2.50 average per LoRA)
- [ ] Implement system-wide training budget monitoring (>$150/month, $200/month hard limit)
- [ ] Implement storage cost monitoring (>$100/month)
- [ ] Set up alerting system (email, Slack, etc.)

**Error Handling:**
- [ ] Implement all error scenarios (10 scenarios)
- [ ] Add comprehensive error logging
- [ ] Add error tracking in database
- [ ] Add user notifications for errors

**Testing:**
- [ ] Unit tests for circuit breaker
- [ ] Unit tests for background jobs
- [ ] Integration tests for error scenarios
- [ ] E2E tests for monitoring and alerting

**Documentation:**
- [ ] Error scenarios documentation (all failure points and handling)
- [ ] Monitoring and alerting guide (stuck jobs, orphaned instances, cost tracking)
- [ ] Background jobs documentation
- [ ] Circuit breaker documentation

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 2025  
**Complete:** All 4 PRDs ready for implementation

