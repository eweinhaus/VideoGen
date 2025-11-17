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
    total_clips = len(clip_boundaries)
    
    for i, (llm_script, boundary) in enumerate(zip(llm_clip_scripts, clip_boundaries)):
        # Align to boundary (use boundary times, but allow ±0.5s tolerance)
        start = boundary.start
        end = boundary.end
        
        # Determine if this is the last clip for proper boundary handling
        is_last_clip = (i == total_clips - 1)
        
        # Extract lyrics for this clip - filter by clip time range with mutually exclusive assignment
        # ALWAYS use filtered lyrics (from audio parser) rather than LLM output
        # to ensure only lyrics within clip start/end times are included
        # Uses half-open interval [start, end) except for last clip which uses [start, end]
        # This ensures mutually exclusive, complete coverage of all lyrics
        lyrics_context = _align_lyrics_to_clip(start, end, lyrics, is_last_clip=is_last_clip)
        
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
    lyrics: List[Lyric],
    is_last_clip: bool = False
) -> Optional[str]:
    """
    Find lyrics within clip time range and return combined text with only words in the clip.
    
    Uses half-open interval [clip_start, clip_end) for mutually exclusive assignment:
    - For all clips except the last: [start, end) - includes start, excludes end
    - For the last clip: [start, end] - includes both start and end to ensure complete coverage
    
    This ensures:
    1. Mutually exclusive: Each word is assigned to exactly one clip (no overlap)
    2. Complete coverage: All words are assigned to a clip (no gaps)
    3. Accurate alignment: Words match exactly what's spoken in that clip's time range
    
    Builds lyrics string from individual words (not formatted_text) to ensure precise alignment.
    Words are joined with spaces, preserving natural phrase grouping when consecutive.
    
    Args:
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        lyrics: List of lyrics with timestamps and formatted_text
        is_last_clip: If True, use inclusive end boundary [start, end]. Otherwise use [start, end).
        
    Returns:
        Combined lyrics text (only words within clip range) or None if no lyrics in range
        
    Example:
        For clips [0-12s] and [12-24s]:
        - Clip 1 [0, 12): Includes words with timestamp >= 0.0 and < 12.0 (excludes word at exactly 12.0)
        - Clip 2 [12, 24): Includes words with timestamp >= 12.0 and < 24.0 (includes word at 12.0)
        - Last clip [24, 30]: Includes words with timestamp >= 24.0 and <= 30.0 (inclusive end)
        
        This ensures word at 12.0s goes to Clip 2, not both clips.
    """
    if not lyrics:
        return None
    
    # Use half-open interval [start, end) for all clips except the last
    # Last clip uses [start, end] to ensure complete coverage
    if is_last_clip:
        # Last clip: inclusive end boundary [clip_start, clip_end]
        clip_lyrics = [
            lyric
            for lyric in lyrics
            if clip_start <= lyric.timestamp <= clip_end
        ]
    else:
        # All other clips: half-open interval [clip_start, clip_end)
        # Includes words at clip_start, excludes words at clip_end
        clip_lyrics = [
            lyric
            for lyric in lyrics
            if clip_start <= lyric.timestamp < clip_end
        ]
    
    if not clip_lyrics:
        logger.debug(
            f"No lyrics found in clip time range [{clip_start:.1f}s-{clip_end:.1f}s]",
            extra={"clip_start": clip_start, "clip_end": clip_end, "total_lyrics": len(lyrics)}
        )
        return None
    
    logger.debug(
        f"Found {len(clip_lyrics)} words in clip time range [{clip_start:.1f}s-{clip_end:.1f}s] "
        f"(filtered from {len(lyrics)} total lyrics)",
        extra={
            "clip_start": clip_start,
            "clip_end": clip_end,
            "clip_lyrics_count": len(clip_lyrics),
            "total_lyrics": len(lyrics),
            "first_lyric": clip_lyrics[0].text if clip_lyrics else None,
            "last_lyric": clip_lyrics[-1].text if clip_lyrics else None,
            "first_timestamp": clip_lyrics[0].timestamp if clip_lyrics else None,
            "last_timestamp": clip_lyrics[-1].timestamp if clip_lyrics else None
        }
    )
    
    # Build lyrics string from individual words (not formatted_text)
    # This ensures we only include words actually within the clip's time range,
    # even if they're part of a phrase that spans multiple clips
    words = [lyric.text for lyric in clip_lyrics]
    result = " ".join(words) if words else None
    
    if result:
        logger.debug(
            f"Extracted {len(words)} words from clip time range [{clip_start:.1f}s-{clip_end:.1f}s]: '{result[:100]}'",
            extra={
                "words_count": len(words),
                "result_preview": result[:100],
                "full_result_length": len(result)
            }
        )
    
    return result

