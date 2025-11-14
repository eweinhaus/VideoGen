# Module 6: Prompt Generator

**Tech Stack:** Python (LLM Optimization)

## Purpose
Optimize video generation prompts by combining clip scripts with style information into concise, high-quality prompts.

## Key Features
- Prompt Synthesis (visual description + style + camera + quality modifiers)
- Consistency (same style keywords in all prompts)
- Conciseness (<200 words per prompt)
- Batch Generation (all prompts in one pass)

## Prompt Structure
```
{visual_description}, {motion}, {camera_angle}, 
{visual_style} aesthetic with {color_palette}, 
cinematic lighting, highly detailed, professional cinematography, 4K
```


