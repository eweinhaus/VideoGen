"""
LLM API integration for scene plan generation.

Handles OpenAI GPT-4o and Claude 3.5 Sonnet API calls with retry logic,
cost tracking, and comprehensive prompt engineering.
"""

import json
import re
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID

from openai import OpenAI, AsyncOpenAI
from openai import APIError, RateLimitError, APITimeoutError

from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import GenerationError, RetryableError
from shared.logging import get_logger
from shared.retry import retry_with_backoff
from shared.models.audio import AudioAnalysis

logger = get_logger("scene_planner")


# Initialize OpenAI client
_openai_client: Optional[AsyncOpenAI] = None


# Character description guidelines for text-to-video character consistency
CHARACTER_DESCRIPTION_GUIDELINES = """
CRITICAL REQUIREMENT: Generate EXTREMELY SPECIFIC character descriptions.

This is for text-to-video generation where precision is CRITICAL for character consistency
across multiple video clips. Vague descriptions result in completely different people in each clip.

Required details for EACH character (7+ specific features):

1. Hair:
   - Exact color with shade (e.g., "warm brown", "ash blonde", "jet black", NOT just "brown")
   - Length with measurement (e.g., "shoulder-length", "buzzcut 1/4 inch", "waist-length")
   - Texture (straight, wavy, curly, coily, kinky)
   - Style (fade, ponytail, braids, loose, slicked back, etc.)

2. Face:
   - Skin tone (specific: olive, fair, deep brown, golden tan, NOT just "light" or "dark")
   - Face shape (round, square, oval, heart-shaped, angular)
   - Distinctive features (high cheekbones, square jaw, defined chin, freckles, etc.)
   - Facial hair if applicable (clean shaven, stubble, full beard, goatee, mustache)

3. Eyes:
   - Color (dark brown, hazel, blue, green, gray - be specific)
   - Eyebrows (thick, thin, arched, straight, defined)

4. Clothing:
   - Exact colors with modifiers (bright blue, navy blue, forest green, NOT just "blue" or "green")
   - Style and type (hoodie, denim jacket, blazer, t-shirt, dress, etc.)
   - Visible details (buttons, zippers, drawstrings, patterns, logos)
   - The character wears the SAME OUTFIT in all scenes

5. Accessories (if any):
   - Glasses: shape and color (round tortoiseshell, rectangular black frames, aviator sunglasses)
   - Jewelry: type and placement (gold chain necklace, silver hoop earrings, watch)
   - Other: hats, scarves, belts, bags, etc.
   - Write "None" if no accessories

6. Build:
   - Body type (athletic, slim, muscular, plus-size, stocky, lean)
   - Approximate height (5'4", 6'2", etc.)
   - Frame (broad shoulders, narrow waist, petite, etc.)

7. Age:
   - Apparent age range (appears early 20s, mid 30s, late 40s, etc.)

FORMAT REQUIREMENT:

[Character Name] - FIXED CHARACTER IDENTITY:
- Hair: [specific description]
- Face: [specific description]
- Eyes: [specific description]
- Clothing: [specific description]
- Accessories: [specific description or "None"]
- Build: [specific description]
- Age: [specific description]

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance.

GOOD EXAMPLES:

"Alice - FIXED CHARACTER IDENTITY:
- Hair: shoulder-length brown curly hair with natural texture and volume, parted in the middle
- Face: olive skin tone, round face shape, defined cheekbones, no visible freckles
- Eyes: dark brown eyes, thick arched eyebrows
- Clothing: bright blue denim jacket with silver buttons and rolled sleeves, white crew-neck t-shirt underneath, dark blue jeans
- Accessories: round tortoiseshell glasses with thick frames, silver hoop earrings (1 inch diameter)
- Build: athletic build, approximately 5'6" height, medium frame
- Age: appears mid-20s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance."

"Marcus - FIXED CHARACTER IDENTITY:
- Hair: short black fade haircut with sharp line-up, tight curls on top (1/2 inch length)
- Face: deep brown skin tone, square jaw, high cheekbones, clean shaven
- Eyes: dark brown eyes, strong thick eyebrows
- Clothing: burgundy hoodie with white drawstrings and kangaroo pocket, black straight-leg jeans, white Air Force 1 sneakers
- Accessories: gold chain necklace (visible outside hoodie), silver watch on left wrist
- Build: athletic muscular build, approximately 6'0" tall, broad shoulders
- Age: appears early 30s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance."

BAD EXAMPLES (TOO VAGUE - DO NOT DO THIS):

❌ "Stylish young woman with cool vibe"
❌ "Confident artist"
❌ "Young man in casual clothes"
❌ "Beautiful person with nice hair"
❌ "Athletic guy"

These vague descriptions will result in COMPLETELY DIFFERENT PEOPLE in each video clip.
"""


def _repair_json(json_str: str) -> str:
    """
    Attempt to repair truncated or malformed JSON.
    
    Common issues:
    - Unterminated strings
    - Unclosed objects/arrays
    - Truncated response
    
    Args:
        json_str: Potentially malformed JSON string
        
    Returns:
        Repaired JSON string
    """
    if not json_str or not json_str.strip():
        return "{}"
    
    # Remove trailing commas before closing braces/brackets
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Count open/close braces and brackets
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    # Close unclosed objects/arrays
    result = json_str
    result += '\n' * (open_braces - close_braces)  # Add newlines for readability
    result += '}' * (open_braces - close_braces)
    result += ']' * (open_brackets - close_brackets)
    
    # Try to close unterminated strings
    # Count unescaped quotes
    in_string = False
    escape_next = False
    quote_count = 0
    
    for i, char in enumerate(json_str):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            quote_count += 1
            in_string = not in_string
    
    # If we're still in a string at the end, close it
    if in_string:
        # Find the last unclosed quote and close the string
        result = json_str.rstrip()
        # Remove any trailing incomplete content after last quote
        last_quote_idx = result.rfind('"')
        if last_quote_idx != -1:
            # Check if there's content after the quote that might be incomplete
            after_quote = result[last_quote_idx + 1:]
            # If there's incomplete content (not just whitespace/punctuation), remove it
            if after_quote.strip() and not after_quote.strip().endswith((':', ',', '}', ']')):
                # Remove incomplete content and close the string
                result = result[:last_quote_idx + 1] + '"'
            else:
                result += '"'
        else:
            result += '"'
    
    return result


def get_openai_client() -> AsyncOpenAI:
    """Get or create OpenAI async client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _calculate_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int
) -> Decimal:
    """
    Calculate LLM API cost based on token usage.
    
    Args:
        model: Model name ("gpt-4o" or "claude-3-5-sonnet")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Cost in USD
    """
    # Pricing as of 2024 (adjust if needed)
    if model == "gpt-4o":
        # GPT-4o: $0.005 per 1K input tokens, $0.015 per 1K output tokens
        input_cost = Decimal(input_tokens) / 1000 * Decimal("0.005")
        output_cost = Decimal(output_tokens) / 1000 * Decimal("0.015")
        return input_cost + output_cost
    elif model == "claude-3-5-sonnet":
        # Claude 3.5 Sonnet: $0.003 per 1K input tokens, $0.015 per 1K output tokens
        input_cost = Decimal(input_tokens) / 1000 * Decimal("0.003")
        output_cost = Decimal(output_tokens) / 1000 * Decimal("0.015")
        return input_cost + output_cost
    else:
        logger.warning(f"Unknown model {model}, using GPT-4o pricing")
        input_cost = Decimal(input_tokens) / 1000 * Decimal("0.005")
        output_cost = Decimal(output_tokens) / 1000 * Decimal("0.015")
        return input_cost + output_cost


def _build_system_prompt(
    director_knowledge: str,
    audio_data: AudioAnalysis
) -> str:
    """
    Build comprehensive system prompt with director knowledge and audio context.
    
    Args:
        director_knowledge: Full director knowledge base text
        audio_data: AudioAnalysis with mood, BPM, structure, etc.
        
    Returns:
        Formatted system prompt
    """
    # Extract audio characteristics
    mood = audio_data.mood.primary
    energy_level = audio_data.mood.energy_level
    bpm = audio_data.bpm
    
    # Build mood/energy-specific instructions
    mood_instructions = _get_mood_instructions(mood, energy_level, bpm)
    
    system_prompt = f"""You are an expert music video director with decades of experience creating professional music videos. Your task is to transform a user's creative vision into a comprehensive, director-informed scene plan that will guide video generation.

## Director Knowledge Base

{director_knowledge}

## Audio Analysis Context

The audio has the following characteristics:
- **Mood:** {mood} (energy level: {energy_level})
- **BPM:** {bpm:.1f}
- **Duration:** {audio_data.duration:.1f} seconds
- **Song Structure:** {len(audio_data.song_structure)} segments (intro, verse, chorus, bridge, outro)
- **Clip Boundaries:** {len(audio_data.clip_boundaries)} clips defined

{mood_instructions}

## Your Task

Generate a complete scene plan that:
1. **Maintains the user's core creative vision** - Their prompt is the anchor for the entire video
2. **Applies director knowledge intelligently** - Use color palettes, camera movements, lighting, and transitions that match the mood and energy level
3. **Aligns to clip boundaries** - Generate exactly {len(audio_data.clip_boundaries)} clip scripts matching the provided boundaries
4. **Ensures consistency** - Same character appearances, same scene lighting, same color palette per location across all clips
5. **Plans transitions** - Generate {len(audio_data.clip_boundaries) - 1} transitions between clips based on beat intensity
6. **Creates coherent narrative** - All clips should tell a visual story that makes sense

## Character Description Guidelines

{CHARACTER_DESCRIPTION_GUIDELINES}

## Output Format

You must output a valid JSON object matching this exact structure:

{{
  "job_id": "uuid-string",
  "video_summary": "High-level narrative overview (2-3 sentences describing the overall video concept)",
  "characters": [
    {{
      "id": "protagonist",
      "description": "MUST follow CHARACTER_DESCRIPTION_GUIDELINES above. Use the FIXED CHARACTER IDENTITY format with all 7 required features (Hair, Face, Eyes, Clothing, Accessories, Build, Age). Be extremely specific with colors, measurements, and details.",
      "role": "main character"
    }}
  ],
  "scenes": [
    {{
      "id": "scene_id",
      "description": "Detailed scene description (location, atmosphere, time of day, key visual elements)",
      "time_of_day": "night|day|dawn|dusk"
    }}
  ],
  "style": {{
    "color_palette": ["#00FFFF", "#FF00FF", "#0000FF"],
    "visual_style": "PRESERVE EXACT STYLE KEYWORDS from user prompt. If user specifies a style (e.g., 'pixar animation style', 'anime style', 'realistic', 'watercolor'), use those EXACT words/phrases. Do not paraphrase. If no specific style mentioned, describe overall aesthetic (e.g., 'Neo-noir cyberpunk with rain and neon')",
    "mood": "Emotional tone description",
    "lighting": "Lighting style description (e.g., 'High-contrast neon with deep shadows')",
    "cinematography": "Camera style description (e.g., 'Handheld, slight shake, tracking shots')"
  }},
  "clip_scripts": [
    {{
      "clip_index": 0,
      "start": 0.0,
      "end": 5.2,
      "visual_description": "Detailed visual description (1-2 sentences: what's happening, key visual elements, character actions)",
      "motion": "How elements move (character movement, camera movement, object movement)",
      "camera_angle": "Shot type and angle (e.g., 'Medium wide shot, slightly low angle, eye level height')",
      "characters": ["character_id"],
      "scenes": ["scene_id"],
      "lyrics_context": "Relevant lyrics during this clip or null",
      "beat_intensity": "low|medium|high"
    }}
  ],
  "transitions": [
    {{
      "from_clip": 0,
      "to_clip": 1,
      "type": "cut|crossfade|fade",
      "duration": 0.0,
      "rationale": "Explanation for transition choice based on beat intensity and song structure"
    }}
  ]
}}

## Critical Requirements

1. **Character Consistency:** The main character must appear in 60-80% of clips with consistent appearance. Define 1-3 signature elements (e.g., red jacket, blonde wig) that remain constant.

2. **Scene Consistency:** Use 2-4 distinct scenes. Each scene should have consistent lighting, color palette, and time of day across all clips.

3. **Color Palette:** Define 2-3 main colors per scene plus one accent color. Apply the color palette consistently - if a scene uses muted blues, all clips in that scene must use muted blues.

4. **Beat Alignment:** Clip scripts must align to the provided clip boundaries (±0.5s tolerance). Transitions should align with beat intensity (hard cut for high energy, crossfade for medium, fade for low).

5. **Style Preservation (CRITICAL):** If the user specifies a visual style (e.g., "pixar animation style", "anime style", "watercolor", "realistic", "3D CGI"), you MUST preserve those EXACT keywords in the visual_style field. Do NOT paraphrase or interpret. The exact style keywords are essential for accurate image generation.

6. **Director Knowledge Application:** Be explicit about applying director knowledge:
   - If mood is calm → Use muted, desaturated colors from the calm mood palette
   - If energy is high → Use fast cuts, handheld camera, tracking shots
   - If BPM >130 → Use hard cuts on strong beats, quick zooms, low angles
   - If BPM <90 → Use static shots, slow zooms, wide shots, fade transitions

7. **Anatomical Safety Requirements (CRITICAL):** All human characters must be described with correct anatomy to prevent generation errors:
   - Humans have exactly 2 arms, 2 legs, 1 head
   - When describing full-body shots: "full body visible showing two legs and two arms"
   - When describing upper-body shots: "upper body shot showing two arms"
   - For dance/action sequences: "anatomically correct human with proper proportions performing [action]"
   - Avoid ambiguous descriptions that could result in extra/missing limbs
   - Example: "Person jumping with both arms raised overhead and both feet off ground"

8. **Visual Description Quality:** Each clip script should be detailed enough for video generation:
   - Specify what's happening (character actions, scene elements)
   - Specify camera movement (tracking, static, panning, zooming)
   - Specify shot type (wide, medium, close-up, extreme close-up)
   - Specify camera angle (low, eye level, high)
   - Include visual metaphors if relevant to lyrics
   - Include anatomical details for human characters

9. **Transition Planning:** Generate exactly {len(audio_data.clip_boundaries) - 1} transitions:
   - Hard cut (0s duration): Strong beats, high energy, chorus transitions
   - Crossfade (0.5s duration): Medium beats, continuous motion, verse transitions
   - Fade (0.5s duration): Soft beats, low energy, intro/outro transitions

## Example Clip Script (High Quality)

{{
  "clip_index": 0,
  "start": 0.0,
  "end": 5.2,
  "visual_description": "Protagonist walks toward camera through rain-slicked cyberpunk street, neon signs reflecting in puddles. Distant city lights create bokeh in background. Character wears signature red jacket, visible even in the dim lighting.",
  "motion": "Slow tracking shot following character, camera moves backward as character approaches. Rain falls steadily, creating movement in frame. Character walks with deliberate pace, matching the calm mood.",
  "camera_angle": "Medium wide shot, slightly low angle, eye level height",
  "characters": ["protagonist"],
  "scenes": ["city_street"],
  "lyrics_context": "I see the lights shining bright",
  "beat_intensity": "medium"
}}

Remember: The user's creative prompt is your anchor. Apply director knowledge to enhance and professionalize their vision, but never lose their core concept."""
    
    return system_prompt


def _get_mood_instructions(mood: str, energy_level: str, bpm: float) -> str:
    """
    Generate mood/energy-specific instructions for the LLM.
    
    Args:
        mood: Primary mood
        energy_level: Energy level
        bpm: Beats per minute
        
    Returns:
        Formatted instructions
    """
    instructions = []
    
    # Determine energy category
    if bpm > 130 or energy_level == "high":
        energy_category = "high"
    elif bpm < 90 or energy_level == "low":
        energy_category = "low"
    else:
        energy_category = "medium"
    
    # Mood-specific instructions
    if mood.lower() == "energetic":
        instructions.append("""
**ENERGETIC MOOD GUIDELINES:**
- Use vibrant, saturated colors (electric blues, magentas, neon yellows, hot pinks)
- Apply high contrast between foreground and background
- Use fast cuts (0.5-1 second shots) for high energy sections
- Camera movements: Fast tracking shots, whip pans, quick zooms, handheld with slight shake
- Transitions: Hard cuts on strong beats, beat-synchronized cuts
- Lighting: Dynamic lighting with color shifts, neon, practical lights, high contrast
- Shot types: Close-ups for intensity, medium shots for action, low angles for power
""")
    elif mood.lower() == "calm":
        instructions.append("""
**CALM MOOD GUIDELINES:**
- Use muted, desaturated colors (soft blues, lavender, mint, peach, pastels)
- Desaturate colors by 30-40% for peaceful feeling
- Use longer shots (5-10 seconds minimum) for contemplation
- Camera movements: Static shots, slow zooms, wide shots, slow pans
- Transitions: Fade or crossfade for smooth flow
- Lighting: Soft, natural, diffused light, low contrast
- Shot types: Wide shots primary, medium shots for context, high angles for perspective
""")
    elif mood.lower() == "dark":
        instructions.append("""
**DARK MOOD GUIDELINES:**
- Use low saturation, high contrast colors (blacks, deep purples, dark blues, dark reds)
- High contrast between light and shadow
- Use single accent color sparingly (e.g., deep red)
- Camera movements: Deliberate tracking shots, slow movements, static shots
- Transitions: Fade transitions, crossfade for smooth flow
- Lighting: Low-key lighting, single primary light source, shadows cover 60-70% of frame
- Shot types: Wide shots for atmosphere, medium shots, silhouettes
""")
    elif mood.lower() == "bright":
        instructions.append("""
**BRIGHT MOOD GUIDELINES:**
- Use high brightness, low contrast colors (yellows, whites, light blues, pinks)
- Pastel or neon colors depending on energy
- Even illumination across frame
- Camera movements: Smooth tracking shots, balanced framing, steady movements
- Transitions: Crossfade for smooth flow, fade for intro/outro
- Lighting: High-key lighting, multiple light sources, soft diffused light, minimal shadows
- Shot types: Balanced framing, medium shots primary, wide shots for context
""")
    
    # Energy-specific instructions
    if energy_category == "high":
        instructions.append("""
**HIGH ENERGY (BPM >130) GUIDELINES:**
- Faster cuts align with musical beats
- Bigger camera moves (whip pans, quick zooms, orbits)
- Hard cuts on snare hits or strong beats
- Low angles for power and dominance
- Quick movements match tempo
""")
    elif energy_category == "low":
        instructions.append("""
**LOW ENERGY (BPM <90) GUIDELINES:**
- Longer takes (5-10 seconds minimum)
- Minimal camera movement for contemplation
- Slow, deliberate movements
- Fade transitions for emotional moments
- Wide shots for atmosphere
""")
    
    return "\n".join(instructions)


def _build_user_prompt(
    user_prompt: str,
    audio_data: AudioAnalysis
) -> str:
    """
    Build user prompt with audio context and clip boundaries.
    
    Args:
        user_prompt: User's creative prompt (50-500 characters)
        audio_data: AudioAnalysis with structure and boundaries
        
    Returns:
        Formatted user prompt with audio context
    """
    # Format song structure
    structure_lines = []
    for segment in audio_data.song_structure:
        structure_lines.append(
            f"  - {segment.type.upper()}: {segment.start:.1f}s - {segment.end:.1f}s ({segment.energy} energy)"
        )
    
    # Format clip boundaries
    boundary_lines = []
    for i, boundary in enumerate(audio_data.clip_boundaries):
        boundary_lines.append(
            f"  Clip {i}: {boundary.start:.1f}s - {boundary.end:.1f}s (duration: {boundary.duration:.1f}s)"
        )
    
    # Format lyrics (if available)
    lyrics_text = ""
    if audio_data.lyrics:
        lyrics_lines = []
        for lyric in audio_data.lyrics[:20]:  # Limit to first 20 lyrics to avoid token bloat
            lyrics_lines.append(f"  [{lyric.timestamp:.1f}s] {lyric.text}")
        lyrics_text = f"""
## Lyrics Context

{chr(10).join(lyrics_lines)}
"""
    
    user_prompt_formatted = f"""## User's Creative Vision

{user_prompt}

## Song Structure

{chr(10).join(structure_lines)}

## Clip Boundaries (You must generate scripts for these exact boundaries)

{chr(10).join(boundary_lines)}
{lyrics_text}

Generate a complete scene plan that transforms the user's creative vision into a professional music video plan. Apply director knowledge to enhance the vision while maintaining the core concept. Ensure all clip scripts align to the provided boundaries and create a coherent visual narrative."""
    
    return user_prompt_formatted


@retry_with_backoff(max_attempts=3, base_delay=2)
async def generate_scene_plan(
    job_id: UUID,
    user_prompt: str,
    audio_data: AudioAnalysis,
    director_knowledge: str
) -> Dict[str, Any]:
    """
    Generate scene plan using LLM API.
    
    This is the core function that constructs the final LLM prompt by:
    1. Loading director knowledge
    2. Extracting relevant sections based on audio mood/energy/BPM
    3. Formatting user prompt as creative vision anchor
    4. Structuring audio context as constraints
    5. Explicitly instructing LLM to apply director knowledge
    6. Requesting JSON output matching ScenePlan model
    
    Args:
        job_id: Job ID for cost tracking
        user_prompt: User's creative prompt (50-500 characters)
        audio_data: AudioAnalysis with BPM, mood, structure, boundaries
        director_knowledge: Director knowledge base text
        
    Returns:
        Parsed JSON dict matching ScenePlan structure
        
    Raises:
        GenerationError: If LLM call fails after retries
        RetryableError: If transient error occurs (will be retried)
    """
    model = "gpt-4o"  # Preferred model
    
    try:
        # Build prompts
        system_prompt = _build_system_prompt(director_knowledge, audio_data)
        user_prompt_formatted = _build_user_prompt(user_prompt, audio_data)
        
        logger.info(
            f"Calling LLM for scene plan generation",
            extra={
                "job_id": str(job_id),
                "model": model,
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt_formatted)
            }
        )
        
        # Call OpenAI API
        client = get_openai_client()
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_formatted}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16000,  # Increased from 4000 to handle large scene plans
            timeout=90.0
        )
        
        # Extract response
        content = response.choices[0].message.content
        if not content:
            raise GenerationError("Empty response from LLM", job_id=job_id)
        
        # Try to extract JSON from markdown code blocks if present
        if "```json" in content:
            # Extract JSON from markdown code block
            start_idx = content.find("```json") + 7
            end_idx = content.find("```", start_idx)
            if end_idx != -1:
                content = content[start_idx:end_idx].strip()
        elif "```" in content:
            # Try generic code block
            start_idx = content.find("```") + 3
            end_idx = content.find("```", start_idx)
            if end_idx != -1:
                content = content[start_idx:end_idx].strip()
        
        # Parse JSON with repair attempts
        scene_plan_dict = None
        parse_error = None
        try:
            scene_plan_dict = json.loads(content)
        except json.JSONDecodeError as e:
            parse_error = e
            # Try to repair truncated JSON (common issue with max_tokens)
            logger.warning(
                f"Initial JSON parse failed, attempting repair: {str(e)}",
                extra={"job_id": str(job_id), "response_length": len(content), "error_position": getattr(e, 'pos', None)}
            )
            
            # Attempt 1: Try to find and close unclosed strings/objects
            try:
                repaired = _repair_json(content)
                scene_plan_dict = json.loads(repaired)
                logger.info("Successfully repaired truncated JSON", extra={"job_id": str(job_id)})
            except Exception as repair_error:
                logger.error(
                    f"JSON repair failed: {str(repair_error)}",
                    extra={"job_id": str(job_id), "original_error": str(e)}
                )
                # Log more context for debugging
                error_pos = getattr(e, 'pos', None)
                if error_pos:
                    preview_start = max(0, error_pos - 100)
                    preview_end = min(len(content), error_pos + 100)
                    logger.error(
                        f"JSON parse error context",
                        extra={
                            "job_id": str(job_id),
                            "error_position": error_pos,
                            "content_preview": content[preview_start:preview_end],
                            "full_response_length": len(content),
                            "response_preview": content[:500]
                        }
                    )
                raise RetryableError(f"Invalid JSON from LLM: {str(e)}", job_id=job_id) from e
        
        if scene_plan_dict is None:
            raise RetryableError(f"Invalid JSON from LLM: {str(parse_error)}", job_id=job_id) from parse_error
        
        # Track cost
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = _calculate_llm_cost(model, input_tokens, output_tokens)
        
        await cost_tracker.track_cost(
            job_id=job_id,
            stage_name="scene_planning",
            api_name=model,
            cost=cost
        )
        
        logger.info(
            f"Scene plan generated successfully",
            extra={
                "job_id": str(job_id),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": float(cost)
            }
        )
        
        return scene_plan_dict
        
    except RateLimitError as e:
        logger.warning(f"Rate limit error: {str(e)}", extra={"job_id": str(job_id)})
        raise RetryableError(f"Rate limit error: {str(e)}", job_id=job_id) from e
    except APITimeoutError as e:
        logger.warning(f"API timeout: {str(e)}", extra={"job_id": str(job_id)})
        raise RetryableError(f"API timeout: {str(e)}", job_id=job_id) from e
    except APIError as e:
        logger.error(f"OpenAI API error: {str(e)}", extra={"job_id": str(job_id)})
        # Check if retryable
        if e.status_code and e.status_code >= 500:
            raise RetryableError(f"Retryable API error: {str(e)}", job_id=job_id) from e
        raise GenerationError(f"OpenAI API error: {str(e)}", job_id=job_id) from e
    except Exception as e:
        logger.error(
            f"Unexpected error in LLM call: {str(e)}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        raise GenerationError(f"Unexpected error: {str(e)}", job_id=job_id) from e

