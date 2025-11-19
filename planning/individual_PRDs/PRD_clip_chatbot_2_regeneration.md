# Clip Chatbot Feature - Part 2: Regeneration Core

**Version:** 1.0  
**Date:** January 2025  
**Status:** Planning  
**Phase:** MVP - Part 2 of 3  
**Dependencies:** 
- Part 1: Foundation & Data Infrastructure ✅
- `PRD_clip_chatbot_1_foundation.md` - Part 1 complete

**Related Documents:**
- `PRD_clip_chatbot_1_foundation.md` - Part 1: Foundation
- `PRD_clip_chatbot_3_integration.md` - Part 3: Integration & Polish

---

## Executive Summary

This PRD defines Part 2 of the MVP clip chatbot feature: the core regeneration engine including template system, LLM prompt modification, context building, and the regeneration API. This part implements the intelligence that converts user instructions into regenerated clips.

**Key Deliverables:**
- Template system for common modifications
- LLM prompt modification engine
- Context builder (conversation history management)
- Regeneration API endpoint
- ClipChatbot UI component

**Timeline:** Week 2  
**Success Criteria:** Users can chat with AI to modify clips and trigger regeneration

---

## Objectives

1. **Template System:** Match common instructions to template transformations (skip LLM)
2. **LLM Modification:** Intelligently modify prompts based on user instructions
3. **Context Management:** Build rich context for LLM while limiting token usage
4. **Regeneration API:** Expose regeneration endpoint with SSE progress
5. **Chatbot UI:** Conversational interface for clip modification

---

## User Stories

**US-1: Chatbot Interaction**
- As a user, I want to tell the chatbot "make it nighttime" and have it regenerate the selected clip.

**US-2: Conversational Refinement**
- As a user, I want to have a conversation with the chatbot (e.g., "make it brighter" → "add more motion").

**US-3: Cost Awareness**
- As a user, I want to see the estimated cost before regenerating a clip.

**US-4: Progress Tracking**
- As a user, I want to see progress during clip regeneration.

---

## System Architecture

### High-Level Flow

```
User enters instruction
    ↓
Template Matcher (check common modifications)
    ↓
[Template Match?]
    ├─ Yes → Apply template transformation (skip LLM)
    └─ No → LLM Prompt Modifier (with full context)
    ↓
Modified Prompt
    ↓
Video Generator (single clip)
    ↓
New Clip Generated
```

### Component Structure

```
modules/clip_regenerator/
├── template_matcher.py     # Template matching
├── llm_modifier.py         # LLM prompt modification
├── context_builder.py      # Build LLM context
└── process.py              # Main orchestration

api_gateway/routes/clips.py
└── POST /clips/{idx}/regenerate

frontend/components/
└── ClipChatbot.tsx
```

---

## Detailed Requirements

### 1. Template System

#### 1.1 Overview

Template system matches common user instructions to predefined transformations, skipping LLM calls for faster, cheaper regeneration.

#### 1.2 Template Definitions

**Location:** `modules/clip_regenerator/template_matcher.py`

**Templates:**
```python
TEMPLATES = {
    "brighter": {
        "keywords": ["brighter", "brighten", "more light", "lighter"],
        "transformation": "Add 'bright lighting, well-lit, high exposure' to prompt",
        "cost_savings": 0.01  # Skip LLM call
    },
    "darker": {
        "keywords": ["darker", "darken", "less light", "dimmer"],
        "transformation": "Add 'dark lighting, low exposure, shadowy' to prompt",
        "cost_savings": 0.01
    },
    "nighttime": {
        "keywords": ["nighttime", "night", "dark sky", "stars"],
        "transformation": "Add 'nighttime scene, dark sky, stars visible, night lighting, cool tones' to prompt",
        "cost_savings": 0.01
    },
    "daytime": {
        "keywords": ["daytime", "day", "bright sky", "sunny"],
        "transformation": "Add 'daytime scene, bright sky, natural daylight, warm tones' to prompt",
        "cost_savings": 0.01
    },
    "more_motion": {
        "keywords": ["more motion", "add motion", "dynamic", "movement"],
        "transformation": "Add 'dynamic camera movement, motion blur, fast-paced action' to prompt",
        "cost_savings": 0.01
    },
    "less_motion": {
        "keywords": ["less motion", "calm", "still", "static"],
        "transformation": "Add 'static camera, minimal movement, calm composition' to prompt",
        "cost_savings": 0.01
    }
}
```

#### 1.3 Matching Logic

```python
def match_template(instruction: str) -> Optional[TemplateMatch]:
    """
    Match user instruction to template.
    
    Returns TemplateMatch if found, None otherwise.
    
    Matching Strategy:
    - First match wins (simple, predictable)
    - Templates checked in order defined in TEMPLATES dict
    - All matches logged for future improvement
    - If multiple templates could match, first one in dict order is used
    """
    instruction_lower = instruction.lower()
    matches = []  # Track all matches for logging
    
    for template_id, template in TEMPLATES.items():
        for keyword in template["keywords"]:
            if keyword in instruction_lower:
                match = TemplateMatch(
                    template_id=template_id,
                    transformation=template["transformation"],
                    cost_savings=template["cost_savings"]
                )
                matches.append(match)
                # First match wins
                if len(matches) == 1:
                    logger.info(
                        f"Template matched: {template_id}",
                        extra={"instruction": instruction, "all_matches": [m.id for m in matches]}
                    )
                    return match
    
    if matches:
        # Multiple matches found, log for analysis
        logger.warning(
            f"Multiple template matches found, using first: {matches[0].template_id}",
            extra={"instruction": instruction, "all_matches": [m.template_id for m in matches]}
        )
        return matches[0]
    
    return None
```

**Template Matching Priority:**
- **First match wins:** Simple, predictable behavior
- **Order matters:** Templates checked in dict order
- **Logging:** All matches logged for future template expansion
- **Limitation:** Complex instructions (e.g., "make it brighter and nighttime") will only match first template
- **Future:** Can enhance to support multiple template combinations

#### 1.4 Template Application

```python
def apply_template(original_prompt: str, template: TemplateMatch) -> str:
    """
    Apply template transformation to prompt.
    
    Example:
    Original: "A cyberpunk street scene"
    Template: "nighttime"
    Result: "A cyberpunk street scene, nighttime scene, dark sky, stars visible, night lighting, cool tones"
    """
    return f"{original_prompt}, {template.transformation}"
```

---

### 2. LLM Prompt Modification

#### 2.1 System Prompt

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

#### 2.2 User Prompt Template

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

**Token Budget:**
- Maximum context tokens: 2000 (system + user prompt)
- Conversation history limited to last 2-3 messages to stay within budget
- Scene plan summary truncated if needed (priority: style > characters > scenes)

#### 2.3 LLM Configuration

- Model: GPT-4o (for quality) or Claude 3.5 Sonnet
- Temperature: 0.7 (creative but consistent)
- Max tokens: 300 (output only)
- Max context tokens: 2000 (system + user prompt)
- Retry: 3 attempts with exponential backoff

#### 2.4 Implementation

**Location:** `modules/clip_regenerator/llm_modifier.py`

```python
async def modify_prompt_with_llm(
    original_prompt: str,
    user_instruction: str,
    context: Dict[str, Any],
    conversation_history: List[Dict[str, str]]
) -> str:
    """
    Modify prompt using LLM.
    
    Returns modified prompt string.
    """
    system_prompt = get_system_prompt()
    user_prompt = build_user_prompt(
        original_prompt,
        user_instruction,
        context,
        conversation_history[-3:]  # Last 3 messages only
    )
    
    response = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="gpt-4o",
        temperature=0.7,
        max_tokens=300
    )
    
    # Parse and clean LLM response
    # LLM may add explanations despite "Output only the modified prompt" instruction
    cleaned_prompt = parse_llm_prompt_response(response)
    
    return cleaned_prompt


def parse_llm_prompt_response(response: str) -> str:
    """
    Parse and clean LLM response to extract just the modified prompt.
    
    Handles cases where LLM adds explanations or markdown formatting.
    """
    response = response.strip()
    
    # Remove markdown code blocks if present
    if response.startswith("```"):
        lines = response.split("\n")
        # Remove first line (```) and last line (```)
        response = "\n".join(lines[1:-1]).strip()
    
    # Remove common prefixes LLM might add
    prefixes_to_remove = [
        "Modified prompt:",
        "Here's the modified prompt:",
        "The modified prompt is:",
        "Prompt:",
    ]
    for prefix in prefixes_to_remove:
        if response.lower().startswith(prefix.lower()):
            response = response[len(prefix):].strip()
    
    # If response contains explanation (e.g., "The prompt is: ... because...")
    # Try to extract just the prompt part
    if "because" in response.lower() or "this" in response.lower():
        # Look for the longest sentence/paragraph (likely the prompt)
        sentences = response.split(".")
        if len(sentences) > 1:
            # Take the longest sentence as the prompt
            longest = max(sentences, key=len)
            if len(longest) > 50:  # Reasonable prompt length
                response = longest.strip()
    
    # Fallback: Return full response if parsing fails
    # Better to have a prompt with extra text than no prompt
    return response.strip()
```

---

### 3. Context Builder

#### 3.1 Overview

Builds rich context for LLM while limiting token usage by summarizing older conversation history.

#### 3.2 Context Components

**Required Context:**
- Original prompt
- Scene plan summary (style, characters, scenes, mood)
- User instruction
- Recent conversation (last 2-3 messages)

**Optional Context (if available):**
- Reference images description
- Previous regeneration history

#### 3.3 Conversation History Management

**Storage:**
- Store conversation history in `clip_regenerations.conversation_history` JSONB column
- Format: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- Store only last 5 messages in active conversation (in-memory during session)
- Persist to database when regeneration completes
- Include only last 2-3 messages in LLM prompt (to stay within token budget)
- Summarize older messages if needed: "Previous requests: made clip brighter, added motion"

**Storage Location:**
- Database: `clip_regenerations` table (created in PRD 3)
- Column: `conversation_history` (JSONB)
- Persisted when regeneration completes
- Loaded when user continues conversation (future enhancement)

**Implementation:**
```python
def build_conversation_context(
    conversation_history: List[Dict[str, str]],
    max_messages: int = 3
) -> str:
    """
    Build conversation context for LLM.
    
    Includes only last max_messages, summarizes older if needed.
    """
    if len(conversation_history) <= max_messages:
        return format_messages(conversation_history)
    
    recent = conversation_history[-max_messages:]
    older = conversation_history[:-max_messages]
    
    summary = summarize_older_messages(older)
    recent_text = format_messages(recent)
    
    return f"{summary}\n\n{recent_text}"
```

#### 3.4 Implementation

**Location:** `modules/clip_regenerator/context_builder.py`

```python
def build_llm_context(
    original_prompt: str,
    scene_plan: ScenePlan,
    user_instruction: str,
    conversation_history: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Build context dictionary for LLM prompt template.
    """
    return {
        "original_prompt": original_prompt,
        "style_info": scene_plan.style.visual_style,
        "character_names": [c.name for c in scene_plan.characters],
        "scene_locations": [s.location for s in scene_plan.scenes],
        "mood": scene_plan.style.mood,
        "user_instruction": user_instruction,
        "recent_conversation": build_conversation_context(conversation_history)
    }
```

---

### 4. Regeneration Process

#### 4.1 Main Orchestration

**Location:** `modules/clip_regenerator/process.py`

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
    1. Load original clip data from job_stages.metadata
    2. Check for template match
    3. If template: Apply transformation
    4. If no template: Call LLM to modify prompt
    5. Generate new clip (reuse Video Generator)
    6. Return new clip URL
    """
    # Step 1: Load data
    clips = await load_clips_from_job_stages(job_id)
    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
    scene_plan = await load_scene_plan_from_job_stages(job_id)
    
    original_clip = clips.clips[clip_index]
    original_prompt = clip_prompts.clip_prompts[clip_index]
    
    # Step 2: Check template
    template_match = match_template(user_instruction)
    
    if template_match:
        # Step 3: Apply template
        modified_prompt = apply_template(original_prompt.prompt, template_match)
        cost_estimate = estimate_video_cost(original_clip.target_duration)
    else:
        # Step 4: LLM modification
        context = build_llm_context(
            original_prompt.prompt,
            scene_plan,
            user_instruction,
            conversation_history or []
        )
        modified_prompt = await modify_prompt_with_llm(
            original_prompt.prompt,
            user_instruction,
            context,
            conversation_history or []
        )
        cost_estimate = estimate_llm_cost() + estimate_video_cost(original_clip.target_duration)
    
    # Step 5: Generate new clip
    new_clip = await generate_single_clip(
        job_id=job_id,
        clip_index=clip_index,
        modified_prompt=modified_prompt,
        original_prompt=original_prompt
    )
    
    return RegenerationResult(
        clip=new_clip,
        modified_prompt=modified_prompt,
        template_used=template_match.template_id if template_match else None,
        cost=cost_estimate
    )
```

---

### 5. Regeneration API

#### 5.1 Endpoint

**POST /api/v1/jobs/{job_id}/clips/{clip_index}/regenerate**

**Purpose:** Regenerate a single clip based on user instruction.

**Concurrent Regeneration Prevention:**
- Check job status before allowing regeneration
- Use PostgreSQL row-level locking: `SELECT ... FOR UPDATE`
- If job status is `regenerating`: Return 409 Conflict
- Error message: "A regeneration is already in progress for this job. Please wait for it to complete."
- Prevents race conditions from multiple tabs/browser sessions

**Request:**
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
  "status": "queued",
  "template_matched": "nighttime"
}
```

#### 5.2 SSE Events

**Event Types:**
- `regeneration_started` - Regeneration queued (sequence: 1)
- `template_matched` - Template transformation applied (skip LLM) (sequence: 2)
- `prompt_modified` - LLM modified prompt (or template applied) (sequence: 3)
- `video_generating` - Video generation in progress (with progress %) (sequence: 4+)
- `regeneration_complete` - New clip URL available (sequence: final)
- `regeneration_failed` - Error occurred (sequence: final)

**Event Format:**
```json
{
  "event_type": "regeneration_started",
  "sequence": 1,
  "timestamp": "2025-01-15T10:30:00Z",
  "data": {...}
}
```

**Progress Tracking:**
- Template check: 0-5% progress
- LLM modification (if needed): 5-10% progress
- Video generation: 10-60% progress (single clip)

**Note:** Sequence numbers help frontend handle out-of-order events (rare but possible with SSE).

#### 5.3 Error Handling

**HTTP Status Codes:**
- 404: Job or clip not found
- 403: Job belongs to different user
- 400: Invalid clip_index or instruction
  - Validate `0 <= clip_index < total_clips`
  - Validate instruction is not empty
- 409: Concurrent regeneration in progress (job status is `regenerating`)
- 429: Too many regenerations (rate limit)

**Error Response Format:**
```json
{
  "error": "concurrent_regeneration",
  "message": "A regeneration is already in progress for this job. Please wait for it to complete.",
  "job_id": "uuid",
  "current_status": "regenerating"
}
```

---

### 6. ClipChatbot UI Component

#### 6.1 Component Structure

**Location:** `project/frontend/components/ClipChatbot.tsx`

**Props:**
```typescript
interface ClipChatbotProps {
  jobId: string
  clipIndex: number
  onRegenerationComplete: (newVideoUrl: string) => void
}
```

#### 6.2 Requirements

**Chat Interface:**
- Message list (scrollable)
- Input field with send button
- Loading indicator during processing
- Cost estimate display (before regeneration)
- Cancel button (during regeneration)

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
│  │      Estimated cost: $0.15"        │ │
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

---

## Implementation Tasks

### Task 1: Template System
- [ ] Create `template_matcher.py` module
- [ ] Define template dictionary with transformations
- [ ] Implement `match_template()` function
- [ ] Implement `apply_template()` function
- [ ] Add unit tests

### Task 2: LLM Modifier
- [ ] Create `llm_modifier.py` module
- [ ] Implement system prompt
- [ ] Implement user prompt template
- [ ] Add token budget enforcement (max 2000 tokens)
- [ ] Implement prompt parsing/cleaning function
- [ ] Integrate with OpenAI/Claude API
- [ ] Add retry logic
- [ ] Add unit tests for prompt parsing

### Task 3: Context Builder
- [ ] Create `context_builder.py` module
- [ ] Implement `build_llm_context()` function
- [ ] Implement conversation history management
- [ ] Add summarization for older messages
- [ ] Add unit tests

### Task 4: Regeneration Process
- [ ] Create `process.py` orchestration
- [ ] Integrate template matcher
- [ ] Integrate LLM modifier
- [ ] Integrate with Video Generator
- [ ] Add error handling
- [ ] Add unit tests

### Task 5: Regeneration API
- [ ] Add `POST /clips/{idx}/regenerate` endpoint
- [ ] Add authentication and authorization
- [ ] Add concurrent regeneration prevention (database locking)
- [ ] Add clip_index bounds validation
- [ ] Integrate with regeneration process
- [ ] Add SSE events with sequence numbers
- [ ] Add cost estimation
- [ ] Add API tests (including concurrent regeneration test)

### Task 6: ClipChatbot UI
- [ ] Create `ClipChatbot.tsx` component
- [ ] Implement chat interface
- [ ] Add SSE connection for progress
- [ ] Add cost estimation display
- [ ] Add error handling
- [ ] Test with real API

---

## Testing Strategy

### Unit Tests
- Template matching logic
- Template application
- LLM prompt modification
- Context building
- Conversation history management

### Integration Tests
- Regeneration API endpoint
- Template → Video Generator flow
- LLM → Video Generator flow
- SSE event publishing

### E2E Tests
- Complete flow: Chat → Regenerate → New clip

---

## Success Criteria

### Functional
- ✅ Template system matches common instructions
- ✅ LLM modifies prompts correctly
- ✅ Regeneration API works end-to-end
- ✅ Chatbot UI displays conversation and progress

### Performance
- ✅ Template matching: <10ms
- ✅ LLM modification: <10s
- ✅ Cost estimates accurate (±20%)

### Quality
- ✅ Template transformations produce good results
- ✅ LLM modifications maintain style consistency
- ✅ Error handling graceful

---

## Dependencies

### External Services
- OpenAI GPT-4o or Claude 3.5 Sonnet (for prompt modification)
- Replicate (for video generation, reused)

### Internal Modules
- Video Generator (single clip generation)
- Data Loader (from Part 1)
- API Gateway (regeneration endpoint)

---

## Risks & Mitigations

### Risk 1: Template Quality
**Risk:** Template transformations don't produce good results  
**Mitigation:** Test templates extensively, allow LLM fallback

### Risk 2: LLM Cost
**Risk:** LLM calls expensive for many regenerations  
**Mitigation:** Template system reduces LLM calls by 30-40%

### Risk 3: Context Token Usage
**Risk:** Large context increases LLM costs  
**Mitigation:** Limit conversation history to last 2-3 messages

---

## Next Steps

After completing Part 2, proceed to:
- **Part 3:** Integration & Polish (composer integration, full recomposition, E2E testing)

