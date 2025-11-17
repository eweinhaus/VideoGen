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
        
        # Extract lyrics for this clip - filter by clip time range
        # ALWAYS use filtered lyrics (from audio parser) rather than LLM output
        # to ensure only lyrics within clip start/end times are included
        lyrics_context = _align_lyrics_to_clip(start, end, lyrics)
        
        # If no lyrics found in this clip's time range, check if LLM provided
        # lyrics_context as fallback, but verify it's actually relevant to this clip
        if not lyrics_context:
            llm_lyrics_context = llm_script.get("lyrics_context")
            if llm_lyrics_context:
                # Log that we're using LLM-provided lyrics (should be rare)
                logger.debug(
                    f"No lyrics found in clip {i} time range [{start:.1f}s-{end:.1f}s], "
                    f"using LLM-provided lyrics_context as fallback",
                    extra={"clip_index": i, "start": start, "end": end}
                )
                lyrics_context = llm_lyrics_context
        else:
            # We have filtered lyrics - always prefer these over LLM output
            # The filtered lyrics are guaranteed to be within the clip's time range
            if llm_script.get("lyrics_context") and llm_script.get("lyrics_context") != lyrics_context:
                logger.debug(
                    f"Clip {i}: Using filtered lyrics_context (from audio parser) instead of LLM output",
                    extra={
                        "clip_index": i,
                        "filtered_lyrics": lyrics_context[:50] if lyrics_context else None,
                        "llm_lyrics": llm_script.get("lyrics_context", "")[:50] if llm_script.get("lyrics_context") else None
                    }
                )
        
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
            lyrics_context=lyrics_context,  # Always use filtered or validated lyrics
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
    
    Only includes lyrics whose timestamps fall within the clip's start and end times.
    This ensures each clip only gets the lyrics snippet relevant to that specific time range,
    rather than the entire lyrics of the song.
    
    Uses formatted_text (sentences/phrases) when available for better readability.
    
    Args:
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        lyrics: List of lyrics with timestamps and formatted_text
        
    Returns:
        Combined lyrics text (formatted phrases) or None if no lyrics in range
        
    Example:
        For a clip from 10.0s to 20.0s:
        - Includes lyrics with timestamp >= 10.0s and <= 20.0s
        - Excludes all other lyrics from the song
    """
    if not lyrics:
        return None
    
    # Find lyrics within clip time range
    # Only include lyrics whose timestamp falls within [clip_start, clip_end]
    clip_lyrics = [
        lyric
        for lyric in lyrics
        if clip_start <= lyric.timestamp <= clip_end
    ]
    
    if not clip_lyrics:
        logger.debug(
            f"No lyrics found in clip time range [{clip_start:.1f}s-{clip_end:.1f}s]",
            extra={"clip_start": clip_start, "clip_end": clip_end, "total_lyrics": len(lyrics)}
        )
        return None
    
    logger.debug(
        f"Found {len(clip_lyrics)} lyrics in clip time range [{clip_start:.1f}s-{clip_end:.1f}s] "
        f"(filtered from {len(lyrics)} total lyrics)",
        extra={
            "clip_start": clip_start,
            "clip_end": clip_end,
            "clip_lyrics_count": len(clip_lyrics),
            "total_lyrics": len(lyrics),
            "first_lyric": clip_lyrics[0].text if clip_lyrics else None,
            "last_lyric": clip_lyrics[-1].text if clip_lyrics else None
        }
    )
    
    # Use formatted_text if available, otherwise fall back to individual words
    if clip_lyrics[0].formatted_text:
        # Group by unique phrases to avoid repetition
        # formatted_text groups words into sentences/phrases
        seen_phrases = set()
        phrases = []
        for lyric in clip_lyrics:
            if lyric.formatted_text and lyric.formatted_text not in seen_phrases:
                seen_phrases.add(lyric.formatted_text)
                phrases.append(lyric.formatted_text)
        result = " ".join(phrases) if phrases else None
        if result:
            logger.debug(
                f"Extracted {len(phrases)} unique phrases from {len(clip_lyrics)} lyrics",
                extra={"phrases_count": len(phrases), "result_preview": result[:100]}
            )
        return result
    else:
        # Fallback: use individual words
        words = [lyric.text for lyric in clip_lyrics]
        result = " ".join(words) if words else None
        if result:
            logger.debug(
                f"Extracted {len(words)} words from {len(clip_lyrics)} lyrics",
                extra={"words_count": len(words), "result_preview": result[:100]}
            )
        return result

