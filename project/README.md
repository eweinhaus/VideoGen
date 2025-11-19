# AI Music Video Generation Pipeline

An AI-powered pipeline that generates professional, beat-synchronized music videos with consistent visual style informed by music video director expertise.

## Project Structure

```
project/
├── frontend/              # Module 1: Next.js 14 + TypeScript frontend
├── backend/
│   ├── api_gateway/      # Module 2: FastAPI REST API + SSE + Job Queue
│   ├── modules/
│   │   ├── audio_parser/         # Module 3: Audio analysis (beats, lyrics, mood)
│   │   ├── scene_planner/       # Module 4: Video planning with director knowledge
│   │   ├── reference_generator/ # Module 5: SDXL reference image generation
│   │   ├── prompt_generator/    # Module 6: Optimized video prompts
│   │   ├── video_generator/     # Module 7: Parallel video clip generation
│   │   ├── composer/            # Module 8: FFmpeg video composition
│   │   └── clip_regenerator/   # Clip chatbot: Data loading for clip regeneration
│   └── shared/           # Shared utilities and common code
└── infrastructure/       # Docker, configs, deployment files
```

## Pipeline Flow

```
User Upload → [1] Frontend → [2] API Gateway → [3] Audio Parser
    ↓
[8] Composer ← [7] Video Generator ← [6] Prompt Generator
    ↓                                        ↑
Final Video                        [4] Scene Planner → [5] Reference Generator
```

## Processing Flow

1. User uploads audio + prompt via frontend
2. API Gateway creates job, queues for processing
3. Audio Parser extracts beats, lyrics, structure, mood
4. Scene Planner generates video plan using director knowledge
5. Reference Generator creates style reference images
6. Prompt Generator optimizes prompts for each clip
7. Video Generator creates clips in parallel (5 concurrent)
8. Composer stitches clips with audio and transitions

## Key Requirements

- **Quality:** 1080p, 30 FPS, beat-aligned transitions, minimum 3 clips
- **Performance:** 3-minute video in <10 minutes
- **Cost:** <$2/minute ($0.60-$1.20 typical), $20/job hard limit
- **Reliability:** 90%+ success rate with graceful error handling

## Technology Stack

- **Frontend:** Next.js 14, TypeScript, Supabase Auth
- **Backend:** FastAPI (Python), BullMQ + Redis, Supabase
- **AI Services:** OpenAI (Whisper, GPT-4o), Replicate (SDXL, Stable Video Diffusion)
- **Video Processing:** FFmpeg, Librosa, Aubio

## Getting Started

See individual module READMEs for detailed setup instructions.

## Development Roadmap

- **Day 1:** Foundation (Frontend, API Gateway, Audio Parser)
- **Day 2:** Generation (Scene Planner, Reference Generator, Prompt Generator, Video Generator)
- **Day 3:** Composition + Polish (Composer, Testing, Deployment)

