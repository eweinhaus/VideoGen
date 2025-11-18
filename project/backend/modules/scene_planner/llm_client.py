"""
LLM API integration for scene plan generation.

Handles OpenAI GPT-4o and Claude 3.5 Sonnet API calls with retry logic,
cost tracking, and comprehensive prompt engineering.
"""

import json
import re
from decimal import Decimal
from typing import Dict, Any, Optional, List
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
⚠️ CRITICAL REQUIREMENT: Generate EXTREMELY SPECIFIC character descriptions.

WARNING: Vague or missing descriptions cause COMPLETELY DIFFERENT PEOPLE in each video clip!
❌ NEVER use "unspecified", "average", "typical", "normal" - these are USELESS and CAUSE FAILURE!
✅ ALWAYS provide SPECIFIC, MEASURABLE details for ALL 7 features - NO EXCEPTIONS!

MANDATORY details for EVERY character (ALL 7 features required):

1. Hair:
   - Exact color with shade (e.g., "jet black", "ash blonde", "warm brown", NOT "brown" or "unspecified")
   - Length with measurement ("buzzcut 1/4 inch", "shoulder-length", "waist-length")
   - Texture (straight, wavy, curly, coily, kinky)
   - Style (fade, ponytail, braids, locs, cornrows, slicked back, etc.)

2. Face:
   - Skin tone (SPECIFIC: deep brown, golden tan, fair, olive, mahogany, NOT "light"/"dark"/"unspecified")
   - Face shape (round, square, oval, heart-shaped, angular, diamond)
   - Distinctive features (high cheekbones, square jaw, dimples, freckles, etc.)
   - Facial hair (clean shaven, stubble, full beard, goatee, thin mustache, soul patch)

3. Eyes:
   - Color (dark brown, hazel, blue, green, gray, amber - NEVER "unspecified")
   - Eyebrows (thick, thin, arched, straight, defined, bushy)

4. Clothing:
   - Exact colors with modifiers (navy blue, forest green, burgundy, NOT just "blue" or "unspecified")
   - Specific items (hoodie, denim jacket, graphic t-shirt, leather jacket, NOT "shirt")
   - Visible details (white drawstrings, silver buttons, brand logo, patterns)
   - Character wears SAME OUTFIT in all scenes

5. Accessories:
   - Glasses: shape + color (round tortoiseshell, rectangular black frames, aviator sunglasses)
   - Jewelry: type + placement (gold chain necklace, diamond studs, silver watch on left wrist)
   - Other: specific hats (snapback, beanie, fedora), headphones, bags, etc.
   - Write "None" ONLY if truly no accessories (NOT "unspecified")

6. Build:
   - Body type (athletic, slim, muscular, lean, toned, stocky - NOT "average" or "unspecified")
   - Approximate height (5'6", 6'0", 5'4", etc.)
   - Frame (broad shoulders, narrow waist, petite, lanky, stocky)

7. Age:
   - Apparent age (appears early 20s, mid 30s, late 40s, etc. - NEVER "unspecified")

SPECIAL: Real People (celebrities, public figures):
When user mentions a real person (e.g., "Kendrick Lamar", "Taylor Swift"), describe their ACTUAL recognizable features:

"Kendrick Lamar - FIXED CHARACTER IDENTITY:
- Hair: short black hair in tight coils, shaped fade on sides (1/4 inch), slightly longer on top (1 inch)
- Face: deep brown skin tone, angular face shape, high cheekbones, thin mustache and goatee
- Eyes: dark brown eyes, thick straight eyebrows, intense gaze
- Clothing: black oversized hoodie with white drawstrings, dark blue jeans, white Nike Cortez sneakers
- Accessories: small diamond stud earrings in both ears, thin gold chain necklace
- Build: lean athletic build, approximately 5'6" height, narrow shoulders
- Age: appears mid-30s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance."

GOOD EXAMPLES (Generic Characters):

"Alice - FIXED CHARACTER IDENTITY:
- Hair: shoulder-length brown curly hair with natural texture and volume, parted in the middle
- Face: olive skin tone, round face shape, defined cheekbones, no visible freckles
- Eyes: dark brown eyes, thick arched eyebrows
- Clothing: bright blue denim jacket with silver buttons and rolled sleeves, white crew-neck t-shirt underneath, dark blue jeans
- Accessories: round tortoiseshell glasses with thick frames, silver hoop earrings (1 inch diameter)
- Build: athletic build, approximately 5'6" height, medium frame
- Age: appears mid-20s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance."

UNACCEPTABLE - WILL CAUSE COMPLETE FAILURE:

❌ "Kendrick Lamar - FIXED CHARACTER IDENTITY:
- Hair: unspecified hair
- Face: unspecified face
- Eyes: unspecified eyes
- Clothing: unspecified clothing
- Accessories: None
- Build: average build
- Age: unspecified age"
THIS IS USELESS! Will generate random different people in every clip!

❌ "Stylish artist" / "Cool guy" / "Young man" / "Athletic person"
❌ ANY description using "unspecified", "average", "normal", "typical"

BACKGROUND CHARACTERS:
ALL characters appearing in scenes need descriptions (including background):
- Bartender → full description required
- Crowd members (if visible/prominent) → full descriptions
- Passersby (if in multiple clips) → full descriptions
Only truly faceless/distant crowds can be generic.

EVERY character MUST have ALL 7 specific features. "Unspecified" = FAILURE.
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

## CHARACTER GENERATION RULES (CRITICAL)

You MUST generate character profiles for ALL characters that appear in ANY clip, including:

1. **MAIN CHARACTERS:** Generate for all protagonists, antagonists, love interests
   - These are the primary focus of the video
   - Should appear in 60-80% of clips

2. **SUPPORTING CHARACTERS:** Generate for all named/speaking characters
   - Any character with a specific role or dialogue
   - Examples: friends, companions, bandmates

3. **BACKGROUND CHARACTERS (CRITICAL):** Generate for ANY recurring background roles:
   - Bartenders (if bar appears in multiple clips)
   - Band members (if band appears in multiple clips)
   - Crowd members who are visible/prominent (if mentioned in multiple clips)
   - Service workers (waiters, cashiers, etc.)
   - Passersby (if they appear in multiple clips)

4. **CHARACTER REUSE:** If a role appears in multiple clips, it MUST be the same character:
   - "the bartender" in clip 1 = "the bartender" in clip 4 (same person)
   - "crowd member" in clip 2 = "crowd member" in clip 5 (same people)

5. **MINIMUM CHARACTERS by Scene Type:**
   - Solo video: 1 main character
   - Couple/duet: 2 main characters
   - Bar/club scene: 2 main + 1 bartender + 2-3 background patrons
   - Street scene: 2 main + 1-2 passersby (if mentioned in clips)
   - Concert/performance scene: 2 main + 3 band members + 2-3 crowd members

⚠️ **DO NOT** generate random background people in clip visual descriptions without creating character profiles for them first!

If a clip mentions "bartender", "crowd", "band", "passersby", etc., you MUST:
1. Create a character profile with full 7-feature description
2. Assign a character ID (e.g., "bartender_1", "crowd_1", "band_guitarist")
3. Include that character ID in the clip's "characters" field

## OBJECT GENERATION RULES (HIGHLY RECOMMENDED)

**CRITICAL: Generate object profiles for KEY OBJECTS that appear in the video.**

**When to Generate Objects:**
1. **Object appears in 2+ clips** (recurring prop) - ALWAYS generate
2. **Object is central to the story** (plot-critical) - ALWAYS generate, even if single-clip
3. **Object is held/worn by characters** across multiple clips - ALWAYS generate
4. **User explicitly mentioned object** in their prompt - ALWAYS generate as PRIMARY
5. **Object is a signature prop** (protagonist's guitar, vintage car, necklace) - ALWAYS generate

**Examples of objects to track:**
- Musical instruments (guitars, pianos, microphones, drums, violins, saxophones, trumpets, bass)
- Vehicles (cars, motorcycles, bicycles, boats, trucks, vans)
- Jewelry and accessories (necklaces, watches, rings, bracelets, earrings, chains)
- Significant props (cameras, phones, laptops, headphones, speakers)
- Key items (books, bottles, glasses, bags, hats, jackets, sunglasses, umbrellas, flowers, guitar cases)

**DO NOT include:**
- Generic scene furnishings (random chairs, tables, cups) unless plot-critical
- Background items that don't interact with characters
- Items mentioned only once in passing

**Object Generation Guidelines:**

1. **Object Features (6 Required Fields - ALL MUST BE SPECIFIC):**
   - **object_type**: Specific type (acoustic guitar, sports car, pendant necklace) - NOT generic "guitar" or "car"
   - **color**: Exact color with shade (cherry red metallic, matte black, honey sunburst finish) - NOT just "red" or "black"
   - **material**: Material/texture (solid spruce top, polished metal, worn leather) - NOT "wood" or "metal"
   - **distinctive_features**: Unique details (scratches, logos, custom design, wear patterns, brand names) - NOT "nice looking"
   - **size**: Approximate dimensions (full-size dreadnought body, compact sedan, 20-inch chain) - NOT "normal size"
   - **condition**: new | worn | vintage | damaged | pristine | well-used

2. **Importance Levels:**
   - **primary**: Central to story (protagonist's signature item, plot device, user-mentioned object)
   - **secondary**: Supporting props (background instruments, vehicle, accessories)

3. **Object Consistency:**
   - Same object must have SAME features in all clips
   - Object features should be SPECIFIC and MEASURABLE
   - Avoid vague descriptions ("nice guitar" → "honey sunburst acoustic guitar with worn finish around soundhole")
   - Extract features from clip descriptions when possible

4. **Clip Assignment:**
   - If a clip mentions an object, include its ID in the "objects" field
   - Example: Clip shows "protagonist playing guitar" → objects: ["vintage_guitar"]
   - Primary objects should appear in relevant clips even if only mentioned once

**GOOD EXAMPLE:**

```json
{{
  "id": "vintage_guitar",
  "name": "Vintage Acoustic Guitar",
  "features": {{
    "object_type": "acoustic guitar",
    "color": "honey sunburst finish with natural wood grain visible",
    "material": "solid spruce top, mahogany back and sides, rosewood fingerboard",
    "distinctive_features": "worn finish around soundhole from years of playing, small dent on lower bout, vintage tuning pegs with aged patina, mother-of-pearl fret markers",
    "size": "full-size dreadnought body (approximately 20 inches long, 15 inches wide)",
    "condition": "vintage, well-used but maintained, authentic wear patterns"
  }},
  "importance": "primary"
}}
```

**BAD EXAMPLE (too vague):**

```json
{{
  "id": "guitar",
  "name": "Guitar",
  "features": {{
    "object_type": "guitar",
    "color": "brown",
    "material": "wood",
    "distinctive_features": "nice looking",
    "size": "normal size",
    "condition": "good"
  }},
  "importance": "secondary"
}}
```

⚠️ **IMPORTANT:** Objects are OPTIONAL. Only generate them if they genuinely appear in 2+ clips or are plot-critical. Do NOT force-generate objects for every video.

## Output Format

You must output a valid JSON object matching this exact structure:

{{
  "job_id": "uuid-string",
  "video_summary": "High-level narrative overview (2-3 sentences describing the overall video concept)",
  "characters": [
    {{
      "id": "protagonist",
      "description": "MUST start with 'CharacterName - FIXED CHARACTER IDENTITY:' then list all 7 features (Hair, Face, Eyes, Clothing, Accessories, Build, Age) using the format shown in CHARACTER_DESCRIPTION_GUIDELINES. Example: 'Sarah - FIXED CHARACTER IDENTITY:\n- Hair: long auburn hair...\n- Face: fair skin...' Be extremely specific with colors, measurements, and details.",
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
  "objects": [
    {{
      "id": "object_id",
      "name": "Object Name",
      "features": {{
        "object_type": "Type of object (guitar, car, necklace, phone, etc.)",
        "color": "Specific color with shade (cherry red, matte black, honey sunburst)",
        "material": "Material/texture (wood, metal, leather, glass, etc.)",
        "distinctive_features": "Unique identifying details (brand logo, wear patterns, custom design, scratches)",
        "size": "Approximate size or scale description",
        "condition": "new|worn|vintage|damaged"
      }},
      "importance": "primary|secondary"
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
      "objects": ["object_id"],
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
    audio_data: AudioAnalysis,
    user_input_objects: Optional[List[Any]] = None
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
    
    # Format FULL lyrics (if available) - use ALL lyrics as primary context for scene planning
    # Lyrics inform the overall story and character actions, not just individual clips
    lyrics_text = ""
    if audio_data.lyrics:
        # Group lyrics by formatted phrases to avoid repetition, but include ALL unique phrases
        seen_phrases = set()
        lyrics_lines = []
        
        for lyric in audio_data.lyrics:
            # Use formatted_text if available, otherwise use individual word
            if lyric.formatted_text:
                phrase = lyric.formatted_text
                # Only add each unique phrase once with its timestamp
                if phrase not in seen_phrases:
                    seen_phrases.add(phrase)
                    lyrics_lines.append(f"  [{lyric.timestamp:.1f}s] {phrase}")
            else:
                # Fallback to individual word if formatted_text not available
                lyrics_lines.append(f"  [{lyric.timestamp:.1f}s] {lyric.text}")
        
        # Use ALL lyrics - no truncation (full lyrics strongly inform the overall story)
            lyrics_text = f"""
## Full Lyrics (Complete Song - Strongly Inform Scene Planning)

{chr(10).join(lyrics_lines)}

**IMPORTANT:** These lyrics are a STRONG SECONDARY source (1B) that should strongly inform the scene planning. Use them to:
- Understand the song's narrative, themes, and emotional journey
- Determine character actions and motivations that align with lyrical content
- Create scenes that complement and enhance the user's creative vision
- Ensure characters perform actions (talking, moving, gesturing) that match the lyrics
- The user's creative vision (above) is PRIMARY (1A), but lyrics should strongly influence how that vision is executed
"""
    
    # Add user input objects information if available
    objects_hint = ""
    if user_input_objects:
        object_names = [obj.name for obj in user_input_objects]
        objects_hint = f"""
## Objects Mentioned by User (IMPORTANT - Mark as PRIMARY)

The user explicitly mentioned these objects in their prompt. These should be marked as "primary" importance and included in relevant clips:
{chr(10).join(f"- {name}" for name in object_names)}

**CRITICAL:** These objects are plot-critical and should appear in the scene plan even if they only appear in one clip.
"""
    
    user_prompt_formatted = f"""## User's Creative Vision (PRIMARY - 1A)

{user_prompt}
{objects_hint}{lyrics_text}
## Song Structure

{chr(10).join(structure_lines)}

## Clip Boundaries (You must generate scripts for these exact boundaries)

{chr(10).join(boundary_lines)}

**IMPORTANT INSTRUCTIONS:**
1. **User's Creative Vision is PRIMARY (1A)** - This is the foundation of the scene plan
2. **Lyrics are SECONDARY but STRONGLY INFORM (1B)** - Use lyrics to enhance and inform how the user's vision is executed
3. Characters should PERFORM ACTIONS based on lyrics: talking (lip-sync), moving, gesturing, interacting with objects
4. Avoid static "moving still shots" - characters must be DOING things, not just standing there
5. Each clip's visual_description should include specific actions that align with the lyrics at that timestamp
6. The lyrics_context field in each clip should contain the specific lyrics/phrases for that clip's timestamp range

Generate a complete scene plan that transforms the user's creative vision (PRIMARY) informed by the lyrics (SECONDARY but strong) into a professional music video plan. Apply director knowledge to enhance the vision while maintaining the core concept. Ensure all clip scripts align to the provided boundaries and create a coherent visual narrative with active, dynamic characters."""
    
    return user_prompt_formatted


@retry_with_backoff(max_attempts=3, base_delay=2)
async def generate_scene_plan(
    job_id: UUID,
    user_prompt: str,
    audio_data: AudioAnalysis,
    director_knowledge: str,
    user_input_objects: Optional[List[Any]] = None
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
        user_prompt_formatted = _build_user_prompt(user_prompt, audio_data, user_input_objects)
        
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

