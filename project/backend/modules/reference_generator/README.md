# Module 5: Reference Generator

**Tech Stack:** Python (SDXL via Replicate)

## Purpose
Generate reference images for all scenes and characters using SDXL to establish visual consistency across all video clips.

## Key Features
- Model: Stable Diffusion XL via Replicate
- Scene References (one per unique scene location/setting)
- Character References (one per character for consistency)
- Parallel Generation (all reference images concurrently)
- Prompt Synthesis (combine style info with character/scene descriptions)
- Settings: 1024x1024, 30-40 steps, guidance 7-9

## Fallback
- If generation fails → Proceed with text-only prompts (no reference image)
- Text-only mode → Video prompts include style keywords but no visual reference
- Retry: 3 attempts with exponential backoff (2s, 4s, 8s) before fallback


