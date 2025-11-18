# Clip Chatbot Feature - Part 5: Style Transfer & Multi-Clip Intelligence

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** Post-MVP - Part 2 of 3  
**Dependencies:** 
- Part 4: Batch Operations & Versioning ✅
- `PRD_clip_chatbot_4_batch_versioning.md` - Part 4 complete

**Related Documents:**
- `PRD_clip_chatbot_4_batch_versioning.md` - Part 4: Batch & Versioning
- `PRD_clip_chatbot_6_comparison_analytics.md` - Part 6: Comparison & Analytics

---

## Executive Summary

This PRD defines Part 5 of the post-MVP clip chatbot enhancements: style transfer between clips (keyword-based) and multi-clip instructions with intelligent parsing. This part enables users to maintain visual consistency and modify multiple clips with single instructions.

**Key Features:**
- Style transfer (keyword-based analysis)
- AI-powered prompt suggestions
- Multi-clip instructions (simple keyword matching)
- Audio context matching (chorus, verse, etc.)

**Timeline:** Weeks 3-4  
**Success Criteria:** Users can transfer styles between clips and modify multiple clips with single instructions

---

## Objectives

1. **Style Transfer:** Apply visual style from one clip to another
2. **Intelligent Suggestions:** AI suggests modifications based on clip analysis
3. **Multi-Clip Instructions:** Parse instructions to modify multiple clips
4. **Audio Context:** Match instructions to audio segments (chorus, verse)

---

## User Stories

**US-1: Style Transfer**
- As a user, I want to apply the style of one clip to another, so I can maintain consistency across different scenes.

**US-2: Prompt Suggestions**
- As a user, I want the AI to suggest modifications for my clip, so I can discover new creative possibilities.

**US-3: Multi-Clip Instructions**
- As a user, I want to say "make clips 2 and 4 brighter" and have both regenerate, so I can modify multiple clips efficiently.

---

## System Architecture

### Style Transfer Flow

```
User selects source clip (style to copy)
    ↓
User selects target clip (clip to modify)
    ↓
Extract style keywords from source prompt
    ↓
Inject style keywords into target prompt
    ↓
Regenerate target clip
```

### Multi-Clip Instruction Flow

```
User enters: "make clips 2 and 4 brighter"
    ↓
Parse instruction (keyword matching)
    ├─ Extract clip numbers: [2, 4]
    └─ Extract modification: "brighter"
    ↓
Generate per-clip instructions
    ├─ Clip 2: "make it brighter"
    └─ Clip 4: "make it brighter"
    ↓
Batch regenerate clips
```

---

## Detailed Requirements

### 1. Style Transfer

#### 1.1 Overview

Allow users to apply the visual style of one clip to another clip. Uses keyword-based analysis for MVP+ (simpler than ML-based approach).

#### 1.2 Style Analysis

**Keyword Extraction:**
- Extract style keywords from source clip prompt
- Identify color palette keywords (warm, cool, vibrant, muted)
- Identify lighting keywords (bright, dark, dramatic, soft)
- Identify mood keywords (energetic, calm, mysterious)
- **LLM Fallback:** If <2 style keywords found, use LLM to analyze prompt and extract style elements
  - Cost: Additional $0.01-0.02 per style transfer
  - Ensures style transfer works even with minimal keywords

**Implementation:**
```python
def extract_style_keywords(prompt: str) -> StyleKeywords:
    """
    Extract style keywords from prompt.
    
    Returns StyleKeywords with color, lighting, mood.
    """
    prompt_lower = prompt.lower()
    
    # Color palette
    color_keywords = []
    if any(kw in prompt_lower for kw in ["warm", "golden", "orange", "yellow"]):
        color_keywords.append("warm")
    if any(kw in prompt_lower for kw in ["cool", "blue", "cyan", "teal"]):
        color_keywords.append("cool")
    if any(kw in prompt_lower for kw in ["vibrant", "saturated", "colorful"]):
        color_keywords.append("vibrant")
    if any(kw in prompt_lower for kw in ["muted", "desaturated", "subtle"]):
        color_keywords.append("muted")
    
    # Lighting
    lighting_keywords = []
    if any(kw in prompt_lower for kw in ["bright", "well-lit", "daylight"]):
        lighting_keywords.append("bright")
    if any(kw in prompt_lower for kw in ["dark", "shadowy", "low light"]):
        lighting_keywords.append("dark")
    if any(kw in prompt_lower for kw in ["dramatic", "high contrast"]):
        lighting_keywords.append("dramatic")
    if any(kw in prompt_lower for kw in ["soft", "gentle", "diffused"]):
        lighting_keywords.append("soft")
    
    # Mood
    mood_keywords = []
    if any(kw in prompt_lower for kw in ["energetic", "dynamic", "fast-paced"]):
        mood_keywords.append("energetic")
    if any(kw in prompt_lower for kw in ["calm", "peaceful", "serene"]):
        mood_keywords.append("calm")
    if any(kw in prompt_lower for kw in ["mysterious", "mystical", "enigmatic"]):
        mood_keywords.append("mysterious")
    
    keywords = StyleKeywords(
        color=color_keywords,
        lighting=lighting_keywords,
        mood=mood_keywords
    )
    
    # LLM fallback if insufficient keywords
    total_keywords = len(keywords.color) + len(keywords.lighting) + len(keywords.mood)
    if total_keywords < 2:
        logger.info(f"Insufficient keywords ({total_keywords}), using LLM fallback")
        return await extract_style_with_llm(prompt)
    
    return keywords


async def extract_style_with_llm(prompt: str) -> StyleKeywords:
    """
    Use LLM to extract style keywords from prompt.
    
    Fallback when keyword matching finds insufficient style elements.
    """
    llm_prompt = f"""
    Analyze this video generation prompt and extract visual style elements:
    
    Prompt: {prompt}
    
    Extract:
    - Color palette (warm, cool, vibrant, muted, etc.)
    - Lighting style (bright, dark, dramatic, soft, etc.)
    - Mood/atmosphere (energetic, calm, mysterious, etc.)
    
    Return JSON: {{"color": [...], "lighting": [...], "mood": [...]}}
    """
    
    response = await call_llm(llm_prompt, model="gpt-4o", max_tokens=200)
    return parse_llm_style_response(response)
```

#### 1.3 Style Application

**Keyword Injection:**
```python
def apply_style_to_prompt(
    target_prompt: str,
    style_keywords: StyleKeywords,
    transfer_options: StyleTransferOptions
) -> str:
    """
    Apply style keywords to target prompt.
    
    Preserves original composition and subject.
    """
    style_additions = []
    
    if transfer_options.color_palette:
        style_additions.extend(style_keywords.color)
    
    if transfer_options.lighting:
        style_additions.extend(style_keywords.lighting)
    
    if transfer_options.mood:
        style_additions.extend(style_keywords.mood)
    
    if style_additions:
        style_text = ", ".join(style_additions)
        return f"{target_prompt}, {style_text} aesthetic"
    
    return target_prompt
```

#### 1.4 User Interface

**Style Transfer Dialog:**
```
┌─────────────────────────────────────────┐
│  Apply Style from Clip                  │
├─────────────────────────────────────────┤
│  Source Clip (style to copy):           │
│  [Clip 1 Thumbnail] "cyberpunk street"  │
│                                         │
│  Target Clip (clip to modify):         │
│  [Clip 3 Thumbnail] "cityscape"        │
│                                         │
│  Transfer Options:                      │
│  ☑ Color palette                       │
│  ☑ Lighting style                       │
│  ☐ Camera angle                         │
│  ☐ Motion style                         │
│                                         │
│  Additional instruction:                │
│  ┌───────────────────────────────────┐ │
│  │ "keep the original composition"    │ │
│  └───────────────────────────────────┘ │
│                                         │
│  [Apply Style] [Cancel]                │
└─────────────────────────────────────────┘
```

#### 1.5 API Endpoint

**POST /api/v1/jobs/{job_id}/clips/style-transfer**

**Validation:**
- Verify source and target clips exist and belong to same job_id
- Return 400 Bad Request if clips from different jobs
- Error message: "Source and target clips must be from the same video"

**Request:**
```json
{
  "source_clip_index": 0,
  "target_clip_index": 2,
  "transfer_options": {
    "color_palette": true,
    "lighting": true,
    "camera_angle": false,
    "motion": false,
    "preserve_characters": true  // Keep target clip's character references
  },
  "additional_instruction": "keep original composition"
}
```

**Response:**
```json
{
  "regeneration_id": "uuid",
  "estimated_cost": 0.15,
  "status": "queued"
}
```

---

### 2. AI-Powered Prompt Suggestions

#### 2.1 Overview

AI analyzes clips and suggests modifications to improve quality, consistency, or creativity.

#### 2.2 Suggestion Types

**Quality Improvements:**
- "This clip could benefit from better lighting"
- "Consider adding more motion to match the beat"
- "The color palette could be more vibrant"

**Consistency Suggestions:**
- "Clip 2's style doesn't match Clip 1 - consider adjusting"
- "The lighting in this clip is inconsistent with others"

**Creative Enhancements:**
- "This scene could use more dramatic camera movement"
- "Consider adding visual effects to match the music intensity"

#### 2.3 Implementation

**Analysis Pipeline:**
```python
async def generate_suggestions(
    job_id: UUID,
    clip_index: int
) -> List[Suggestion]:
    """
    Generate AI suggestions for a clip.
    """
    # Load clip data
    clips = await load_clips_from_job_stages(job_id)
    clip = clips.clips[clip_index]
    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
    audio_data = await load_audio_data(job_id)
    
    # Build context
    context = {
        "clip_prompt": clip_prompts.clip_prompts[clip_index].prompt,
        "other_clips": [cp.prompt for cp in clip_prompts.clip_prompts if cp.clip_index != clip_index],
        "audio_context": {
            "beat_intensity": audio_data.song_structure[clip_index].beat_intensity,
            "mood": audio_data.mood.primary
        }
    }
    
    # Generate suggestions with LLM
    suggestions = await call_llm_for_suggestions(context)
    
    return suggestions
```

**LLM Prompt:**
```
Analyze this clip and suggest improvements:

Clip Prompt: {clip_prompt}
Other Clips: {other_clips_summary}
Audio Context: {audio_context}

Suggest 3-5 specific, actionable improvements.
Format: Short description + example instruction
```

#### 2.4 User Interface

**Suggestions Panel:**
```
┌─────────────────────────────────────────┐
│  AI Suggestions for Clip 2              │
├─────────────────────────────────────────┤
│  💡 Quality: "This clip could benefit   │
│     from better lighting"               │
│     [Apply: "improve lighting"]         │
│                                         │
│  💡 Consistency: "Clip 2's style        │
│     doesn't match Clip 1"              │
│     [Apply: "match Clip 1's style"]    │
│                                         │
│  💡 Creative: "Add more motion to       │
│     match the beat intensity"          │
│     [Apply: "add more motion"]         │
└─────────────────────────────────────────┘
```

#### 2.5 API Endpoint

**GET /api/v1/jobs/{job_id}/clips/{clip_index}/suggestions**
- Returns list of suggestions with example instructions
- **Rate Limiting:** 10 requests per job per hour
- **Caching:** Suggestions cached for 5 minutes (same clip, same context)
- Returns 429 if rate limit exceeded

**POST /api/v1/jobs/{job_id}/clips/{clip_index}/suggestions/{suggestion_id}/apply**
- Applies a suggestion (creates regeneration)

---

### 3. Multi-Clip Instructions

#### 3.1 Overview

Allow users to modify multiple clips with a single instruction, with intelligent interpretation using simple keyword matching for MVP+.

#### 3.2 Instruction Types

**Universal Instructions:**
- "make all clips brighter" - Applies to all clips
- "add motion to all clips" - Applies to all clips

**Selective Instructions:**
- "make clips 2 and 4 brighter" - Specific clips
- "add motion to the chorus clips" - Based on audio context
- "make the first 3 clips warmer" - Range-based

**Conditional Instructions (Future):**
- "make dark clips brighter" - Based on clip analysis
- "add motion to slow clips" - Based on motion analysis

#### 3.3 Instruction Parser

**Simple Keyword Matching (MVP+):**
```python
def parse_multi_clip_instruction(
    instruction: str,
    total_clips: int,
    audio_data: AudioAnalysis
) -> List[ClipInstruction]:
    """
    Parse instruction to identify target clips.
    
    Returns list of (clip_index, instruction) pairs.
    """
    instruction_lower = instruction.lower()
    target_clips = []
    
    # Check for "all clips"
    if "all clips" in instruction_lower or "every clip" in instruction_lower:
        modification = extract_modification(instruction)
        return [
            ClipInstruction(clip_index=i, instruction=modification)
            for i in range(total_clips)
        ]
    
    # Check for specific clip numbers
    import re
    clip_numbers = re.findall(r'clip[s]?\s+(\d+)', instruction_lower)
    if clip_numbers:
        modification = extract_modification(instruction)
        return [
            ClipInstruction(clip_index=int(num) - 1, instruction=modification)
            for num in clip_numbers
        ]
    
    # Check for range notation: "clips 1-3"
    range_match = re.search(r'clips?\s+(\d+)\s*-\s*(\d+)', instruction_lower)
    if range_match:
        start_idx = int(range_match.group(1)) - 1
        end_idx = int(range_match.group(2)) - 1
        modification = extract_modification(instruction)
        return [
            ClipInstruction(clip_index=i, instruction=modification)
            for i in range(max(0, start_idx), min(total_clips, end_idx + 1))
        ]
    
    # Check for exclusion: "all clips except clip 2"
    if "all clips" in instruction_lower and "except" in instruction_lower:
        excluded = re.findall(r'except\s+clip[s]?\s+(\d+)', instruction_lower)
        excluded_indices = [int(x) - 1 for x in excluded]
        modification = extract_modification(instruction)
        return [
            ClipInstruction(clip_index=i, instruction=modification)
            for i in range(total_clips) if i not in excluded_indices
        ]
    
    # Check for audio context (chorus, verse, etc.)
    if "chorus" in instruction_lower:
        chorus_clips = identify_chorus_clips(audio_data)
        modification = extract_modification(instruction)
        return [
            ClipInstruction(clip_index=i, instruction=modification)
            for i in chorus_clips
        ]
    
    # Check for range-based (first 3, last 2, etc.)
    if "first" in instruction_lower:
        match = re.search(r'first\s+(\d+)', instruction_lower)
        if match:
            count = int(match.group(1))
            modification = extract_modification(instruction)
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in range(min(count, total_clips))
            ]
    
    # Default: apply to all clips
    modification = extract_modification(instruction)
    return [
        ClipInstruction(clip_index=i, instruction=modification)
        for i in range(total_clips)
    ]
```

**Audio Context Matching:**
```python
def identify_chorus_clips(audio_data: AudioAnalysis) -> List[int]:
    """
    Identify clips that correspond to chorus segments.
    """
    chorus_clips = []
    
    for i, boundary in enumerate(audio_data.clip_boundaries):
        # Check if clip overlaps with chorus segment
        for segment in audio_data.song_structure:
            if segment.type == "chorus":
                if (boundary.start >= segment.start and boundary.start < segment.end) or \
                   (boundary.end > segment.start and boundary.end <= segment.end):
                    chorus_clips.append(i)
                    break
    
    return chorus_clips
```

#### 3.4 User Interface

**Multi-Clip Instruction Input:**
```
┌─────────────────────────────────────────┐
│  Multi-Clip Instruction                 │
├─────────────────────────────────────────┤
│  Instruction:                           │
│  ┌───────────────────────────────────┐ │
│  │ "make clips 2 and 4 brighter"      │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Will apply to:                         │
│  ✓ Clip 2: "make it brighter"          │
│  ✓ Clip 4: "make it brighter"          │
│                                         │
│  Estimated cost: $0.30                  │
│  [Apply to Selected] [Cancel]           │
└─────────────────────────────────────────┘
```

---

## Implementation Tasks

### Task 1: Style Transfer
- [ ] Create style analysis functions (keyword extraction)
- [ ] Create style application functions (keyword injection)
- [ ] Create style transfer API endpoint
- [ ] Create style transfer UI component
- [ ] Add unit tests

### Task 2: AI Suggestions
- [ ] Create suggestion generation pipeline
- [ ] Integrate with LLM for suggestions
- [ ] Create suggestions API endpoint
- [ ] Create suggestions UI component
- [ ] Add unit tests

### Task 3: Multi-Clip Instructions
- [ ] Create instruction parser (keyword matching)
- [ ] Implement audio context matching
- [ ] Create multi-clip instruction UI
- [ ] Integrate with batch regeneration
- [ ] Add unit tests

---

## Testing Strategy

### Unit Tests
- Style keyword extraction
- Style application
- Instruction parsing
- Audio context matching

### Integration Tests
- Style transfer API
- Suggestions API
- Multi-clip instruction flow
- Batch regeneration with multi-clip

### E2E Tests
- Complete style transfer flow
- Complete suggestions flow
- Complete multi-clip instruction flow

---

## Success Criteria

### Functional
- ✅ Users can transfer styles between clips
- ✅ Users receive helpful AI suggestions
- ✅ Users can modify multiple clips with single instruction

### Performance
- ✅ Style transfer: <10s analysis + regeneration
- ✅ Suggestions: <5s generation time
- ✅ Instruction parsing: <100ms

### Quality
- ✅ Style transfer maintains quality
- ✅ Suggestions are relevant and actionable
- ✅ Multi-clip instructions accurately parsed

---

## Dependencies

### Internal Modules
- Clip Regenerator (from MVP)
- Audio Parser (for audio context)
- Batch Regeneration (from Part 4)

### External Services
- OpenAI GPT-4o or Claude 3.5 Sonnet (for suggestions)

---

## Risks & Mitigations

### Risk 1: Style Transfer Quality
**Risk:** Keyword-based style transfer doesn't produce good results  
**Mitigation:** Extensive testing, allow LLM fallback if keyword extraction insufficient

### Risk 2: Suggestion Relevance
**Risk:** AI suggestions aren't helpful or relevant  
**Mitigation:** Fine-tune LLM prompts, user feedback loop, allow hiding suggestions

### Risk 3: Instruction Parsing Accuracy
**Risk:** Simple keyword matching misses complex instructions  
**Mitigation:** Start with simple matching, add LLM-based parsing later if needed

---

## Next Steps

After completing Part 5, proceed to:
- **Part 6:** Comparison Tools & Analytics

