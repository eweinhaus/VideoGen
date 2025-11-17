# LoRA Module - Part 2: Training Infrastructure

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning - Ready for Implementation  
**Dependencies:** PRD 1 (Overview) - Complete First  
**Phase:** Post-MVP Enhancement  
**Order:** 2 of 4 (Complete After Overview)

**Related Documents:**
- `PRD_lora_1_overview.md` - Overview and architecture
- `PRD_lora_3_application.md` - LoRA application to video generation
- `PRD_lora_4_operations.md` - Error handling, monitoring, and operations

---

## Executive Summary

This document specifies the LoRA training infrastructure, including RunPod integration, dataset validation, quality validation, per-user limits, and the complete training module implementation. Training is fully async (background job) and includes comprehensive error handling and monitoring.

**Key Components:**
- RunPod API client for instance management
- Dataset validation (before training)
- Quality validation (after training, 3 test images)
- Per-user limit enforcement (max 5 LoRAs/month)
- Training script template
- Image extraction and storage

---

## Training Infrastructure

### Primary: RunPod (Cloud GPU)

**Why:** Full control, lower cost, flexible training parameters

**Cost:** ~$0.30-$1/hour (30-60 min = $0.15-$1 per LoRA)

**Setup:**
- RunPod API integration for instance management
- GPU instance creation via API (RTX 3090 or A40 recommended)
- Training script deployment to instance
- Progress monitoring via RunPod API polling (every 30s)
- Automatic instance cleanup after training (success or failure)

**Implementation:**
- `modules/lora_trainer/runpod_client.py` - RunPod API client
- `modules/lora_trainer/instance_manager.py` - Instance lifecycle management
- `modules/lora_trainer/training_script.py` - Training script template
- Instance template: Pre-configured with PyTorch, diffusers, peft
- Storage: Upload training images to RunPod instance storage
- Download: Download trained LoRA file after completion

**Risk Mitigation:**
- **Circuit Breaker:** If RunPod API fails 3+ times in 10 minutes, disable RunPod and use fallback (see PRD 4)
- **Instance Cleanup Monitoring:** Background job checks for orphaned instances every hour (see PRD 4)
- **Cost Monitoring:** Track RunPod costs per LoRA, alert if >$2 per LoRA (see PRD 4)
- **Rate Limit Handling:** Exponential backoff for RunPod API rate limits (2s, 4s, 8s)
- **Timeout Protection:** Maximum 2 hours per training job (prevent infinite training)

### Fallback: Replicate Training API (if available)

**Why:** Managed service, no infrastructure management, resilience

**Status:** Verify availability and API during Phase 1

**Pre-Phase 1 Verification Required:**
- Research Replicate training API availability
- Document API endpoints and parameters
- Test API access and rate limits
- If unavailable: Implement training job queue (delay training until RunPod available)

**Implementation:** Add Replicate fallback if RunPod unavailable or circuit breaker triggered

**Cost:** TBD (verify during implementation)

**Priority:** Phase 1.5 (quick win if available)

**Activation:** Automatic fallback if RunPod circuit breaker triggered or RunPod API unavailable

**Fallback Strategy if Replicate Unavailable:**
- Queue training jobs in database (status: "pending")
- Retry RunPod instance creation every 30 minutes
- Notify user when training starts (SSE event)

---

## Training Parameters

**Base Model:** SDXL (Stable Diffusion XL)

**LoRA Configuration:**
- **Rank:** 8 (configurable)
- **LoRA Alpha:** 32 (configurable)
- **Target Modules:** ["to_k", "to_q", "to_v", "to_out.0"]
- **LoRA Dropout:** 0.1 (configurable)

**Training Configuration:**
- **Training Steps:** 1000-2000 (configurable)
- **Learning Rate:** 1e-4 (configurable)
- **Batch Size:** 1-2 (configurable)
- **Optimizer:** AdamW (default)
- **Scheduler:** Cosine with warmup (default)

**File Format:** `.safetensors` (safe, standard)

**Output:**
- LoRA file: `model.safetensors` (~5-200MB)
- Metadata: Training parameters, base model, training time

---

## Training Dataset

### Dataset Requirements

**Minimum:** 3 images (basic training)

**Optimal:** 5-10 images (best quality)

**Maximum:** 20 images (diminishing returns)

**Source (Phase 1):** Character reference images from Reference Generator
- **Clarification:** Use ALL character reference images from the job's Reference Generator
- **Multiple Characters:** If job has multiple characters, train separate LoRAs (one per character)
- **Image Selection:** Use all variations per character (if Reference Generator creates multiple variations)
- **Minimum:** Must have at least 3 images per character to train LoRA

**Implementation Logic:**
- Group `ReferenceImages.character_references` by `character_id`
- For each character with ≥3 images, train separate LoRA
- If character has <3 images, skip (log warning)
- Multiple characters = multiple LoRAs (one per character)

**Enhancement (Phase 2):** User-uploaded images + generated images

### Dataset Validation (Before Training)

**Validation Checks:**
- **Count:** Minimum 3 images required
- **Format:** Valid formats: JPG, PNG
- **File Size:** 100KB - 10MB per image
- **Resolution:** Minimum 512x512 pixels
- **Quality:** Valid image file (not corrupted)
- **Reject if validation fails:** Don't start training, return error to user

**Implementation:**
- Download each image, validate format (JPG/PNG), size (100KB-10MB), resolution (≥512x512), and integrity (PIL verify)
- Return user-friendly error messages on failure

---

## Quality Validation (After Training)

### Enhanced Basic Validation (3 Test Images in Parallel)

**Process:**
1. Generate 3 test images with LoRA using different prompts:
   - Character-focused prompt
   - Scene-focused prompt
   - Action-focused prompt
2. All 3 images must generate successfully (no errors)
3. At least 2/3 images must show recognizable character features
   - **Character Features Definition:** 
     - Face similarity (consistent facial features across images)
     - Clothing/accessories consistency (if applicable)
     - Overall character appearance matches training images
   - **Detection Method (Phase 1):** Basic visual inspection (manual review or simple similarity check)
   - **Future Enhancement (Phase 2):** Automated similarity scoring using CLIP embeddings
4. If validation passes: Mark LoRA as "completed"
5. If validation fails: Mark as "failed", store error, don't count toward user limit

**Implementation:**
- Generate 3 test images in parallel using SDXL + LoRA (see PRD 3 for SDXL integration)
- Check all 3 images generated successfully, at least 2/3 show character features
- Upload validation images to Supabase Storage (30-day TTL), store URLs in database
- Track costs in `job_costs` table

**Cost:** ~$0.015 per validation (3 × $0.005 per SDXL image, parallel generation)

**Time:** ~5 seconds (parallel) vs ~15 seconds (sequential)

---

## Per-User Limits

### Limit Configuration

**Maximum:** 5 LoRAs per user per month

**Enforcement:**
- Check per-user limit before starting training
- **Count Logic:** Only count LoRAs with status "completed", "training", or "pending" (failed LoRAs don't count)
- Reject training request if limit exceeded
- Return clear error message: "You've reached your monthly limit of 5 LoRAs. Limit resets on the first of each month."

**Edge Cases:**
- **Failed LoRAs:** Don't count toward limit (user can retry)
- **Pending LoRAs:** Count toward limit (prevents queue abuse)
- **Training LoRAs:** Count toward limit (prevents concurrent training abuse)
- **Mid-Month Reset:** If user creates 5 LoRAs on day 1, they must wait until next month

**Monthly Reset:**
- Reset per-user counts on first of each month (automated cron job)
- Reset runs at 00:00 UTC on first day of month
- **Reset Logic:** Check if `month_reset_date.month != current_month.month OR month_reset_date.year != current_month.year`
- Updates `month_reset_date` and resets `loras_created_this_month` to 0
- **Implementation:** Database cron job or scheduled task (Supabase Edge Function or backend cron)
- **Timezone:** All date comparisons use UTC to avoid timezone edge cases

**Implementation:**
- Count LoRAs with status "completed", "training", or "pending" (authoritative count from database)
- Check if month changed (compare `month_reset_date` with current date)
- If month changed, reset count to 0 and update `month_reset_date`
- Return error message with next reset date if limit exceeded
- Fail open: Allow creation if limit check fails (log error, don't block user)

---

## Training Module Components

### Module Structure

```
modules/lora_trainer/
├── __init__.py
├── main.py              # Entry point for training
├── trainer.py            # LoRA training orchestration
├── runpod_client.py      # RunPod API client (instance management)
├── instance_manager.py   # Instance lifecycle (create, monitor, cleanup)
├── training_script.py    # Training script template (deployed to RunPod)
├── validator.py          # Dataset validation (before) + quality validation (after)
├── config.py             # Training configuration (base model, parameters)
├── storage.py            # LoRA file storage (Supabase Storage)
├── image_extractor.py    # Download character images from Supabase Storage URLs
└── limit_checker.py      # Per-user limit checking (max 5 LoRAs/month)
```

### Component Responsibilities

**main.py:**
- Entry point: `async def train_lora(job_id: UUID, lora_model_id: UUID, user_id: str) -> None`
- Orchestrates entire training flow
- Calls other components in sequence
- Handles errors and status updates

**Entry Point:** `async def train_lora(job_id, lora_model_id, user_id, character_image_urls=None)`
- Load LoRA record, verify status is "pending"
- Extract character images from job references if not provided
- Validate dataset, check per-user limit (double-check)
- Call `train_lora_model()` to start training

**trainer.py:**
- Main training orchestration logic
- Coordinates: validation → instance creation → training → validation → storage
- Progress tracking and SSE event publishing
- Error handling and cleanup

**runpod_client.py:**
- RunPod API client
- Instance creation, deletion, status checking
- Progress polling (every 30s)
- Error handling and retry logic

**RunPod API Client:**
- `create_instance()` - Create GPU instance (RTX 3090 or A40), handle rate limits (429), return pod_id
- `get_instance_status()` - Poll instance status for progress
- `delete_instance()` - Cleanup instance (always call, even on failure)
- **IMPORTANT:** Configure RunPod template_id and network_volume_id before implementation

**instance_manager.py:**
- Instance lifecycle management
- Create instance, monitor progress, cleanup
- Timeout handling (max 2 hours)
- Always cleanup on success or failure

**training_script.py:**
- Training script template (deployed to RunPod)
- PyTorch + diffusers + peft training code
- Configurable parameters (rank, steps, learning rate)
- Saves LoRA as `.safetensors` file

**Training Script:**
- Deploy to RunPod instance (PyTorch, diffusers, peft pre-configured)
- Train LoRA from character images (SDXL base, rank 8, 1500 steps, lr 1e-4)
- Save as `.safetensors` file
- Report progress for polling (every 30s)

**validator.py:**
- Dataset validation (before training)
- Quality validation (after training, 3 test images)
- Image format, size, resolution checks
- Character feature detection (basic)

**config.py:**
- Training configuration constants
- Base model selection (SDXL)
- Training parameters (rank, steps, learning rate)
- Environment-aware settings

**storage.py:**
- LoRA file upload to Supabase Storage
- Storage path generation
- Signed URL generation
- File size tracking

**Storage:**
- Upload to Supabase Storage bucket `lora-models`, path `{user_id}/{lora_model_id}/model.safetensors`
- Validate file size (5-200MB), generate signed URL (1 hour expiration)
- Never deleted (permanent archive)

**image_extractor.py:**
- Download character images from Supabase Storage URLs
- Image caching (temp directory, 1 hour TTL)
- Format validation
- Error handling and retry

**limit_checker.py:**
- Per-user limit checking
- Monthly count retrieval
- Limit enforcement
- Reset date checking

---

## Training Flow

### Complete Training Process

```
1. User selects "Train new LoRA" + provides name
   ↓
2. Check per-user limit (max 5 LoRAs/month)
   - If exceeded: Reject with error message
   - If OK: Continue
   ↓
3. Determine character image source
   - If triggered by video job: Use character reference images from current job
   - If standalone: User must provide images (Phase 2)
   ↓
4. Create LoRA record in database (status: "pending")
   ↓
5. Download character images from Supabase Storage URLs
   - Use image_extractor.py
   - Cache images locally (1 hour TTL)
   ↓
6. Validate dataset (before training)
   - Check count (min 3), format, size, resolution
   - If validation fails: Mark as "failed", return error
   ↓
7. Update status to "training"
   ↓
8. Create RunPod instance via API
   - Use runpod_client.py
   - Retry 3 times with exponential backoff if fails
   ↓
9. Upload training images to RunPod instance
   ↓
10. Deploy training script to instance
    ↓
11. Train LoRA model (async, 30-60 min)
    - Poll RunPod API every 30s for progress
    - Update training_progress in database
    - Publish SSE events for progress
    - Timeout after 2 hours
    ↓
12. Download trained LoRA file from RunPod
    - Download from RunPod instance storage (via API or SSH)
    - Validate LoRA file format (`.safetensors` structure)
    - Check file size (5-200MB range)
    - Verify file is not corrupted before upload
    - Validate `.safetensors` format (use safetensors library, check for LoRA keys)
    ↓
13. Cleanup RunPod instance (always, even on failure)
    - Use instance_manager.py
    - Retry cleanup if fails
    ↓
14. Upload LoRA to Supabase Storage
    - Use storage.py
    - Retry 3 times with exponential backoff
    ↓
15. Update status to "validating"
    ↓
16. Quality validation: Generate 3 test images with LoRA (parallel)
    - Use validator.py
    - Different prompts (character, scene, action)
    - Check if character features detected
    ↓
17. If validation passes: Mark as "completed"
    If validation fails: Mark as "failed", store error, don't count toward limit
    ↓
18. Store validation image URLs in database
    ↓
19. Publish completion SSE event
    ↓
20. LoRA available for all users (if completed)
```

---

## Cost Tracking

### Training Costs (Tracked in Budget System)

**Costs:**
- Training infrastructure cost (RunPod: ~$0.15-$1 per LoRA)
- Storage cost (Supabase: ~$0.001 per LoRA)
- Validation cost (SDXL test images: ~$0.015 per LoRA = 3 × $0.005, parallel generation)
- Total: ~$0.50-$2.02 per LoRA

**Cost Tracking Integration:**
- Track all training costs in `job_costs` table (stage: "lora_training")
- Add training costs to job's `total_cost` field (if triggered by video job)
- Track system-wide training costs separately (monthly budget: $200/month)
- Alert admin when system-wide training costs >$150/month (75% threshold)
- **Budget Enforcement:** Reject new training jobs if system budget exceeded (after current month's training completes)

**Per-User Limit:**
- Maximum 5 LoRAs per user per month
- Simple count-based enforcement (counts completed/training/pending, failed don't count)
- Monthly reset on first of month

---

## Error Handling

### Training Failures

**Retry Logic:**
- 3 attempts maximum
- Exponential backoff: 2s, 4s, 8s
- Only retry on retryable errors (network, timeout, infrastructure)

**Failure Handling:**
- Mark LoRA status as "failed" in database
- Store error message in `lora_training_jobs.error_message`
- Cleanup RunPod instance (if created) - **CRITICAL: Always cleanup, even on failure**
- Notify user via SSE event
- **Failed LoRAs:** Don't count toward per-user limit (user can retry)

**Non-Retryable Errors:**
- Invalid training images (<3 images, validation failed)
- Insufficient storage space
- Per-user limit exceeded (max 5 LoRAs/month)
- Invalid LoRA parameters
- Dataset validation failures (format, size, resolution)

### Error Scenarios

**Scenario 1: RunPod Instance Creation Fails**
- Retry 3 times with exponential backoff
- If all retries fail: Mark LoRA as "failed", notify user, try Replicate fallback (if available)
- If Replicate also unavailable: Mark as "failed", user can retry later

**Scenario 2: Training Images Corrupted During Download**
- Re-download image (3 attempts)
- If re-download fails: Mark LoRA as "failed" with error "Invalid training images"
- Don't count toward user limit

**Scenario 3: LoRA File Upload to Supabase Fails After Training**
- Retry upload 3 times with exponential backoff
- If all retries fail: Mark LoRA as "failed", store error, cleanup RunPod instance
- **Critical:** Don't lose trained LoRA file - store temporarily, retry upload later
- Background job retries failed uploads every hour (see PRD 4)

**Scenario 4: Quality Validation Fails**
- Mark LoRA as "failed" with error "Quality validation failed"
- Store validation results (which images failed, why)
- Don't count toward user limit
- User can see validation results in UI (Phase 2+)

**Scenario 5: Training Timeout (Exceeds 2 Hours)**
- Cancel training job, cleanup RunPod instance
- Mark LoRA as "failed" with error "Training timeout"
- Don't count toward user limit
- Log timeout for monitoring

---

## Testing Requirements

**Unit Tests:** Dataset validation, per-user limit checking, image extraction, quality validation, RunPod client (mocked), instance manager

**Integration Tests:** End-to-end training flow, per-user limit edge cases (failed LoRAs don't count, monthly reset)

---

## Implementation Checklist

**Training Module:**
- [ ] Create `lora_trainer` module structure
- [ ] **Pre-Phase 1:** Research and verify RunPod API (access, instance types, pricing, rate limits)
- [ ] **Pre-Phase 1:** Research Replicate training API (availability, API endpoints, cost)
- [ ] Implement RunPod API client (`runpod_client.py`) with rate limit handling
- [ ] Implement instance manager (`instance_manager.py`)
- [ ] Create training script template (`training_script.py`)
- [ ] Implement dataset validator (`validator.py` - before training)
- [ ] Implement quality validator (`validator.py` - after training, 3 test images in parallel)
- [ ] Implement LoRA file validation (format, size, corruption check)
- [ ] Implement image extractor (`image_extractor.py`)
- [ ] Implement LoRA storage (Supabase)
- [ ] Implement per-user limit checking (max 5 LoRAs/month)
- [ ] Implement cost tracking integration (job_costs table, system budget)
- [ ] Implement main trainer orchestration (`trainer.py`)
- [ ] Implement entry point (`main.py`)
- [ ] Add SSE events for training status
- [ ] Implement monthly limit reset job (cron job, runs first of month at 00:00 UTC, timezone-aware)

**Testing:**
- [ ] Unit tests for dataset validation
- [ ] Unit tests for per-user limit checking
- [ ] Unit tests for image extraction
- [ ] Unit tests for quality validation
- [ ] Unit tests for RunPod client (mocked)
- [ ] Unit tests for instance manager
- [ ] Integration tests for training flow
- [ ] Per-user limit edge cases

**Documentation:**
- [ ] Developer guide (RunPod setup, training parameters)
- [ ] Per-user limits documentation (edge cases, reset mechanism)

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 2025  
**Next:** PRD 3 (Application), PRD 4 (Operations)

