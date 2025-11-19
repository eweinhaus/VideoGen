"""
AI-powered prompt suggestions for clip improvements.

Generates suggestions for clip modifications using LLM analysis.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from shared.logging import get_logger
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clip_prompts_from_job_stages,
    load_audio_data_from_job_stages
)
from modules.clip_regenerator.llm_modifier import get_openai_client

logger = get_logger("clip_regenerator.suggestion_generator")


class Suggestion(BaseModel):
    """AI-generated suggestion for clip improvement."""
    
    type: str = Field(..., description="Suggestion type: quality, consistency, or creative")
    description: str = Field(..., description="Suggestion description")
    example_instruction: str = Field(..., description="Example instruction to apply suggestion")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")


async def generate_suggestions(
    job_id: UUID,
    clip_index: int
) -> List[Suggestion]:
    """
    Generate AI suggestions for a clip.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip to generate suggestions for
        
    Returns:
        List of Suggestion objects
        
    Raises:
        ValidationError: If clip_index is invalid or data loading fails
    """
    logger.info(
        f"Generating suggestions for clip",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    
    # Load clip data
    clips = await load_clips_from_job_stages(job_id)
    if not clips:
        raise ValueError(f"Failed to load clips for job {job_id}")
    
    if clip_index < 0 or clip_index >= len(clips.clips):
        raise ValueError(
            f"Invalid clip_index: {clip_index}. Valid range: 0-{len(clips.clips) - 1}"
        )
    
    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
    if not clip_prompts:
        raise ValueError(f"Failed to load clip prompts for job {job_id}")
    
    if clip_index >= len(clip_prompts.clip_prompts):
        raise ValueError(
            f"Invalid clip_index: {clip_index}. Valid range: 0-{len(clip_prompts.clip_prompts) - 1}"
        )
    
    audio_data = await load_audio_data_from_job_stages(job_id)
    
    # Build context
    clip_prompt = clip_prompts.clip_prompts[clip_index].prompt
    other_clips = [
        cp.prompt for cp in clip_prompts.clip_prompts 
        if cp.clip_index != clip_index
    ][:5]  # Limit to last 5 clips to avoid token limit
    
    audio_context = {}
    if audio_data:
        # Get beat intensity for this clip's segment
        beat_intensity = "medium"  # Default
        if audio_data.song_structure and clip_index < len(audio_data.song_structure):
            segment = audio_data.song_structure[clip_index]
            beat_intensity = getattr(segment, "beat_intensity", "medium")
        
        audio_context = {
            "beat_intensity": beat_intensity,
            "mood": audio_data.mood.primary if audio_data.mood else "neutral"
        }
    
    context = {
        "clip_prompt": clip_prompt,
        "other_clips": other_clips,
        "audio_context": audio_context
    }
    
    # Generate suggestions with LLM
    suggestions = await call_llm_for_suggestions(context)
    
    logger.info(
        f"Generated {len(suggestions)} suggestions",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    
    return suggestions


async def call_llm_for_suggestions(context: Dict[str, Any]) -> List[Suggestion]:
    """
    Call LLM to generate suggestions.
    
    Args:
        context: Context dictionary with clip_prompt, other_clips, audio_context
        
    Returns:
        List of Suggestion objects
    """
    clip_prompt = context.get("clip_prompt", "")
    other_clips = context.get("other_clips", [])
    audio_context = context.get("audio_context", {})
    
    # Build other clips summary
    other_clips_summary = "\n".join([f"- {prompt[:100]}..." for prompt in other_clips[:3]])
    if not other_clips_summary:
        other_clips_summary = "No other clips available"
    
    # Build audio context string
    beat_intensity = audio_context.get("beat_intensity", "medium")
    mood = audio_context.get("mood", "neutral")
    audio_context_str = f"Beat intensity: {beat_intensity}, Mood: {mood}"
    
    llm_prompt = f"""Analyze this video clip prompt and suggest 3-5 specific, actionable improvements:

Clip Prompt: {clip_prompt}

Other Clips in Video:
{other_clips_summary}

Audio Context: {audio_context_str}

Suggest improvements in these categories:
1. Quality: Technical improvements (lighting, composition, clarity)
2. Consistency: Style matching with other clips
3. Creative: Artistic enhancements (motion, effects, visual interest)

For each suggestion, provide:
- type: "quality", "consistency", or "creative"
- description: Brief description of the improvement
- example_instruction: Example instruction the user could give to apply this suggestion
- confidence: Confidence score 0.0-1.0

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "type": "quality",
    "description": "Brief description",
    "example_instruction": "make it brighter",
    "confidence": 0.85
  }},
  ...
]

Do not include any explanation or markdown formatting, only the JSON array."""

    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a video editing assistant. Analyze clips and suggest improvements. Return only valid JSON arrays."},
                {"role": "user", "content": llm_prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        
        # Parse JSON
        import json
        suggestions_data = json.loads(content)
        
        # Convert to Suggestion objects
        suggestions = [Suggestion(**s) for s in suggestions_data]
        
        return suggestions
        
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse LLM response as JSON",
            extra={"error": str(e), "response": content[:200]}
        )
        return []
    except Exception as e:
        logger.error(
            f"LLM suggestion generation failed",
            extra={"error": str(e)},
            exc_info=True
        )
        return []

