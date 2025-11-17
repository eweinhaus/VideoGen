# LoRA Module - Part 1: Overview & Architecture

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning - Ready for Implementation  
**Dependencies:** Reference Generator (Module 5) - ✅ Complete, Video Generator (Module 7) - ✅ Complete  
**Phase:** Post-MVP Enhancement  
**Order:** 1 of 4 (Complete First)

**Related Documents:**
- `PRD_lora_2_training.md` - Training infrastructure and implementation
- `PRD_lora_3_application.md` - LoRA application to video generation
- `PRD_lora_4_operations.md` - Error handling, monitoring, and operations
- `PRD_reference_generator_overview.md` - Reference image generation
- `PRD_video_generator_part2_generator.md` - Video generation with reference images

---

## Executive Summary

The LoRA (Low-Rank Adaptation) module enables character consistency across video clips by training custom LoRA models from character reference images. LoRAs are shared across all users, never deleted, and must be named by users when created. This module enhances the existing reference image strategy with AI model fine-tuning for superior character consistency.

**Key Metrics:**
- **Training Time:** 30-60 minutes per LoRA (async background job)
- **Training Cost:** ~$0.50-$2 per LoRA (tracked in job_costs, system budget: $200/month)
- **Storage Cost:** ~$0.001 per LoRA (50MB average, negligible)
- **Application Cost:** Minimal (pre-processing adds ~$0.005 per image, tracked in job_costs)
- **Success Rate:** 90%+ training success rate with retry logic
- **System Budget:** $200/month total training costs (monitored, alerts at $150/month)

---

## Objectives

1. **Character Consistency:** Maintain consistent character appearance across all video clips
2. **User Control:** Allow users to select existing LoRAs or train new ones
3. **Community Sharing:** All LoRAs are shared across all users (public library)
4. **Persistence:** LoRAs are never deleted (permanent archive)
5. **User Naming:** Users must name LoRAs when creating new ones (unique per user)
6. **Cost Efficiency:** Training costs tracked in budget system with per-user limit (max 5 LoRAs/month) and system-wide budget ($200/month)

---

## System Architecture

### Module Position in Pipeline

```
[5] Reference Generator → [LoRA Trainer] → [7] Video Generator
                              ↓
                    (LoRA stored for reuse)
                              ↓
                    [LoRA Application]
                              ↓
                    (Enhanced character consistency)
```

### Data Flow

**Training Flow:**
```
User selects "Train new LoRA" + provides name
  ↓
Check per-user limit (max 5 LoRAs/month, only count completed/training/pending)
  ↓
Determine character image source:
  - If triggered by video job: Use ALL character reference images from current job's Reference Generator (all characters, all variations)
  - If standalone: User must provide character images (Phase 2) or select from previous job
  ↓
Reference Generator creates character reference images (if not already done, only if triggered by job)
  - Collect all character reference images (multiple characters = multiple LoRAs, one per character)
  - Minimum 3 images per character required (validation before training)
  - **IMPORTANT:** Reference Generator returns `ReferenceImages` object with `character_references: List[ReferenceImage]`
  - Each `ReferenceImage` has: `character_id: str`, `image_url: str`
  - **Grouping Logic:** Group by `character_id`, collect all `image_url`s for each character
  - **Example:** If job has 2 characters (char1, char2) with 3 images each:
    - Character 1: [url1, url2, url3] → Train LoRA 1
    - Character 2: [url4, url5, url6] → Train LoRA 2
  - **Edge Case:** If character has <3 images, skip that character (log warning, don't train LoRA)
  ↓
LoRA Trainer downloads character images from Supabase Storage URLs
  ↓
Validate dataset (count, format, size, resolution)
  ↓
Create RunPod instance via API
  ↓
Upload training images to RunPod instance
  ↓
Deploy training script to instance
  ↓
Train LoRA model (async, 30-60 min, poll progress every 30s)
  ↓
Download trained LoRA file from RunPod
  ↓
Cleanup RunPod instance (always, even on failure)
  ↓
Upload LoRA to Supabase Storage
  ↓
Quality validation: Generate 3 test images with LoRA (parallel, different prompts)
  ↓
If validation passes (all 3 images successful, 2/3 show character features): Mark as "completed"
  ↓
If validation fails: Mark as "failed", store error, don't count toward user limit
  ↓
Store LoRA metadata in database
  ↓
LoRA available for all users (if completed)
```

**Application Flow:**
```
User selects LoRA (existing or new)
  ↓
If new: Start training (async), continue with reference images
If existing: Load LoRA URL
  ↓
Video Generator applies LoRA:
  Option A (if model supports): Direct LoRA parameter
  Option B (fallback): Pre-process with SDXL + LoRA → image → video
  ↓
Enhanced character consistency in all clips
```

### Key Components

1. **LoRA Trainer:** Trains LoRA models from character reference images (see PRD 2)
2. **LoRA Storage:** Stores trained LoRAs in Supabase Storage
3. **LoRA Database:** Tracks LoRA metadata (name, status, creator, usage)
4. **LoRA Application:** Applies LoRA to video generation (see PRD 3)
5. **LoRA Selector UI:** Frontend component for LoRA selection
6. **Operations & Monitoring:** Error handling, cleanup, monitoring (see PRD 4)

---

## Success Criteria

### Functional
- ✅ Users can select existing LoRAs from dropdown
- ✅ Users can train new LoRAs (with required naming)
- ✅ LoRA training completes successfully (90%+ success rate)
- ✅ LoRAs are shared across all users (public library)
- ✅ LoRAs are never deleted (permanent archive)
- ✅ LoRA application improves character consistency

### Quality
- ✅ Character consistency improved vs. reference images alone
- ✅ LoRA training produces usable models (no failures)
- ✅ LoRA application doesn't degrade video quality
- ✅ Training images are sufficient (3-10 images optimal)

### Performance
- ✅ Training completes in 30-60 minutes (async)
- ✅ LoRA application adds minimal latency (<5s per clip)
- ✅ Storage costs remain negligible (<$0.01 per LoRA)
- ✅ Training doesn't block video generation

### Reliability
- ✅ Training failures handled gracefully (retry logic)
- ✅ Fallback to reference images if LoRA not ready
- ✅ LoRA storage is reliable (Supabase Storage)
- ✅ 90%+ training success rate

### User Experience
- ✅ Clear LoRA selection UI (dropdown + new option)
- ✅ Training status visible (pending, training, validating, completed, failed)
- ✅ LoRA naming required and validated (unique per user)
- ✅ Existing LoRAs searchable/discoverable

---

## Implementation Phases

### Phase 1: MVP LoRA System (Priority: HIGH)

**Goal:** Basic LoRA training and application with generated images only

**Components:**
1. **Database Schema** (see Database Schema section)
2. **Training Module** (`modules/lora_trainer/`) - See PRD 2
3. **Application Module** (enhancement to `modules/video_generator/`) - See PRD 3
4. **API Endpoints** (see API Specifications section)
5. **Frontend Components** (see Frontend Specifications section)
6. **Operations & Monitoring** - See PRD 4

**Timeline:** 1-2 weeks

**Success Metrics:**
- LoRA training completes successfully
- LoRAs are stored and retrievable
- LoRA application improves character consistency
- Users can select and use LoRAs

---

### Phase 2: User Image Upload (Priority: MEDIUM)

**Goal:** Allow users to upload custom character images for better training quality

**Components:**
1. **Image Upload UI**
   - Drag-and-drop interface
   - Image preview
   - Validation (min 3, max 10 images)
   - Format validation (JPG, PNG)

2. **Image Storage**
   - `lora-training-images` bucket in Supabase Storage
   - Structure: `{user_id}/{lora_id}/uploaded/{image_index}.jpg`
   - Link to LoRA record in database

3. **Training Dataset Composition**
   - If user uploads 5+ images: Use only user images
   - If user uploads 3-4 images: Combine with 1-2 generated images
   - If user uploads 0 images: Use only generated images (Phase 1 behavior)

4. **Enhanced Training**
   - Better quality with user-curated images
   - Improved character consistency

**Timeline:** 1 week

**Success Metrics:**
- Users can upload 3-10 character images
- Training quality improves with user images
- Combined datasets work correctly

---

### Phase 3: Enhanced Discovery & Management (Priority: LOW)

**Goal:** Improve LoRA discovery, search, and management

**Components:**
1. **Search & Discovery UI**
   - Search by name/description
   - Filter by status, creator, date
   - Sort by popularity, recent, quality
   - Tags/categories (future)

2. **Usage Statistics**
   - Track LoRA usage count
   - Popular LoRAs highlighted
   - Creator attribution

3. **Quality Ratings** (optional)
   - User ratings for LoRAs
   - Quality indicators
   - Best practices guide

4. **Moderation** (if needed)
   - Basic content moderation
   - Report inappropriate LoRAs
   - Admin review system

**Timeline:** 2-3 weeks

**Success Metrics:**
- Users can easily find relevant LoRAs
- Popular LoRAs are discoverable
- Quality ratings help users choose

---

## Database Schema

```sql
-- LoRA Models Table
CREATE TABLE IF NOT EXISTS lora_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,  -- User-provided name (required, duplicates allowed across users)
  usage_count INTEGER DEFAULT 0,  -- Track how many times LoRA is used
  description TEXT,  -- Optional description
  storage_path TEXT NOT NULL,  -- Path in Supabase Storage
  storage_url TEXT NOT NULL,  -- Full URL to LoRA file
  file_size BIGINT NOT NULL,  -- Size in bytes
  training_status VARCHAR(20) NOT NULL CHECK (training_status IN ('pending', 'training', 'validating', 'completed', 'failed')),
  triggered_by_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,  -- Optional: Reference to video generation job that triggered training (if null, standalone training)
  validation_image_urls TEXT[],  -- Array of URLs to validation test images (3 images, stored in Supabase Storage, 30-day TTL)
  validation_passed BOOLEAN DEFAULT FALSE,  -- Whether quality validation passed
  character_description TEXT,  -- Character description used for training
  reference_image_urls TEXT[],  -- Array of reference image URLs used for training
  training_cost DECIMAL(10,4) DEFAULT 0.0000,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_lora_models_user ON lora_models(user_id);
CREATE INDEX IF NOT EXISTS idx_lora_models_status ON lora_models(training_status);
CREATE INDEX IF NOT EXISTS idx_lora_models_user_status ON lora_models(user_id, training_status);
CREATE INDEX IF NOT EXISTS idx_lora_models_name ON lora_models(name);  -- For search
CREATE INDEX IF NOT EXISTS idx_lora_models_usage ON lora_models(usage_count DESC);  -- For popularity sorting
CREATE UNIQUE INDEX IF NOT EXISTS idx_lora_models_user_name ON lora_models(user_id, name);  -- Prevent user from creating duplicate names

-- RLS Policies (all users can view all LoRAs - public library)
ALTER TABLE lora_models ENABLE ROW LEVEL SECURITY;

CREATE POLICY "All users can view all LoRAs"
  ON lora_models FOR SELECT
  USING (true);  -- Public library - all LoRAs visible to all users

CREATE POLICY "Users can insert own LoRAs"
  ON lora_models FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own LoRAs"
  ON lora_models FOR UPDATE
  USING (auth.uid() = user_id);

-- Update jobs table to reference LoRA
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lora_model_id UUID REFERENCES lora_models(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_lora_model ON jobs(lora_model_id);

-- LoRA Training Jobs Table (separate from video generation jobs)
CREATE TABLE IF NOT EXISTS lora_training_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lora_model_id UUID REFERENCES lora_models(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  runpod_pod_id TEXT,  -- RunPod instance ID
  training_progress INTEGER DEFAULT 0,  -- 0-100
  estimated_remaining INTEGER,  -- seconds
  error_message TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lora_training_jobs_lora ON lora_training_jobs(lora_model_id);
CREATE INDEX IF NOT EXISTS idx_lora_training_jobs_user ON lora_training_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_lora_training_jobs_pod ON lora_training_jobs(runpod_pod_id);

-- User Training Limits Tracking
CREATE TABLE IF NOT EXISTS user_training_limits (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  loras_created_this_month INTEGER DEFAULT 0,
  month_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_training_limits_reset ON user_training_limits(month_reset_date);
```

---

## API Specifications

### `GET /api/v1/lora-models`

**Purpose:** List all LoRAs (public library, all users can see all LoRAs)

**Authentication:** Required (JWT token)

**Query Parameters:**
- `status` (optional): Filter by training_status (pending, training, completed, failed)
- `search` (optional): Search by name/description
- `limit` (optional): Number of results (default: 50, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response:** JSON array of LoRA models with id, name, description, training_status, created_at, created_by, usage_count, plus pagination (total, limit, offset)

### `POST /api/v1/lora-models`

**Purpose:** Create new LoRA training job

**Authentication:** Required (JWT token)

**Request Body:** JSON with `name` (required, 1-255 chars, unique per user), `description` (optional), `character_images` (optional, Phase 2)

**Validation:** Validate name, check per-user limit (max 5/month), check duplicate name, create record with status "pending"

**Response:** JSON with `lora_id`, `status` ("pending"), `message`

**Error Responses:** 400 (invalid name), 409 (duplicate name), 429 (limit exceeded), 500 (server error)

### `GET /api/v1/lora-models/{id}`

**Purpose:** Get LoRA details

**Authentication:** Required (JWT token)

**Response:** JSON with id, name, description, training_status, storage_url, file_size, created_at, created_by, usage_count, reference_image_urls

### `GET /api/v1/lora-models/{id}/status`

**Purpose:** Get LoRA training status (for polling)

**Response:** JSON with id, training_status, progress (0-100), estimated_remaining (seconds)

---

## Frontend Specifications

### LoRA Selector Component

**Location:** `components/LoRASelector.tsx`

**Props:** `value: LoRASelection`, `onChange`, `disabled?` where `LoRASelection = { type: "none" } | { type: "existing"; loraId: string } | { type: "new"; characterName: string }`

**UI Elements:**
1. **Radio Group:**
   - "No LoRA" (use reference images only)
   - "Use existing LoRA" (dropdown of completed LoRAs)
   - "Train new LoRA" (text input for character name)

2. **Dropdown (if "existing" selected):**
   - List of completed LoRAs (name, description, creator)
   - **Display format:** "Cyberpunk Girl (by user@example.com)" - Shows creator to disambiguate duplicates
   - Sort by: Popularity (usage_count), Recent, Name
   - Search/filter (Phase 3)
   - Loading state while fetching

3. **Text Input (if "new" selected):**
   - Character name input (required, 1-255 characters)
   - **Validation:** 
     - Check if user already has LoRA with same name (prevent duplicates per user)
     - Show warning if name exists (other users can have same name)
   - Validation feedback
   - Help text: "A new LoRA will be trained from character reference images. This adds ~30-60 minutes to generation time. Training costs are covered by the system. Maximum 5 LoRAs per month per user."

4. **Status Display (if training):**
   - Training status badge (pending, training, validating, completed, failed)
   - Progress indicator (0-100% during training)
   - Estimated time remaining (updates every 30s)
   - **Validation Status:** Show "Validating quality..." when in validating state
   - **Completion Notification:** SSE event + optional email when training completes
   - **User Notice:** If LoRA training in progress during video generation: "LoRA training in progress. Video will use reference images. You can regenerate with LoRA once training completes."

**Integration:**
- Added to upload page (`app/upload/page.tsx`)
- Included in form submission
- LoRA selection passed to API Gateway

**Integration Notes:**
- Frontend: Add `loraSelection` to upload form, pass `lora_model_id` or `lora_name` in FormData
- Upload Route: Validate LoRA selection, create training job if `lora_name` provided, store `lora_model_id` in job record
- Orchestrator: After Reference Generator, start LoRA training if status is "pending", pass `lora_model_id` to Video Generator

---

## Decision Analysis & Rationale

This section documents the key architectural decisions made for the LoRA implementation.

### Key Decisions

1. **LoRA Sharing:** Public library (all users see all LoRAs, duplicates allowed with creator display)
2. **Deletion Policy:** Never delete (permanent archive, archival strategy in Phase 3 if storage costs exceed $100/month)
3. **User Naming:** Required, unique per user, duplicates allowed across users
4. **Per-User Limits:** 5 LoRAs/month (simple count, monthly reset)
5. **Training Infrastructure:** RunPod (primary), Replicate (fallback if available)
6. **Application Method:** Hybrid (try direct LoRA parameter, fallback to pre-processing)
7. **Quality Validation:** 3 test images in parallel (~$0.015 cost)
8. **Integration Point:** Conditional (LoRA if ready, reference images if not)

---

## Open Questions & Decisions

### Resolved
- ✅ **LoRA Sharing:** All LoRAs shared (public library, duplicates allowed with creator display)
- ✅ **Deletion Policy:** LoRAs never deleted (permanent archive)
- ✅ **User Naming:** Required when creating new LoRA, unique per user (can't create duplicate name)
- ✅ **Training Cost:** Covered by system with per-user limit (max 5 LoRAs/month)
- ✅ **Training Infrastructure:** RunPod (primary), Replicate (fallback if available)
- ✅ **Application Method:** Hybrid (try direct LoRA, fallback to pre-processing)
- ✅ **Training Timing:** Fully async (background job), check status once at video generation start
- ✅ **Quality Validation:** Enhanced basic validation (3 test images in parallel)
- ✅ **Per-User Limit:** Maximum 5 LoRAs per user per month
- ✅ **Integration Point:** Conditional (LoRA if ready, reference images if not)

### To Verify (Phase 1)
- ⏳ **Replicate Training API:** Does it exist? What's the API? (Fallback option)
- ⏳ **Replicate LoRA Support:** Research Replicate API docs for direct LoRA parameter support BEFORE implementation
- ⏳ **Model Compatibility:** Test each video model for direct LoRA parameter support
- ⏳ **Model Compatibility Decision:** If no models support direct LoRA, simplify to pre-processing only
- ⏳ **Training Quality:** Test optimal training parameters (rank, steps, learning rate)
- ⏳ **RunPod API:** Verify API access, instance types, pricing, cleanup methods, rate limits

### Future Decisions (Phase 2+)
- ⏳ **Private LoRAs:** Should users be able to make LoRAs private? (Phase 3)
- ⏳ **LoRA Versioning:** How to handle retraining same character? (Phase 2+)
- ⏳ **Moderation:** What level of moderation is needed? (Phase 3)
- ⏳ **Storage Archival:** Move old/unused LoRAs to cheaper storage? (Phase 3)
- ⏳ **Enhanced Validation:** Quality metrics, similarity scoring? (Phase 2)

---

## Implementation Checklist

### Phase 1: MVP LoRA System

**Pre-Implementation Research (CRITICAL - Do First):**
- [ ] RunPod API: Sign up, get API key, test instance creation/deletion, document endpoints/rate limits
- [ ] Replicate Training API: Check if exists, document endpoints/pricing, plan fallback
- [ ] Replicate SDXL + LoRA: Check LoRA parameter support, test if available, plan RunPod fallback

**Database:**
- [ ] Create `lora_models`, `lora_training_jobs`, `user_training_limits` tables
- [ ] Add `lora_model_id` to `jobs` table (foreign key)
- [ ] Create indexes and RLS policies

**API Endpoints:**
- [ ] `GET /api/v1/lora-models` - List all (pagination, filtering)
- [ ] `POST /api/v1/lora-models` - Create new (validate name, check limit)
- [ ] `GET /api/v1/lora-models/{id}` - Get details
- [ ] `GET /api/v1/lora-models/{id}/status` - Get training status (for polling)

**Frontend:**
- [ ] Create `LoRASelector` component, add to upload page, update store/API client

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 2025  
**Next:** PRD 2 (Training), PRD 3 (Application), PRD 4 (Operations)

