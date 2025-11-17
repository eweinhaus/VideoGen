"""
Clip script generation from LLM output.

Transforms LLM JSON output into structured ClipScript objects,
aligning scripts to clip boundaries and matching lyrics to clips.
"""

from typing import List, Optional
from shared.models.audio import AudioAnalysis, ClipBoundary, Lyric
from shared.models.scene import ClipScript
from shared.logging import get_logger

logger = get_logger("scene_planner")


def generate_clip_scripts(
    llm_output: dict,
    clip_boundaries: List[ClipBoundary],
    lyrics: List[Lyric]
) -> List[ClipScript]:
    """
    Transform LLM output into structured clip scripts.
    
    Args:
        llm_output: LLM JSON response containing clip_scripts array
        clip_boundaries: List of clip boundaries from audio analysis
        lyrics: List of lyrics with timestamps
        
    Returns:
        List of ClipScript objects aligned to boundaries
        
    Raises:
        ValueError: If clip scripts don't match boundaries count
    """
    # Extract clip scripts from LLM output
    if "clip_scripts" not in llm_output:
        raise ValueError("LLM output missing 'clip_scripts' field")
    
    llm_clip_scripts = llm_output["clip_scripts"]
    
    # Validate count matches
    if len(llm_clip_scripts) != len(clip_boundaries):
        logger.warning(
            f"Clip script count mismatch: LLM generated {len(llm_clip_scripts)}, "
            f"expected {len(clip_boundaries)}. Adjusting to match boundaries."
        )
        # Adjust: truncate or pad as needed
        if len(llm_clip_scripts) > len(clip_boundaries):
            llm_clip_scripts = llm_clip_scripts[:len(clip_boundaries)]
        else:
            # Pad with simple scripts
            for i in range(len(llm_clip_scripts), len(clip_boundaries)):
                boundary = clip_boundaries[i]
                llm_clip_scripts.append({
                    "clip_index": i,
                    "start": boundary.start,
                    "end": boundary.end,
                    "visual_description": "Scene continuation",
                    "motion": "Static shot",
                    "camera_angle": "Medium shot",
                    "characters": [],
                    "scenes": [],
                    "lyrics_context": None,
                    "beat_intensity": "medium"
                })
    
    # Generate ClipScript objects
    clip_scripts = []
    for i, (llm_script, boundary) in enumerate(zip(llm_clip_scripts, clip_boundaries)):
        # Align to boundary (use boundary times, but allow ±0.5s tolerance)
        start = boundary.start
        end = boundary.end
        
        # Extract lyrics for this clip
        lyrics_context = _align_lyrics_to_clip(start, end, lyrics)
        
        # Create ClipScript
        clip_script = ClipScript(
            clip_index=i,
            start=start,
            end=end,
            visual_description=llm_script.get("visual_description", "Scene"),
            motion=llm_script.get("motion", "Static shot"),
            camera_angle=llm_script.get("camera_angle", "Medium shot"),
            characters=llm_script.get("characters", []),
            scenes=llm_script.get("scenes", []),
            lyrics_context=lyrics_context or llm_script.get("lyrics_context"),
            beat_intensity=llm_script.get("beat_intensity", "medium")
        )
        
        clip_scripts.append(clip_script)
    
    logger.info(
        f"Generated {len(clip_scripts)} clip scripts",
        extra={"clip_count": len(clip_scripts)}
    )
    
    return clip_scripts


def _align_lyrics_to_clip(
    clip_start: float,
    clip_end: float,
    lyrics: List[Lyric]
) -> Optional[str]:
    """
    Find lyrics within clip time range and return combined formatted text.
    
    Uses formatted_text (sentences/phrases) when available for better readability.
    
    Args:
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        lyrics: List of lyrics with timestamps and formatted_text
        
    Returns:
        Combined lyrics text (formatted phrases) or None if no lyrics in range
    """
    # Find lyrics within clip time range
    clip_lyrics = [
        lyric
        for lyric in lyrics
        if clip_start <= lyric.timestamp <= clip_end
    ]
    
    if not clip_lyrics:
        return None
    
    # Use formatted_text if available, otherwise fall back to individual words
    if clip_lyrics[0].formatted_text:
        # Group by unique phrases to avoid repetition
        seen_phrases = set()
        phrases = []
        for lyric in clip_lyrics:
            if lyric.formatted_text and lyric.formatted_text not in seen_phrases:
                seen_phrases.add(lyric.formatted_text)
                phrases.append(lyric.formatted_text)
        return " ".join(phrases) if phrases else None
    else:
        # Fallback: use individual words
        words = [lyric.text for lyric in clip_lyrics]
        return " ".join(words) if words else None

