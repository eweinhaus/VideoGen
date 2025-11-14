"""
Clip boundary generation.

Generate beat-aligned clip boundaries (4-8s clips, minimum 3).
"""

from typing import List

from shared.models.audio import ClipBoundary
from shared.logging import get_logger

logger = get_logger("audio_parser")


def _snap_to_beat(timestamp: float, beat_timestamps: List[float], threshold: float = 0.1) -> float:
    """
    Snap timestamp to nearest beat if within threshold (±100ms default).
    
    Args:
        timestamp: Timestamp to snap
        beat_timestamps: List of beat timestamps
        threshold: Threshold in seconds (default: 0.1)
        
    Returns:
        Snapped timestamp
    """
    if not beat_timestamps:
        return timestamp
    
    # Find nearest beat
    nearest_beat = min(beat_timestamps, key=lambda b: abs(b - timestamp))
    
    # Calculate distance
    distance = abs(nearest_beat - timestamp)
    
    # If within threshold, snap to beat
    if distance <= threshold:
        return nearest_beat
    
    # Otherwise return original timestamp
    return timestamp


def generate_boundaries(
    beat_timestamps: List[float],
    duration: float,
    bpm: float,
    min_clips: int = 3,
    min_duration: float = 4.0,
    max_duration: float = 8.0
) -> List[ClipBoundary]:
    """
    Generate clip boundaries aligned to beats, 4-8s duration, minimum 3 clips.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        duration: Total duration in seconds
        bpm: Beats per minute
        min_clips: Minimum number of clips (default: 3)
        min_duration: Minimum clip duration in seconds (default: 4.0)
        max_duration: Maximum clip duration in seconds (default: 8.0)
        
    Returns:
        List of ClipBoundary objects
    """
    try:
        if not beat_timestamps:
            # Fallback: generate boundaries without beats
            logger.warning("No beat timestamps available, generating uniform boundaries")
            target_duration = (min_duration + max_duration) / 2
            n_clips = max(min_clips, int(duration / target_duration))
            clip_duration = duration / n_clips
            
            boundaries = []
            for i in range(n_clips):
                start = i * clip_duration
                end = (i + 1) * clip_duration if i < n_clips - 1 else duration
                boundaries.append(ClipBoundary(
                    start=start,
                    end=end,
                    duration=end - start
                ))
            
            return boundaries
        
        # 1. Calculate target clip duration
        # Ideal: 6 seconds (middle of 4-8s range)
        ideal_duration = 6.0
        
        # Adjust based on total duration and min_clips requirement
        min_total_duration = min_clips * min_duration
        if duration < min_total_duration:
            # Very short song: use minimum duration
            target_duration = min_duration
        else:
            # Use ideal duration, but ensure we get at least min_clips
            max_clips_with_ideal = int(duration / ideal_duration)
            if max_clips_with_ideal < min_clips:
                # Need more clips: reduce duration per clip
                target_duration = duration / min_clips
                target_duration = max(min_duration, min(target_duration, max_duration))
            else:
                target_duration = ideal_duration
        
        logger.debug(f"Target clip duration: {target_duration:.2f}s")
        
        # 2. Generate boundaries aligned to beats
        boundaries = []
        current_start = beat_timestamps[0] if beat_timestamps else 0.0
        
        beat_idx = 0
        
        while current_start < duration and len(boundaries) < 100:  # Safety limit
            # Find next beat that is >= min_duration away
            next_beat_idx = beat_idx + 1
            while next_beat_idx < len(beat_timestamps) and \
                  beat_timestamps[next_beat_idx] - current_start < min_duration:
                next_beat_idx += 1
            
            if next_beat_idx < len(beat_timestamps):
                # Found a beat that's far enough
                potential_end = beat_timestamps[next_beat_idx]
                
                # Check if it exceeds max_duration
                if potential_end - current_start > max_duration:
                    # Use max_duration instead
                    end = current_start + max_duration
                else:
                    end = potential_end
                
                # Snap to nearest beat
                end = _snap_to_beat(end, beat_timestamps, threshold=0.1)
                
                # Ensure end doesn't exceed duration
                end = min(end, duration)
                
                # Create boundary
                clip_duration = end - current_start
                if clip_duration >= min_duration:
                    boundaries.append(ClipBoundary(
                        start=current_start,
                        end=end,
                        duration=clip_duration
                    ))
                    
                    # Move to next boundary start
                    current_start = end
                    beat_idx = next_beat_idx
                else:
                    # Skip this beat, try next
                    beat_idx += 1
                    if beat_idx < len(beat_timestamps):
                        current_start = beat_timestamps[beat_idx]
                    else:
                        break
            else:
                # No more beats, extend to duration
                end = duration
                clip_duration = end - current_start
                if clip_duration >= min_duration:
                    boundaries.append(ClipBoundary(
                        start=current_start,
                        end=end,
                        duration=clip_duration
                    ))
                break
        
        # 3. Validate: ensure at least min_clips boundaries
        if len(boundaries) < min_clips:
            logger.warning(
                f"Only {len(boundaries)} boundaries generated, need {min_clips}. "
                "Regenerating with reduced duration per clip."
            )
            # Reduce duration per clip and regenerate
            target_duration = duration / min_clips
            target_duration = max(min_duration, min(target_duration, max_duration))
            
            # Regenerate with uniform boundaries
            boundaries = []
            clip_duration = duration / min_clips
            for i in range(min_clips):
                start = i * clip_duration
                end = (i + 1) * clip_duration if i < min_clips - 1 else duration
                
                # Snap to nearest beats
                start = _snap_to_beat(start, beat_timestamps, threshold=0.1)
                end = _snap_to_beat(end, beat_timestamps, threshold=0.1)
                
                boundaries.append(ClipBoundary(
                    start=start,
                    end=end,
                    duration=end - start
                ))
        
        # 4. Validate all boundaries are within [0, duration]
        validated_boundaries = []
        for boundary in boundaries:
            start = max(0.0, boundary.start)
            end = min(duration, boundary.end)
            if start < end:
                validated_boundaries.append(ClipBoundary(
                    start=start,
                    end=end,
                    duration=end - start
                ))
        
        logger.info(f"Generated {len(validated_boundaries)} clip boundaries")
        return validated_boundaries
        
    except Exception as e:
        logger.error(f"Boundary generation failed: {str(e)}")
        # Fallback: generate uniform boundaries
        logger.warning("Using fallback uniform boundaries")
        n_clips = max(min_clips, int(duration / 6.0))
        clip_duration = duration / n_clips
        
        boundaries = []
        for i in range(n_clips):
            start = i * clip_duration
            end = (i + 1) * clip_duration if i < n_clips - 1 else duration
            boundaries.append(ClipBoundary(
                start=start,
                end=end,
                duration=end - start
            ))
        
        return boundaries

