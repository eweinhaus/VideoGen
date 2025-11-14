# AI Video Generation Pipeline - Product Requirements Document

## Executive Summary

This document defines the MVP requirements for an AI-powered music video generation pipeline. The system takes an audio file and creative prompt as input, and produces a complete, beat-synchronized music video with consistent visual style across multiple clips.

**Target**: MVP delivery in 48 hours  
**Budget Target**: $1.50 per minute of video  
**Minimum Clips**: 3 clips per video  
**Tech Stack**: Python (FastAPI), Render deployment, AWS S3 storage

---

## System Architecture Overview

The pipeline consists of 8 modular components, each implemented as a separate module in the repository:

1. **Frontend** (`frontend/`) - User interface and job management
2. **API Gateway** (`api/`) - REST API and WebSocket server
3. **Audio Parser** (`audio_parser/`) - Audio analysis and beat detection
4. **Scene Planner** (`scene_planner/`) - Video planning and script generation
5. **Reference Generator** (`reference_generator/`) - Reference image generation
6. **Prompt Generator** (`prompt_generator/`) - Video prompt optimization
7. **Video Generator** (`video_generator/`) - Video clip generation
8. **Composer** (`composer/`) - Video stitching and audio sync

Each module is independently testable and communicates via well-defined interfaces.

---

## Module 1: Frontend (`frontend/`)

### Purpose
User-facing web interface for uploading audio, entering prompts, and viewing generated videos.

### Requirements

#### Input Collection
- Audio file upload (MP3, WAV) with validation
- Creative prompt text input (required)
- Optional parameters:
  - Style preferences (text)
  - Duration hint (number, seconds)
  - Mood preference (text)

#### Job Management
- Generate unique job ID (UUID) on submission
- Display job status (queued, processing, complete, error)
- Real-time progress updates via WebSocket/SSE
- Cost tracking display per stage

#### Video Display
- Progressive rendering: show clips as they complete
- Final composed video player
- Individual clip previews
- Export functionality (MP4/MOV download)

#### UI Components
- File upload component with drag-and-drop
- Text input for creative prompt
- Progress indicator with stage names
- Cost tracker component
- Video player with controls
- Export button

### Technical Stack
- React or Vue.js
- WebSocket client for real-time updates
- File upload handling
- Video player (HTML5)

### Success Criteria
- User can upload audio and submit prompt
- Real-time progress updates visible
- Cost tracking displayed per stage
- Generated video plays correctly
- Export downloads working file

---

## Module 2: API Gateway (`api/`)

### Purpose
REST API server and WebSocket handler for coordinating pipeline execution.

### Requirements

#### REST Endpoints
- `POST /api/jobs` - Create new generation job
  - Accepts: audio file, prompt, optional parameters
  - Returns: job_id, status
- `GET /api/jobs/{job_id}` - Get job status
  - Returns: status, progress, current stage
- `GET /api/jobs/{job_id}/clips` - Get individual clips
  - Returns: array of clip metadata
- `GET /api/jobs/{job_id}/video` - Get final composed video
  - Returns: video file or URL

#### WebSocket
- Connection endpoint: `/ws/jobs/{job_id}`
- Broadcasts progress updates:
  - Stage name
  - Progress percentage (0-100)
  - Current message
  - Clip index (if applicable)
  - Cost per stage
- **Reconnection Logic**: 
  - Client automatically reconnects on disconnect
  - Exponential backoff for reconnection attempts
  - Fallback to polling (`GET /api/jobs/{job_id}`) if WebSocket unavailable

#### Job Queue
- Celery integration for background processing
- Redis for job queue and result storage
- Job state management (queued → processing → complete/error)

#### Error Handling
- Validation errors returned immediately
- Job errors stored and retrievable
- Graceful degradation for failed stages

### Technical Stack
- FastAPI framework
- Celery for background tasks
- Redis for queue
- WebSocket support (FastAPI WebSocket)
- AWS S3 client for file storage

### Success Criteria
- Jobs can be created and tracked
- WebSocket delivers real-time updates
- Background processing works correctly
- Errors are handled gracefully

---

## Module 3: Audio Parser (`audio_parser/`)

### Purpose
Analyze audio file to extract musical features, detect beats, transcribe lyrics, and determine clip boundaries.

### Requirements

#### Beat Detection
- Use Librosa for beat tracking
- Output beat timestamps array
- Calculate tempo (BPM)
- Confidence scoring for beat detection
- **Fallback**: If beat detection fails, use tempo-based boundaries (evenly spaced at tempo intervals)

#### Lyrics Transcription
- Use OpenAI Whisper API (via Replicate) for transcription
- Output timed lyrics with timestamps
- Language detection
- Handle instrumental tracks (empty lyrics)
- **Fallback**: If transcription fails, proceed with empty lyrics (instrumental track assumed)

#### Audio Features (Simplified for MVP)
- Calculate loudness/energy
- Basic mood analysis (energy level: 0-1 scale)
- Extract tempo (BPM) - required for fallback

#### Clip Boundary Generation
- Create beat-aligned clip boundaries (not fixed duration)
- Typical clip length: 3-7 seconds
- Minimum 3 clips for MVP
- Output boundaries as array of {start, end, duration}
- **Fallback Strategy**: If beat detection fails, generate boundaries based on tempo:
  - Calculate interval = 60 / BPM (seconds per beat)
  - Create boundaries at regular intervals (every 4-8 beats)
  - Ensure minimum 3 clips

#### Validation
- Verify beat detection succeeded
- Check if fallback was used
- Output confidence score
- Validate clip boundaries are valid (non-overlapping, within audio duration)

### Technical Stack
- Librosa for audio analysis
- Replicate Whisper API for transcription
- NumPy for calculations
- Audio file handling (librosa)

### Input/Output
- Input: Audio file path
- Output: JSON with lyrics, beats, tempo, features, boundaries, validation

### Success Criteria
- Accurate beat detection for most songs
- Successful lyrics transcription (or graceful handling of instrumental tracks)
- Clip boundaries align with beats (or tempo-based fallback)
- Fallback works for instrumental tracks and beat detection failures

---

## Module 4: Scene Planner (`scene_planner/`)

### Purpose
Generate comprehensive video plan including characters, scenes, objects, style, and detailed clip scripts.

### Requirements

#### Video Planning
- Generate high-level video summary
- Create character definitions with physical attributes
- Define scenes with environment details
- Identify objects with attributes
- Extract style information (colors, mood, lighting)

#### Clip Script Generation
- Create detailed script for each clip (minimum 3)
- Align scripts to beat boundaries from audio parser
- Include lyrics context for each clip
- Specify visual descriptions, motion, camera angles
- Assign characters and scenes to clips

#### Transition Planning
- Plan transitions between clips
- Support 2-3 transition types for MVP:
  - Crossfade (smooth blend)
  - Cut (hard cut at beat)
  - Fade (fade to black/white)
- Output transition specifications

#### Style Consistency
- Generate color palette (hex codes)
- Define visual style description
- Specify mood and lighting
- Ensure consistency across all clips

#### Validation
- Verify all required outputs present
- Check clip scripts match clip boundaries
- Validate transition plans

### Technical Stack
- OpenAI GPT-4 or Claude API for planning
- JSON schema validation
- Prompt engineering for consistency

### Input/Output
- Input: User prompt, audio parsing output
- Output: JSON with video summary, characters, scenes, objects, style, clip scripts, transitions

### Success Criteria
- Detailed clip scripts generated
- Characters/scenes consistently defined
- Transitions planned correctly
- Style information extracted

---

## Module 5: Reference Generator (`reference_generator/`)

### Purpose
Generate a single reference image for visual consistency across video clips (MVP: minimal approach).

### Requirements

#### Reference Photo Strategy (MVP: Single Reference Photo)
- **1 style reference image** - Overall aesthetic/visual style reference
- 1 color palette (non-photo, hex codes from scene planning)
- **Fallback**: If reference photo generation fails, proceed with text-only prompts (no reference image)

#### Image Generation
- Use Replicate Stable Diffusion XL
- Generate single style reference image based on scene planning style_info
- Sequential processing (no parallelization for MVP)
- Cache mechanism for similar reference photos

#### Reference Photo Generation
- Generate style reference: Based on visual_style, mood, and color_palette from scene planning
- Description combines: visual_style + mood + lighting + color_descriptions
- Output single image path

#### Caching
- Generate cache keys based on description hash
- Check cache before generating new images
- Store cache keys in output for reuse

#### Validation
- Verify reference photo generated successfully
- Track failed generations
- Retry failed generations (max 2 retries)
- **Fallback**: If all retries fail, set image_path to null and proceed without reference image

### Technical Stack
- Replicate API (Stable Diffusion XL)
- ControlNet for reference image support
- Image processing (PIL/Pillow)
- Caching mechanism (Redis or file-based)

### Input/Output
- Input: Scene planning output
- Output: JSON with reference photo object (single), color palette, validation

### Success Criteria
- Reference photo generated successfully (or fallback to null)
- Image matches scene planning style description
- Caching reduces redundant generations
- Pipeline continues even if reference photo generation fails

---

## Module 6: Prompt Generator (`prompt_generator/`)

### Purpose
Create optimized video generation prompts for each clip, incorporating reference photos and style information.

### Requirements

#### Prompt Optimization
- Generate text prompt for video generation API
- Incorporate reference photo paths
- Include style parameters (colors, aesthetic, mood, lighting)
- Add motion parameters (camera, subject motion, speed)
- Specify camera parameters (shot type, movement, angle)
- Include transition hints for composition

#### Style Consistency
- Embed color palette in prompt
- Reference style descriptions from scene planning
- Include visual style keywords consistently
- Maintain aesthetic coherence across clips

#### Processing
- Process clips sequentially for MVP
- Generate one prompt per clip
- Output exact duration from beat boundaries
- Include all reference photo paths (excluding color palette)

#### Prompt Engineering
- Combine clip script visual description
- Add style parameters
- Include reference photo context
- Optimize for video generation API format

### Technical Stack
- OpenAI GPT-4 or Claude API for prompt generation
- Text processing and formatting
- JSON schema validation

### Input/Output
- Input: Clip script, reference photos, video summary, style info, transition info
- Output: JSON with video prompt, style/motion/camera parameters, duration, reference paths

### Success Criteria
- Prompts optimized for video generation
- Style consistency maintained
- Reference photos properly referenced
- Duration matches beat boundaries

---

## Module 7: Video Generator (`video_generator/`)

### Purpose
Generate individual video clips using AI video generation API.

### Requirements

#### Video Generation
- Call Replicate video generation API (Stable Video Diffusion or similar)
- Pass optimized prompt and reference photo (if available)
- **Duration Handling**: 
  - Request duration from beat boundaries
  - **Note**: Most video APIs have fixed durations (e.g., 4s, 5s, 10s)
  - If API doesn't support exact duration, request closest available duration
  - Document actual API duration options and limitations
- Support reference images via API (ControlNet/IP-Adapter) if available
- **Fallback**: If reference photo unavailable, use text-only prompt

#### Duration Strategy
- **Verify API Duration Options**: Check available durations (e.g., 4s, 5s, 10s)
- **Request Strategy**: Request closest available duration to target
- **Trimming Strategy**: Composer will trim clips to exact beat boundaries
- **Looping Strategy**: If clip is shorter than needed, loop the clip (repeat frames) to fill duration
- **Tolerance**: Accept clips within ±2 seconds of target duration

#### Retry Logic
- Exponential backoff for failed generations
- Maximum 3 retries per clip
- Individual clip failure handling (don't regenerate all clips)
- Track retry count in output

#### Cost Tracking
- Track API cost per clip
- Record generation time
- Store cost in metadata

#### Validation
- Verify clip duration is within tolerance (±2 seconds)
- Basic quality check (file exists, valid format)
- Check resolution and frame rate
- Output validation results including duration difference

#### Progress Updates
- Send progress update after each clip completes
- Include clip index, status, cost, actual duration
- Update frontend via WebSocket

#### Error Handling
- Handle API failures gracefully
- Log errors with details
- Return error status and message
- Continue processing other clips if one fails
- **Partial Success**: If at least 2 clips succeed, proceed to composition (minimum 3 clips required, but allow 2 for MVP edge cases)

### Technical Stack
- Replicate API client
- Video file handling
- Retry logic implementation
- Cost tracking system

### Input/Output
- Input: Video prompt object, reference photo paths
- Output: JSON with clip index, video path, metadata, cost, status, validation

### Success Criteria
- Video clips generated successfully
- Duration matches requested (within tolerance)
- Cost tracked accurately
- Retry logic handles failures
- Individual clip failures don't stop pipeline

---

## Module 8: Composer (`composer/`)

### Purpose
Stitch video clips together, sync audio, and apply transitions.

### Requirements

#### Clip Processing
- **Duration Handling**:
  - Trim clips to exact durations (prioritize staying on beat)
  - **Never extend clips** (only truncate if too long)
  - **Looping Strategy**: If clip is shorter than needed after trimming:
    - Loop the clip (repeat frames) to fill required duration
    - Use seamless loop if possible (detect loop point)
    - Fallback: Simple frame repetition
- Normalize frame rate across all clips (target: 30 FPS)
- Normalize resolution (target: 1080p minimum)
- Handle clips that are too short (loop) or too long (trim)

#### Audio Synchronization
- Sync original audio with video
- Ensure no audio-video drift
- Match total video duration to audio duration exactly
- Verify sync accuracy
- **Fallback**: If duration mismatch > 1 second, adjust video speed slightly (within ±5%) to match audio

#### Transition Application
- Apply transitions from scene planning:
  - Crossfade: Blend between clips (default: 0.5s duration)
  - Cut: Hard cut at beat boundary (no transition)
  - Fade: Fade to black/white (default: 0.5s duration)
- Apply transitions at beat boundaries
- Support transition duration specification
- **Fallback**: If transition fails, use simple cut

#### Video Composition
- Stitch clips in order
- Maintain beat alignment
- Handle clips trimmed to fit boundaries
- Handle clips looped to fill duration
- Output final composed video (MP4 format)
- **Partial Success**: If some clips failed, compose with available clips (minimum 2 clips for MVP edge cases)

#### Validation
- Verify audio sync succeeded
- Check final duration matches audio (within 0.1s tolerance)
- Calculate sync drift (should be < 0.1s)
- Track number of clips trimmed
- Track number of clips looped

### Technical Stack
- FFmpeg for video processing
- MoviePy or similar for Python integration
- Audio processing libraries
- Video encoding/decoding

### Input/Output
- Input: Generated clips array, original audio, beat timestamps, clip boundaries, transition plans
- Output: JSON with composed video path, metadata, clips array, validation

### Success Criteria
- Final video matches audio duration exactly
- Transitions applied correctly
- No audio-video drift
- Video plays smoothly
- Beat alignment maintained

---

## Cross-Module Requirements

### Storage
- AWS S3 for all intermediate and final files
- Lifecycle policy: 24 hours for intermediates, 7 days for finals
- File organization by job_id

### Error Handling
- Validation at each stage
- Graceful failure recovery
- Error logging and tracking
- User-friendly error messages

### Cost Management
- Track cost per stage
- Display cost in UI
- Budget target: $1.50 per minute for MVP
- Cost breakdown per component

### Performance
- Sequential reference photo generation (MVP - no parallelization)
- Sequential video generation (MVP - no parallelization)
- Progressive rendering in frontend
- Background job processing

### Deployment
- Render platform for API and workers
- AWS S3 for storage
- Redis for job queue
- WebSocket support for real-time updates

---

## MVP Success Criteria

1. **End-to-End Functionality**
   - User can upload audio and prompt
   - Pipeline generates complete video
   - Video plays correctly with synced audio

2. **Quality Requirements**
   - Minimum 3 clips per video
   - Beat-aligned transitions
   - Consistent visual style
   - 1080p resolution, 30 FPS

3. **Performance**
   - 30-second video: < 5 minutes generation
   - 60-second video: < 10 minutes generation
   - Real-time progress updates

4. **Cost**
   - Under $1.50 per minute of video
   - Cost tracking visible in UI

5. **Reliability**
   - 90%+ successful generation rate
   - Individual clip failure handling
   - Graceful error recovery

---

## Future Enhancements (Post-MVP)

- Parallel video generation
- Batch prompt generation
- Advanced transitions (wipe, dissolve)
- LoRA models for style consistency
- Previous clip context for continuity
- Beat timing within clips
- Multiple aspect ratios
- Text overlays
- Voiceover generation
- Advanced caching strategies
- Song structure detection (intro/verse/chorus/bridge/outro)
- Multiple reference photos (character, scene, object references)
- Instrument detection and prominence analysis
- Musical key extraction
- Advanced mood analysis (valence, arousal)

---

## Technical Decisions Summary

- **Tech Stack**: Python (FastAPI), React frontend
- **Deployment**: Render (API + workers), AWS S3 (storage)
- **Audio Parsing**: Librosa + Whisper API (beat detection + tempo only for MVP)
- **Video Generation**: Replicate (Stable Video Diffusion or similar)
- **Image Generation**: Replicate (Stable Diffusion XL)
- **Job Queue**: Celery + Redis
- **Reference Photos**: Single style reference photo (MVP)
- **Transitions**: Crossfade + Cut for MVP
- **Budget**: $1.50 per minute (MVP)
- **Fallbacks**: 
  - Tempo-based boundaries if beat detection fails
  - Text-only prompts if reference photo generation fails
  - Partial video composition if some clips fail (minimum 2 clips)
  - Polling fallback if WebSocket unavailable
- **Duration Strategy**: Request closest API duration, trim/loop in composer

---

## Repository Structure

```
VideoGen/
├── frontend/          # React frontend application
├── api/              # FastAPI server and WebSocket
├── audio_parser/     # Audio analysis module
├── scene_planner/    # Video planning module
├── reference_generator/  # Reference image generation
├── prompt_generator/ # Prompt optimization module
├── video_generator/  # Video clip generation
├── composer/         # Video composition and sync
├── shared/           # Shared utilities and schemas
├── tests/            # Integration and unit tests
├── requirements.txt  # Python dependencies
└── README.md         # Setup and deployment instructions
```

Each module is independently testable and follows consistent interface patterns.

