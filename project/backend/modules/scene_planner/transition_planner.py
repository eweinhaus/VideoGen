"""
Transition planning based on beat intensity and song structure.

Generates transition plans between clips based on beat intensity,
song structure, and energy levels.
"""

from typing import List, Literal, Tuple
from shared.models.audio import AudioAnalysis, SongStructure
from shared.models.scene import ClipScript, Transition
from shared.logging import get_logger

logger = get_logger("scene_planner")


def plan_transitions(
    clip_scripts: List[ClipScript],
    beat_timestamps: List[float],
    song_structure: List[SongStructure]
) -> List[Transition]:
    """
    Generate transition plan between clips based on beat intensity.
    
    Args:
        clip_scripts: List of clip scripts
        beat_timestamps: List of beat timestamps in seconds
        song_structure: List of song structure segments
        
    Returns:
        List of Transition objects (N-1 transitions for N clips)
    """
    if len(clip_scripts) < 2:
        return []  # No transitions needed for single clip
    
    transitions = []
    
    for i in range(len(clip_scripts) - 1):
        current_clip = clip_scripts[i]
        next_clip = clip_scripts[i + 1]
        
        # Transition point is at the end of current clip
        transition_time = current_clip.end
        
        # Analyze beat intensity at transition point
        beat_intensity = _get_beat_intensity_at_time(
            transition_time,
            beat_timestamps
        )
        
        # Check song structure at transition point
        structure_context = _get_structure_context(
            transition_time,
            song_structure
        )
        
        # Determine transition type
        transition_type, duration, rationale = _determine_transition(
            beat_intensity,
            structure_context,
            current_clip,
            next_clip
        )
        
        transition = Transition(
            from_clip=i,
            to_clip=i + 1,
            type=transition_type,
            duration=duration,
            rationale=rationale
        )
        
        transitions.append(transition)
    
    logger.info(
        f"Planned {len(transitions)} transitions",
        extra={"transition_count": len(transitions)}
    )
    
    return transitions


def _get_beat_intensity_at_time(
    timestamp: float,
    beat_timestamps: List[float],
    window: float = 0.5
) -> Literal["low", "medium", "high"]:
    """
    Count beats within window around timestamp and classify intensity.
    
    Args:
        timestamp: Time to analyze
        beat_timestamps: List of all beat timestamps
        window: Time window in seconds (±window/2)
        
    Returns:
        "low", "medium", or "high" intensity
    """
    window_start = timestamp - window / 2
    window_end = timestamp + window / 2
    
    beats_in_window = [
        beat
        for beat in beat_timestamps
        if window_start <= beat <= window_end
    ]
    
    beat_count = len(beats_in_window)
    
    # Classify intensity
    if beat_count >= 3:
        return "high"
    elif beat_count >= 1:
        return "medium"
    else:
        return "low"


def _get_structure_context(
    timestamp: float,
    song_structure: List[SongStructure]
) -> dict:
    """
    Get song structure context at timestamp.
    
    Args:
        timestamp: Time to analyze
        song_structure: List of song structure segments
        
    Returns:
        Dict with current_segment, next_segment, transition_type
    """
    current_segment = None
    next_segment = None
    
    for segment in song_structure:
        if segment.start <= timestamp <= segment.end:
            current_segment = segment
            break
    
    # Find next segment
    for segment in song_structure:
        if segment.start > timestamp:
            next_segment = segment
            break
    
    # Determine transition type
    transition_type = None
    if current_segment and next_segment:
        if current_segment.type == "chorus" and next_segment.type == "verse":
            transition_type = "chorus_to_verse"
        elif current_segment.type == "verse" and next_segment.type == "chorus":
            transition_type = "verse_to_chorus"
        elif current_segment.type == "intro" and next_segment.type == "verse":
            transition_type = "intro_to_verse"
        elif current_segment.type == "verse" and next_segment.type == "outro":
            transition_type = "verse_to_outro"
    
    return {
        "current_segment": current_segment,
        "next_segment": next_segment,
        "transition_type": transition_type
    }


def _determine_transition(
    beat_intensity: Literal["low", "medium", "high"],
    structure_context: dict,
    current_clip: ClipScript,
    next_clip: ClipScript
) -> Tuple[Literal["cut", "crossfade", "fade"], float, str]:
    """
    Determine transition type based on beat intensity and structure.
    
    Args:
        beat_intensity: Beat intensity at transition point
        structure_context: Song structure context
        current_clip: Current clip script
        next_clip: Next clip script
        
    Returns:
        Tuple of (transition_type, duration, rationale)
    """
    transition_type = structure_context.get("transition_type")
    current_energy = current_clip.beat_intensity
    next_energy = next_clip.beat_intensity
    
    # Hard cut (0s duration) for high energy
    if beat_intensity == "high" or current_energy == "high" or next_energy == "high":
        if transition_type == "verse_to_chorus" or transition_type == "chorus_to_verse":
            return (
                "cut",
                0.0,
                f"Hard cut on strong beat for high energy transition ({transition_type})"
            )
        return (
            "cut",
            0.0,
            f"Hard cut on strong beat (beat intensity: {beat_intensity})"
        )
    
    # Crossfade (0.5s duration) for medium energy
    if beat_intensity == "medium" or current_energy == "medium" or next_energy == "medium":
        if transition_type == "verse_to_verse":
            return (
                "crossfade",
                0.5,
                f"Crossfade for continuous motion (verse to verse)"
            )
        return (
            "crossfade",
            0.5,
            f"Crossfade for medium energy transition (beat intensity: {beat_intensity})"
        )
    
    # Fade (0.5s duration) for low energy
    if transition_type == "intro_to_verse" or transition_type == "verse_to_outro":
        return (
            "fade",
            0.5,
            f"Fade for {transition_type} transition (low energy section)"
        )
    
    return (
        "fade",
        0.5,
        f"Fade for low energy transition (beat intensity: {beat_intensity})"
    )

