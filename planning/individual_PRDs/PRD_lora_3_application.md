# LoRA Module - Part 3: Application to Video Generation

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning - Ready for Implementation  
**Dependencies:** PRD 1 (Overview) - Complete First, PRD 2 (Training) - Complete First  
**Phase:** Post-MVP Enhancement  
**Order:** 3 of 4 (Complete After Training)

**Related Documents:**
- `PRD_lora_1_overview.md` - Overview and architecture
- `PRD_lora_2_training.md` - Training infrastructure
- `PRD_lora_4_operations.md` - Error handling, monitoring, and operations
- `PRD_video_generator_part2_generator.md` - Video generation with reference images

---

## Executive Summary

This document specifies how LoRA models are applied to video generation, including conditional integration, model compatibility checking, direct LoRA parameter support, and pre-processing fallback. LoRA application enhances character consistency across video clips.

**Key Components:**
- LoRA status checking (at video generation start)
- Model compatibility checking (which models support direct LoRA)
- Direct LoRA application (if supported)
- Pre-processing fallback (SDXL + LoRA → image → video)
- Conditional integration (LoRA if ready, reference images if not)

---

## LoRA Application Strategy

### Hybrid Approach: Try Direct, Fallback to Pre-processing

**Primary Path: Direct LoRA Parameter (if supported)**
- **Why:** Lower cost, better quality, single API call
- **Process:** Pass LoRA URL directly to Replicate video generation API
- **Cost:** Minimal (just loading LoRA, no extra SDXL generation)
- **Quality:** Best (no double generation)
- **Status:** Test each video model for direct LoRA support during Phase 1

**Fallback Path: Pre-processing (SDXL + LoRA → Image → Video)**
- **Why:** Works with all models, proven approach, flexible
- **Process:**
  1. Generate LoRA-enhanced image using SDXL + LoRA
  2. Use enhanced image as input to video generator
  3. Video generator creates clip from enhanced image
- **Cost:** +$0.005 per image (SDXL generation)
- **Quality:** Good (double generation, but acceptable fallback)
- **When Used:** 
  - If model doesn't support direct LoRA
  - If direct LoRA fails (error handling)
  - As universal fallback for all models

---

## Model Compatibility

### Compatibility Testing

**Pre-Phase 1 Research:**
- Check Replicate API documentation for direct LoRA parameter support
- Research each video model's capabilities
- Document findings before implementation

**Phase 1 Testing:**
- Test LoRA application with each video model:
  - `kling_v21`
  - `kling_v25_turbo`
  - `hailuo_23`
  - `wan_25_i2v`
  - `veo_31`
- Document which models support direct LoRA
- Create compatibility matrix in documentation

**Fallback Strategy:**
- If no models support direct LoRA: Simplify to pre-processing only (remove hybrid complexity)
- If 1-2 models support: Use hybrid approach (try direct, fallback to pre-processing)
- Document compatibility matrix for future reference

### Compatibility Matrix

**Expected Outcome:**
- **Best Case:** 1-2 models support direct LoRA → Hybrid approach
- **Likely Case:** No models support direct LoRA → Pre-processing only (simpler)
- **Worst Case:** Unknown → Test during Phase 1, document results

**Implementation:**
```python
# modules/video_generator/lora_compatibility.py

MODEL_LORA_COMPATIBILITY = {
    "kling_v21": {
        "direct_lora_supported": False,  # Test during implementation
        "preprocessing_required": True,
        "notes": "Test during Phase 1"
    },
    "kling_v25_turbo": {
        "direct_lora_supported": False,  # Test during implementation
        "preprocessing_required": True,
        "notes": "Test during Phase 1"
    },
    "hailuo_23": {
        "direct_lora_supported": False,  # Test during implementation
        "preprocessing_required": True,
        "notes": "Test during Phase 1"
    },
    "wan_25_i2v": {
        "direct_lora_supported": False,  # Test during implementation
        "preprocessing_required": True,
        "notes": "Test during Phase 1"
    },
    "veo_31": {
        "direct_lora_supported": False,  # Test during implementation
        "preprocessing_required": True,
        "notes": "Test during Phase 1"
    }
}

def supports_direct_lora(video_model: str) -> bool:
    """Check if video model supports direct LoRA parameter."""
    return MODEL_LORA_COMPATIBILITY.get(video_model, {}).get("direct_lora_supported", False)
```

---

## Conditional Integration

### Integration Point

**Approach:**
- Check LoRA status once at video generation start (static decision, no polling during generation)
- If LoRA ready: Generate LoRA-enhanced reference image, use as character reference
- If LoRA not ready: Use original reference images (graceful fallback)
- Users can regenerate video with LoRA once training completes

**Rationale:**
- Post-MVP requires resilience
- Conditional integration provides best quality when available, graceful fallback when not
- Static check (no polling during generation) keeps implementation simple and predictable
- Known limitation: If LoRA completes mid-generation, it won't be used (acceptable for Phase 1)

### Integration Flow

```
Video Generator starts
  ↓
Check if job has lora_model_id
  ↓
If no LoRA: Use original reference images (current behavior)
  ↓
If LoRA selected:
  - Load LoRA record from database
  - Check training_status
    ↓
  If status == "completed":
    - Check model compatibility for direct LoRA
      ↓
    If direct supported:
      - Pass LoRA URL directly to video model
      - Generate clips with LoRA
    If not supported:
      - Generate LoRA-enhanced reference image (pre-processing)
      - Use enhanced image as character reference
      - Generate clips from enhanced image
    ↓
  If status != "completed" (pending, training, validating, failed):
    - Use original reference images (graceful fallback)
    - Log warning, continue pipeline
    - Don't fail video generation
```

---

## Direct LoRA Application

### Implementation

**If Model Supports Direct LoRA:**

```python
# modules/video_generator/lora_application.py

async def apply_lora_direct(
    lora_url: str,
    clip_prompt: ClipPrompt,
    video_model: str,
    job_id: UUID
) -> Optional[str]:
    """
    Apply LoRA directly to video generation (if model supports).
    
    Returns:
        LoRA URL if successful, None if not supported or fails
    """
    if not supports_direct_lora(video_model):
        return None
    
    # Pass LoRA URL directly to Replicate API
    # Implementation depends on Replicate API support
    # This is a placeholder - actual implementation depends on API verification
    
    return lora_url
```

**Testing:**
- Test with each video model
- Verify LoRA parameter is accepted
- Verify LoRA is applied correctly
- Document results in compatibility matrix

**Testing:**
- Create test prediction with LoRA parameter, check if API accepts it
- Document results in compatibility matrix (dict mapping model → direct_lora_supported boolean)

---

## Pre-processing Path

### Implementation

**Implementation:**
- Download LoRA file once, process each clip prompt
- For clips with character references: Generate LoRA-enhanced image using SDXL + LoRA, replace `character_reference_urls[0]`
- **SDXL + LoRA Integration (CRITICAL - Research First):**
  - Option 1: Replicate SDXL with LoRA parameter (if supported)
  - Option 2: RunPod SDXL inference (fallback)
  - Research Replicate API docs, test LoRA parameter, document API format

**Integration:**
- Add `lora_model_id` parameter to `video_generator.process()`
- Check LoRA status once at start (if status="completed", apply LoRA; else use original references)
- Replace `character_reference_urls[0]` with LoRA-enhanced image, keep scene references unchanged

---

## Error Handling

### Application Failures

**LoRA Not Ready:**
- If LoRA still training: Use original reference images (graceful fallback)
- If LoRA failed: Use original reference images (graceful fallback)
- If LoRA validating: Use original reference images (graceful fallback)
- Log warning, continue pipeline (don't fail video generation)

**LoRA Load Failure:**
- If LoRA file missing: Use original reference images (fallback)
- If LoRA invalid: Use original reference images (fallback)
- Log error, continue pipeline

**Direct LoRA Application Failure:**
- If direct LoRA fails: Fallback to pre-processing path
- Retry direct application (1 attempt)
- If retry fails: Use pre-processing path

**Pre-processing Failure:**
- If SDXL generation fails: Use original reference image
- Retry SDXL generation (3 attempts with exponential backoff)
- If all retries fail: Use original reference image (don't fail video generation)

**Error Handling:**
- Retry SDXL generation 3 times with exponential backoff (2s, 4s, 8s)
- If all retries fail: Use original reference image (don't fail video generation)

---

## Cost Tracking

### Application Costs

**Direct LoRA Path (if supported):**
- Minimal cost (just loading LoRA)
- Negligible impact (~$0.0001 per clip)
- **Preferred method** when available
- **Cost Tracking:** Track in `job_costs` table (stage: "lora_application", api_name: "lora_direct")

**Pre-processing Path (fallback):**
- SDXL generation: +$0.005 per image
- For 5 clips: +$0.025 total
- Minimal impact on overall budget
- **Used when:** Direct LoRA not supported or fails
- **Cost Tracking:** Track SDXL generation costs in `job_costs` table (stage: "lora_application", api_name: "sdxl_lora_preprocessing")
- **Integration:** Add pre-processing costs to job's `total_cost` field

---

## Testing Requirements

### Unit Tests

**Direct LoRA Application:**
- Model compatibility checking
- LoRA URL passing to video model
- Error handling (unsupported model, invalid LoRA)

**Pre-processing Path:**
- LoRA-enhanced image generation
- SDXL + LoRA integration
- Enhanced image upload
- Error handling (SDXL generation failures)

**Conditional Integration Logic:**
- LoRA status checking
- Fallback to reference images
- Model compatibility checking
- Error handling

### Integration Tests

**Application Flow:**
- LoRA selection
- LoRA status checking (at video generation start)
- Direct LoRA application (if supported)
- Pre-processing fallback (if direct fails or not supported)
- Model compatibility checking
- Fallback to reference images (if LoRA not ready)
- Cost tracking

### E2E Tests

**Full Pipeline with LoRA:**
- User selects existing LoRA
- Video generation uses LoRA
- Character consistency verified

**Fallback Scenarios:**
- LoRA not ready → Uses reference images
- Direct LoRA fails → Falls back to pre-processing
- Pre-processing fails → Uses original reference images

**Model Compatibility Testing:**
- Test each video model for direct LoRA support
- Document compatibility matrix
- Verify fallback works for all models

---

## Implementation Checklist

**Application Module:**
- [ ] **Pre-Phase 1:** Research Replicate API for direct LoRA support (before implementation)
- [ ] **Pre-Phase 1:** Research SDXL + LoRA integration on Replicate (if pre-processing needed)
- [ ] Enhance video generator with LoRA application
  - [ ] LoRA URL loading from database
  - [ ] Conditional integration (check LoRA status at start)
  - [ ] Model compatibility checking
  - [ ] Direct LoRA support (test each model)
  - [ ] Pre-processing fallback path (SDXL + LoRA)
  - [ ] Error handling (all failure scenarios)
  - [ ] Cost tracking integration (job_costs table)
- [ ] Test each video model for direct LoRA compatibility
- [ ] Create compatibility matrix documentation
- [ ] Implement direct LoRA application (if supported)
- [ ] Implement pre-processing path (SDXL + LoRA via Replicate or RunPod)
- [ ] Integrate with video generator process
- [ ] Add cost tracking for LoRA application (direct and pre-processing paths)

**Testing:**
- [ ] Unit tests for direct LoRA application
- [ ] Unit tests for pre-processing fallback
- [ ] Unit tests for model compatibility checking
- [ ] Unit tests for conditional integration logic
- [ ] Integration tests for application flow
- [ ] E2E tests for full pipeline with LoRA
- [ ] Fallback scenario tests
- [ ] Model compatibility testing

**Documentation:**
- [ ] Model compatibility matrix (which models support direct LoRA)
- [ ] Application flow documentation
- [ ] Error handling documentation

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 2025  
**Next:** PRD 4 (Operations)

