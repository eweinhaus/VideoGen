# Audio Parser PRD Split - Detailed Content Outline

## PRD 1: Audio Parser - Overview & Integration (~250 lines)

### Purpose
High-level understanding of the module, its role in the pipeline, and how it integrates with existing systems.

### Sections:

1. **Header & Metadata**
   - Version, date, priority
   - Budget constraints
   - Timeline and dependencies

2. **Executive Summary**
   - What the module does
   - Key technologies used
   - Role in pipeline

3. **Purpose & Responsibilities**
   - 6 core functions (beat detection, structure, lyrics, mood, boundaries, caching)
   - Why each is important

4. **Architecture Overview**
   - High-level flow diagram
   - Component file structure
   - Processing pipeline visualization
   - Progress markers (2%, 4%, 6%, etc.)

5. **Input/Output Specification**
   - Input: job_id, audio_url
   - Input validation rules
   - Output: AudioAnalysis model structure
   - Example JSON output
   - Data model relationships

6. **Integration Points** (DETAILED)
   - **Orchestrator Integration**:
     - Current state (stub location)
     - Required implementation code
     - Function signatures
     - Database storage pattern
   - **Progress Updates**:
     - SSE event structure
     - Progress percentage mapping
     - Message format
   - **Database Storage**:
     - Table/column details
     - Migration reference
     - Storage strategy
     - When to store
   - **Cost Tracking**:
     - Cost calculation formula
     - Budget check flow
     - Integration with CostTracker
     - Error handling on budget exceed

7. **Error Handling Strategy**
   - Component-level failures (summary)
   - Module-level failures
   - Error decision tree (high-level)
   - Error types used
   - When module fails vs. continues

8. **Success Criteria**
   - Functional requirements
   - Quality metrics
   - Performance targets
   - Integration requirements

9. **Boundary Ownership Clarification**
   - Audio Parser responsibilities
   - Scene Planner responsibilities
   - Composer responsibilities
   - Data flow between modules

10. **Cross-References**
    - Links to Component PRD (detailed specs)
    - Links to Implementation PRD (how to build)

---

## PRD 2: Audio Parser - Component Specifications (~350 lines)

### Purpose
Detailed technical specifications for each component. This is the "how it works" document.

### Sections:

1. **Header & Cross-References**
   - Link to Overview PRD
   - Link to Implementation PRD
   - Component overview table

2. **Component 1: Beat Detection (`beat_detection.py`)**
   - Purpose and role
   - **Algorithm Details**:
     - Librosa functions used
     - Parameters and settings
     - Step-by-step process
   - **Fallback Strategy**:
     - When fallback triggers
     - Fallback algorithm
     - Confidence calculation
   - **Output Specification**:
     - Return type
     - Data structure
     - Validation rules
   - **Performance Target**: <10s
   - **Edge Cases**:
     - No beats detected
     - Very slow/fast tempo
     - Variable tempo
   - **Code Example** (pseudocode or actual code)

3. **Component 2: Structure Analysis (`structure_analysis.py`)**
   - Purpose and role
   - **Algorithm Details**:
     - Feature extraction (chroma)
     - Recurrence matrix construction
     - Clustering algorithm (Ward linkage, 8 clusters)
     - Segment classification heuristics
     - Step-by-step with parameters
   - **Fallback Strategy**:
     - When fallback triggers
     - Uniform segmentation algorithm
   - **Output Specification**:
     - SongStructure model
     - Energy calculation
   - **Performance Target**: <15s
   - **Edge Cases**:
     - Songs with no clear structure
     - Very short songs
     - Songs with many sections
   - **Code Example**

4. **Component 3: Lyrics Extraction (`lyrics_extraction.py`)**
   - Purpose and role
   - **Algorithm Details**:
     - Whisper API integration
     - Request parameters
     - Response parsing
     - Word-level timestamp extraction
   - **Retry Logic**:
     - Exponential backoff details
     - Retry conditions
     - Max attempts
   - **Cost Tracking**:
     - Cost calculation
     - Budget check before call
     - Tracking after success
   - **Fallback Strategy**:
     - When fallback triggers
     - Empty lyrics handling
   - **Output Specification**:
     - Lyric model structure
     - Timestamp format
   - **Performance Target**: <30s
   - **Edge Cases**:
     - Instrumental tracks
     - Non-English lyrics
     - Very long songs
   - **Code Example**

5. **Component 4: Mood Classification (`mood_classifier.py`)**
   - Purpose and role
   - **Algorithm Details**:
     - Feature extraction (energy, spectral centroid, rolloff, chroma)
     - Rule definitions with thresholds
     - Classification logic (step-by-step)
     - Confidence calculation
   - **Fallback Strategy**:
     - When fallback triggers
     - Default mood selection
   - **Output Specification**:
     - Mood model structure
     - Primary/secondary selection
     - Energy level calculation
   - **Performance Target**: <1s
   - **Edge Cases**:
     - Ambiguous moods
     - Mixed genres
   - **Code Example**

6. **Component 5: Clip Boundaries (`boundaries.py`)**
   - Purpose and role
   - **Algorithm Details**:
     - Beat-aligned boundary generation
     - Duration calculation
     - Edge case handling
     - Step-by-step process
   - **Rules & Constraints**:
     - 4-8s duration
     - Minimum 3 clips
     - Maximum configurable
     - Beat alignment tolerance
   - **Fallback Strategy**:
     - Tempo-based boundaries
     - When to use
   - **Output Specification**:
     - ClipBoundary model
     - Validation rules
   - **Performance Target**: <1s
   - **Edge Cases**:
     - Songs <12s
     - Beat interval >8s
     - Variable tempo
     - No beats detected
   - **Code Example**

7. **Component 6: Caching (`cache.py`)**
   - Purpose and role
   - **Strategy Details**:
     - Redis-only for MVP
     - Cache key format
     - TTL settings
   - **Cache Flow** (step-by-step):
     - Hash extraction from URL
     - Cache lookup before download
     - Download if needed
     - Hash calculation
     - Cache lookup after download
     - Cache storage
   - **Performance Target**: <1s cache hit
   - **Edge Cases**:
     - Hash not in URL
     - Cache miss
     - Redis unavailable
   - **Code Example**

8. **Component Dependencies**
   - Which components depend on which
   - Execution order
   - Data flow between components

9. **Component Testing Requirements**
   - Unit test requirements per component
   - Mock requirements
   - Test data examples

---

## PRD 3: Audio Parser - Implementation Guide (~250 lines)

### Purpose
Step-by-step guide for implementing the module. The "how to build it" document.

### Sections:

1. **Header & Cross-References**
   - Link to Overview PRD
   - Link to Component PRD
   - Implementation timeline

2. **Implementation Phases** (DETAILED)
   - **Phase 0: Model Creation**
     - Files to create
     - Models to define
     - Error classes to add
     - Testing requirements
     - Checklist
   - **Phase 1: Foundation & Integration**
     - Directory structure
     - File creation order
     - Orchestrator integration steps
     - Testing checklist
   - **Phase 2: Core Components**
     - Implementation order
     - Dependencies between components
     - Testing approach
     - Checklist
   - **Phase 3: Lyrics & Caching**
     - External API integration
     - Caching implementation
     - Cost tracking integration
     - Testing checklist
   - **Phase 4: Orchestrator Integration**
     - Code changes needed
     - Progress update implementation
     - Error handling integration
     - Testing checklist
   - **Phase 5: Testing & Validation**
     - Test types
     - Test data preparation
     - Manual testing scenarios
     - Checklist

3. **Testing Requirements** (DETAILED)
   - **Unit Tests**:
     - Per-component test requirements
     - Mock setup
     - Test data examples
     - Assertions needed
   - **Integration Tests**:
     - Full flow testing
     - Cache testing
     - Database testing
     - Cost tracking testing
   - **End-to-End Tests**:
     - API Gateway integration
     - Frontend integration
     - Progress update verification
   - **Manual Testing**:
     - Test cases by genre
     - Test cases by duration
     - Error scenario testing
     - Performance validation

4. **Dependencies**
   - **Python Packages**:
     - Exact versions
     - Installation instructions
     - Why each is needed
   - **Shared Components**:
     - Which components to use
     - How to import
     - Usage examples
   - **External Services**:
     - OpenAI Whisper API setup
     - Redis setup
     - Supabase Storage setup

5. **Code Patterns & Examples**
   - **Error Handling Pattern**:
     - How to raise errors
     - How to use fallbacks
     - Error propagation
   - **Cost Tracking Pattern**:
     - Budget check before API calls
     - Cost tracking after success
     - Error handling
   - **Progress Update Pattern**:
     - How to send SSE events
     - Progress percentage calculation
   - **Caching Pattern**:
     - Cache key generation
     - Cache lookup
     - Cache storage
   - **Retry Pattern**:
     - Using retry decorator
     - Exponential backoff
     - Error handling

6. **File Structure**
   - Complete directory tree
   - File purposes
   - Import structure

7. **Known Limitations & Future Enhancements**
   - MVP limitations (what we're NOT doing)
   - Future enhancements (post-MVP)
   - Migration path

8. **Troubleshooting Guide**
   - Common issues
   - Debugging tips
   - Performance optimization tips

9. **Implementation Checklist**
   - Master checklist for all phases
   - Dependencies between tasks
   - Estimated time per task

---

## Cross-Reference Strategy

Each PRD should have:
- **At the top**: Links to other PRDs
- **In relevant sections**: "See Component PRD for details" or "See Implementation PRD for steps"
- **Consistent terminology**: Same names, same concepts

## File Naming

- `PRD_audio_parser_overview.md` - Overview & Integration
- `PRD_audio_parser_components.md` - Component Specifications  
- `PRD_audio_parser_implementation.md` - Implementation Guide

