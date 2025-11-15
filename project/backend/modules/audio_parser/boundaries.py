"""
Clip boundary generation component.

Generate beat-aligned clip boundaries for video segmentation.
"""

import math
import numpy as np
from typing import List
from shared.models.audio import ClipBoundary
from shared.logging import get_logger

logger = get_logger("audio_parser")


def generate_boundaries(
    beat_timestamps: List[float], 
    bpm: float, 
    total_duration: float,
    max_clips: int = 20
) -> List[ClipBoundary]:
    """
    Generate clip boundaries aligned to beats.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        bpm: Beats per minute
        total_duration: Total audio duration in seconds
        max_clips: Maximum number of clips (default: 20)
        
    Returns:
        List of ClipBoundary objects
    """
    # Edge case 1: Very short songs (<12s) → Create fewer segments to ensure 4s minimum
    # The model requires 4-8s per segment, so for songs <12s, we can't have 3 segments
    # Instead, create 1-2 segments that meet the 4s minimum requirement
    if total_duration < 12.0:
        boundaries = []
        # For songs <12s, create segments that are at least 4s each
        # If duration < 4s, create 1 segment (edge case)
        # If 4s <= duration < 8s, create 1 segment
        # If 8s <= duration < 12s, create 2 segments
        
        if total_duration < 4.0:
            # Very short: single segment covering entire duration
            boundaries.append(ClipBoundary(
                start=0.0,
                end=total_duration,
                duration=total_duration
            ))
        elif total_duration < 8.0:
            # Short: single segment
            boundaries.append(ClipBoundary(
                start=0.0,
                end=total_duration,
                duration=total_duration
            ))
        else:
            # 8s <= duration < 12s: create 2 segments of ~4-6s each
            mid_point = total_duration / 2.0
            boundaries.append(ClipBoundary(
                start=0.0,
                end=mid_point,
                duration=mid_point
            ))
            boundaries.append(ClipBoundary(
                start=mid_point,
                end=total_duration,
                duration=total_duration - mid_point
            ))
        
        logger.info(f"Very short song ({total_duration:.1f}s), created {len(boundaries)} segments")
        return boundaries
    
    # Edge case 2: No beats detected → Use tempo-based fallback
    if len(beat_timestamps) == 0:
        beat_interval = 60.0 / bpm
        boundaries = []
        current_time = 0.0
        while current_time < total_duration and len(boundaries) < max_clips:
            end_time = min(current_time + (4 * beat_interval), total_duration)
            duration = end_time - current_time
            # Ensure duration is within 4-8s range
            if duration < 4.0:
                end_time = min(current_time + 4.0, total_duration)
                duration = end_time - current_time
            elif duration > 8.0:
                end_time = min(current_time + 8.0, total_duration)
                duration = end_time - current_time
            
            boundaries.append(ClipBoundary(
                start=current_time,
                end=end_time,
                duration=duration
            ))
            current_time = end_time
        
        # Ensure minimum 3 clips
        if len(boundaries) < 3:
            return _create_equal_segments(total_duration, 3)
        
        logger.info(f"No beats detected, created {len(boundaries)} tempo-based boundaries")
        return boundaries[:max_clips]
    
    # Normal case: Beat-aligned boundaries
    target_duration = 6.0  # Middle of 4-8s range
    beat_interval = np.mean(np.diff(beat_timestamps)) if len(beat_timestamps) > 1 else (60.0 / bpm)
    beats_per_clip = max(1, math.ceil(target_duration / beat_interval))
    
    boundaries = []
    current_beat_idx = 0
    
    while current_beat_idx < len(beat_timestamps) and len(boundaries) < max_clips:
        start = beat_timestamps[current_beat_idx]
        end_idx = min(current_beat_idx + beats_per_clip, len(beat_timestamps) - 1)
        end = beat_timestamps[end_idx]
        duration = end - start
        
        # Adjust duration to fit 4-8s range
        if duration < 4.0:
            # Extend to next beats (up to 8s max)
            while end_idx < len(beat_timestamps) - 1 and duration < 8.0:
                end_idx += 1
                end = beat_timestamps[end_idx]
                duration = end - start
                if duration >= 8.0:
                    break
        elif duration > 8.0:
            # Find nearest beat to 8s mark
            target_end = start + 8.0
            nearest_idx = min(
                range(current_beat_idx, len(beat_timestamps)),
                key=lambda i: abs(beat_timestamps[i] - target_end)
            )
            end = beat_timestamps[nearest_idx]
            duration = end - start
        
        # Ensure duration is within valid range
        if duration < 4.0:
            duration = 4.0
            end = start + duration
        elif duration > 8.0:
            duration = 8.0
            end = start + duration
        
        boundaries.append(ClipBoundary(
            start=start,
            end=end,
            duration=duration
        ))
        
        current_beat_idx = end_idx + 1
    
    # Ensure minimum 1 clip (for very short songs, we may have fewer than 3)
    if len(boundaries) < 1:
        # Fallback: create at least 1 clip
        if total_duration < 4.0:
            return [ClipBoundary(start=0.0, end=total_duration, duration=total_duration)]
        else:
            return _create_equal_segments(total_duration, min(3, int(total_duration / 4.0)))
    
    # Trim last clip to end if needed, but ensure duration doesn't exceed 8s
    if boundaries[-1].end < total_duration:
        new_end = total_duration
        new_duration = new_end - boundaries[-1].start
        # If extending would exceed 8s, create additional clip if there's enough time
        if new_duration <= 8.0:
            boundaries[-1].end = new_end
            boundaries[-1].duration = new_duration
        else:
            # Can't extend last clip without exceeding 8s
            # Create additional clip if remaining time is >= 4s and <= 8s
            remaining_time = total_duration - boundaries[-1].end
            if remaining_time >= 4.0 and remaining_time <= 8.0 and len(boundaries) < max_clips:
                boundaries.append(ClipBoundary(
                    start=boundaries[-1].end,
                    end=total_duration,
                    duration=remaining_time
                ))
            # If remaining time > 8s, we'd need multiple clips, but that's complex
            # For now, just leave the last clip as is (it's already valid)
    
    logger.info(f"Generated {len(boundaries)} beat-aligned clip boundaries")
    return boundaries[:max_clips]


def _create_equal_segments(duration: float, num_segments: int) -> List[ClipBoundary]:
    """Create equal-length segments, ensuring durations are in 4-8s range."""
    # For very short songs, we may need to adjust
    # If total duration is less than 12s, we already handled it in the main function
    # This function is called when we need minimum 3 clips but can't fit 4-8s each
    # In that case, we'll create segments that are as close to 4s as possible
    
    if duration < 12.0:
        # For songs <12s, create 3 segments with minimum 4s each where possible
        # But if duration < 12s, we already handled it above, so this shouldn't be called
        # However, if it is called, ensure minimum 4s per segment
        min_segment_duration = max(4.0, duration / num_segments)
        segments = []
        current_time = 0.0
        for i in range(num_segments):
            if i == num_segments - 1:
                # Last segment takes remaining time
                end_time = duration
                seg_duration = end_time - current_time
            else:
                end_time = min(current_time + min_segment_duration, duration)
                seg_duration = end_time - current_time
            
            # Ensure duration is at least 4s (or as close as possible)
            if seg_duration < 4.0 and i < num_segments - 1:
                end_time = min(current_time + 4.0, duration)
                seg_duration = end_time - current_time
            
            # Ensure duration doesn't exceed 8s
            if seg_duration > 8.0:
                end_time = current_time + 8.0
                seg_duration = 8.0
            
            segments.append(ClipBoundary(
                start=current_time,
                end=end_time,
                duration=seg_duration
            ))
            current_time = end_time
            if current_time >= duration:
                break
        
        return segments
    
    # For longer songs, create equal segments
    segment_duration = duration / num_segments
    
    # Ensure segment duration is in 4-8s range
    if segment_duration < 4.0:
        # If segments would be too short, reduce number of segments
        num_segments = max(3, int(duration / 4.0))
        segment_duration = duration / num_segments
    elif segment_duration > 8.0:
        # If segments would be too long, increase number of segments
        num_segments = max(3, int(duration / 8.0))
        segment_duration = duration / num_segments
    
    return [
        ClipBoundary(
            start=i * segment_duration,
            end=(i + 1) * segment_duration if i < num_segments - 1 else duration,
            duration=segment_duration if i < num_segments - 1 else (duration - (num_segments - 1) * segment_duration)
        )
        for i in range(num_segments)
    ]
