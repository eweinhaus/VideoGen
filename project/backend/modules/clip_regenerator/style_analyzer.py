"""
Style analysis for clip style transfer.

Extracts visual style keywords from prompts using keyword matching with LLM fallback.
"""
import json
from typing import List, Optional
from pydantic import BaseModel, Field

from shared.logging import get_logger
from modules.clip_regenerator.llm_modifier import get_openai_client

logger = get_logger("clip_regenerator.style_analyzer")


class StyleKeywords(BaseModel):
    """Style keywords extracted from a prompt."""
    
    color: List[str] = Field(default_factory=list, description="Color palette keywords")
    lighting: List[str] = Field(default_factory=list, description="Lighting style keywords")
    mood: List[str] = Field(default_factory=list, description="Mood/atmosphere keywords")


def extract_style_keywords(prompt: str) -> StyleKeywords:
    """
    Extract style keywords from prompt using keyword matching.
    
    Returns StyleKeywords with color, lighting, mood.
    If insufficient keywords found (<2 total), returns empty StyleKeywords
    (caller should use LLM fallback).
    
    Args:
        prompt: Video generation prompt to analyze
        
    Returns:
        StyleKeywords object with extracted keywords
    """
    prompt_lower = prompt.lower()
    
    # Color palette keywords
    color_keywords = []
    if any(kw in prompt_lower for kw in ["warm", "golden", "orange", "yellow", "amber"]):
        color_keywords.append("warm")
    if any(kw in prompt_lower for kw in ["cool", "blue", "cyan", "teal", "azure"]):
        color_keywords.append("cool")
    if any(kw in prompt_lower for kw in ["vibrant", "saturated", "colorful", "rich colors"]):
        color_keywords.append("vibrant")
    if any(kw in prompt_lower for kw in ["muted", "desaturated", "subtle", "pastel"]):
        color_keywords.append("muted")
    
    # Lighting keywords
    lighting_keywords = []
    if any(kw in prompt_lower for kw in ["bright", "well-lit", "daylight", "sunny", "illuminated"]):
        lighting_keywords.append("bright")
    if any(kw in prompt_lower for kw in ["dark", "shadowy", "low light", "dim", "gloomy"]):
        lighting_keywords.append("dark")
    if any(kw in prompt_lower for kw in ["dramatic", "high contrast", "stark", "bold lighting"]):
        lighting_keywords.append("dramatic")
    if any(kw in prompt_lower for kw in ["soft", "gentle", "diffused", "soft lighting", "gentle light"]):
        lighting_keywords.append("soft")
    
    # Mood keywords
    mood_keywords = []
    if any(kw in prompt_lower for kw in ["energetic", "dynamic", "fast-paced", "intense", "vibrant"]):
        mood_keywords.append("energetic")
    if any(kw in prompt_lower for kw in ["calm", "peaceful", "serene", "tranquil", "relaxed"]):
        mood_keywords.append("calm")
    if any(kw in prompt_lower for kw in ["mysterious", "mystical", "enigmatic", "eerie", "atmospheric"]):
        mood_keywords.append("mysterious")
    
    keywords = StyleKeywords(
        color=color_keywords,
        lighting=lighting_keywords,
        mood=mood_keywords
    )
    
    # Check if sufficient keywords found
    total_keywords = len(keywords.color) + len(keywords.lighting) + len(keywords.mood)
    if total_keywords < 2:
        logger.debug(
            f"Insufficient keywords found ({total_keywords}), LLM fallback recommended",
            extra={"total_keywords": total_keywords}
        )
    
    return keywords


async def extract_style_with_llm(prompt: str) -> StyleKeywords:
    """
    Use LLM to extract style keywords from prompt.
    
    Fallback when keyword matching finds insufficient style elements.
    
    Args:
        prompt: Video generation prompt to analyze
        
    Returns:
        StyleKeywords object with extracted keywords
        
    Raises:
        Exception: If LLM call fails or parsing fails
    """
    logger.info("Using LLM fallback for style extraction", extra={"prompt_length": len(prompt)})
    
    llm_prompt = f"""Analyze this video generation prompt and extract visual style elements:

Prompt: {prompt}

Extract the following style elements:
- Color palette (warm, cool, vibrant, muted, etc.)
- Lighting style (bright, dark, dramatic, soft, etc.)
- Mood/atmosphere (energetic, calm, mysterious, etc.)

Return ONLY a valid JSON object with this exact structure:
{{
  "color": ["keyword1", "keyword2"],
  "lighting": ["keyword1", "keyword2"],
  "mood": ["keyword1", "keyword2"]
}}

Do not include any explanation or markdown formatting, only the JSON object."""

    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a video style analyzer. Extract visual style keywords from prompts and return only valid JSON."},
                {"role": "user", "content": llm_prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        
        # Parse JSON
        style_data = json.loads(content)
        
        return StyleKeywords(
            color=style_data.get("color", []),
            lighting=style_data.get("lighting", []),
            mood=style_data.get("mood", [])
        )
        
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse LLM response as JSON",
            extra={"error": str(e), "response": content[:200]}
        )
        # Return empty keywords on parse failure
        return StyleKeywords()
    except Exception as e:
        logger.error(
            f"LLM style extraction failed",
            extra={"error": str(e)}
        )
        # Return empty keywords on failure
        return StyleKeywords()

