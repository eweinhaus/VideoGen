# Module 7: Video Generator

**Tech Stack:** Python (Stable Video Diffusion / CogVideoX via Replicate)

## Purpose
Generate video clips in **parallel** (5 concurrent) using text-to-video models with retry logic and duration handling.

## Key Features
- Parallel Processing (5 clips concurrently, saves 60-70% time)
- Model: Stable Video Diffusion or CogVideoX via Replicate
- Reference Images (uses scene_reference_url and character_reference_urls)
- Multi-reference (combines scene background with character references)
- Duration Strategy (request closest available duration, accept ±2s tolerance)
- Retry Logic (3 attempts per clip with exponential backoff)
- Progress Updates (SSE event after each clip completes)
- Partial Success (accept ≥3 clips, don't require all)

## Generation Settings
- Resolution: 1024x576 or 768x768
- FPS: 24-30
- Motion amount: 127 (medium)
- Steps: 20-30
- Timeout: 120s per clip


