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
    max_clips: int = None
) -> List[ClipBoundary]:
    """
    Generate clip boundaries aligned to beats.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        bpm: Beats per minute
        total_duration: Total audio duration in seconds
        max_clips: Maximum number of clips (default: None, calculates based on duration)
                   Roughly targets ~20 clips for typical songs, but flexible
        
    Returns:
        List of ClipBoundary objects
    """
    # Calculate target number of clips if not specified
    # Roughly ~20 clips for typical songs, but flexible based on duration
    if max_clips is None:
        # Target ~5 seconds per clip on average (middle of 3-7s range)
        target_clips = int(total_duration / 5.0)
        # But keep it reasonable: 10-30 clips for most songs
        max_clips = max(10, min(30, target_clips))
    # Edge case 1: Very short songs (<9s) → Create fewer segments to ensure 3s minimum
    # The model requires 3-7s per segment, so for songs <9s, we can't have 3 segments
    # Instead, create 1-2 segments that meet the 3s minimum requirement
    if total_duration < 9.0:
        boundaries = []
        # For songs <9s, create segments that are at least 3s each
        # If duration < 3s, create 1 segment (edge case)
        # If 3s <= duration < 6s, create 1 segment
        # If 6s <= duration < 9s, create 2 segments
        
        if total_duration < 3.0:
            # Very short: single segment covering entire duration
            boundaries.append(ClipBoundary(
                start=0.0,
                end=total_duration,
                duration=total_duration
            ))
        elif total_duration < 6.0:
            # Short: single segment
            boundaries.append(ClipBoundary(
                start=0.0,
                end=total_duration,
                duration=total_duration
            ))
        else:
            # 6s <= duration < 9s: create 2 segments of ~3-5s each
            # Ensure both segments are at least 3s
            mid_point = max(3.0, total_duration - 3.0)  # Ensure second segment is at least 3s
            if mid_point > total_duration - 3.0:
                mid_point = total_duration / 2.0  # If possible, split evenly
            
            boundaries.append(ClipBoundary(
                start=0.0,
                end=mid_point,
                duration=mid_point
            ))
            second_duration = total_duration - mid_point
            # Ensure second segment is at least 3s
            if second_duration < 3.0:
                # Adjust mid_point to ensure second segment is 3s
                mid_point = total_duration - 3.0
                # Recreate first boundary with adjusted end
                boundaries[0] = ClipBoundary(
                    start=0.0,
                    end=mid_point,
                    duration=mid_point
                )
                second_duration = 3.0
            
            boundaries.append(ClipBoundary(
                start=mid_point,
                end=total_duration,
                duration=second_duration
            ))
        
        logger.info(f"Very short song ({total_duration:.1f}s), created {len(boundaries)} segments")
        return boundaries
    
    # Edge case 2: No beats detected → Use tempo-based fallback
    if len(beat_timestamps) == 0:
        beat_interval = 60.0 / bpm
        boundaries = []
        current_time = 0.0
        while current_time < total_duration and len(boundaries) < max_clips:
            # Target ~5 seconds (middle of 3-7s range), using 4 beats as base
            end_time = min(current_time + (4 * beat_interval), total_duration)
            duration = end_time - current_time
            # Ensure duration is within 3-7s range
            if duration < 3.0:
                end_time = min(current_time + 3.0, total_duration)
                duration = end_time - current_time
            elif duration > 7.0:
                end_time = min(current_time + 7.0, total_duration)
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
    # Target roughly 5 seconds per clip (middle of 3-7s range), but flexible
    # Add variation: use different beats_per_clip values to create natural variation
    target_duration = 5.0  # Middle of 3-7s range
    beat_interval = np.mean(np.diff(beat_timestamps)) if len(beat_timestamps) > 1 else (60.0 / bpm)
    base_beats_per_clip = max(1, math.ceil(target_duration / beat_interval))
    
    boundaries = []
    current_beat_idx = 0
    clip_index = 0  # Track clip index for variation pattern
    current_start = beat_timestamps[0] if len(beat_timestamps) > 0 else 0.0  # Start at first beat or 0.0
    
    while current_beat_idx < len(beat_timestamps) and len(boundaries) < max_clips:
        # For first clip, start at first beat; for subsequent clips, start where previous ended
        start = current_start
        
        # Find the beat index closest to our start time
        if len(boundaries) > 0:
            # Find the beat that is >= start time
            while current_beat_idx < len(beat_timestamps) and beat_timestamps[current_beat_idx] < start:
                current_beat_idx += 1
        
        # Add variation: alternate between base, base+1, and base-1 beats per clip
        # This creates natural variation in clip durations (roughly 3-7s range)
        variation_pattern = [0, 1, -1, 0, 1, -1, 0]  # Pattern repeats every 7 clips
        beats_variation = variation_pattern[clip_index % len(variation_pattern)]
        beats_per_clip = max(1, base_beats_per_clip + beats_variation)
        
        end_idx = min(current_beat_idx + beats_per_clip, len(beat_timestamps) - 1)
        end = beat_timestamps[end_idx]
        duration = end - start
        
        # Adjust duration to be within 3-7s range
        if duration < 3.0:
            # Extend to next beats to reach at least 3s
            while end_idx < len(beat_timestamps) - 1 and duration < 3.0:
                end_idx += 1
                end = beat_timestamps[end_idx]
                duration = end - start
                if duration >= 3.0:
                    break
            
            # If we've run out of beats and duration is still < 3.0, extend to total_duration
            if duration < 3.0:
                # Extend to total_duration to ensure minimum 3s duration
                end = min(start + 3.0, total_duration)
                duration = end - start
                # If extending to 3s would exceed total_duration, we need to handle this differently
                if duration < 3.0:
                    # This means we're near the end and can't create a 3s clip
                    # Merge with previous boundary if possible, or extend to end
                    if len(boundaries) > 0:
                        # Merge with previous boundary
                        prev_boundary = boundaries[-1]
                        # Create new boundary with merged end
                        boundaries[-1] = ClipBoundary(
                            start=prev_boundary.start,
                            end=total_duration,
                            duration=total_duration - prev_boundary.start
                        )
                        # Skip creating this boundary
                        break
                    else:
                        # First boundary - extend to at least 3s or total_duration
                        end = max(start + 3.0, total_duration)
                        duration = end - start
        
        # Cap duration at 7s maximum
        if duration > 7.0:
            # Find the beat that keeps us closest to 7s without going over
            # Backtrack to find a beat that gives us duration <= 7.0
            while end_idx > current_beat_idx and duration > 7.0:
                end_idx -= 1
                if end_idx > current_beat_idx:
                    end = beat_timestamps[end_idx]
                    duration = end - start
                else:
                    # Can't go back further, cap at 7s
                    end = min(start + 7.0, total_duration)
                    duration = end - start
                    break
        
        # Ensure duration is at least 3.0 before creating boundary
        if duration < 3.0:
            # If we still can't reach 3s, skip this boundary or merge with previous
            if len(boundaries) > 0:
                # Merge with previous boundary
                prev_boundary = boundaries[-1]
                new_end = min(end, total_duration)
                new_duration = new_end - prev_boundary.start
                # Ensure merged duration doesn't exceed 7s
                if new_duration <= 7.0:
                    # Create new boundary with merged end
                    boundaries[-1] = ClipBoundary(
                        start=prev_boundary.start,
                        end=new_end,
                        duration=new_duration
                    )
                # Skip creating this boundary
                continue
            else:
                # First boundary - must be at least 3s or use total_duration
                end = max(start + 3.0, total_duration)
                duration = end - start
        
        # Final safeguard: ensure duration is at least 3.0 and at most 7.0 before creating boundary
        if duration < 3.0:
            # This should not happen after all the checks above, but as a final safeguard
            # extend to ensure minimum duration
            end = min(start + 3.0, total_duration)
            duration = end - start
            # If still < 3.0, we're at the end - merge with previous or skip
            if duration < 3.0 and len(boundaries) > 0:
                prev_boundary = boundaries[-1]
                boundaries[-1] = ClipBoundary(
                    start=prev_boundary.start,
                    end=total_duration,
                    duration=total_duration - prev_boundary.start
                )
                continue
        elif duration > 7.0:
            # Cap at 7s maximum
            end = min(start + 7.0, total_duration)
            duration = end - start
        
        boundaries.append(ClipBoundary(
            start=start,
            end=end,
            duration=duration
        ))
        
        # Next clip starts exactly where this one ends (ensuring no gaps)
        current_start = end
        # Move to the beat index after the end beat for next iteration
        current_beat_idx = end_idx + 1
        clip_index += 1
    
    # Ensure minimum 1 clip (for very short songs, we may have fewer than 3)
    if len(boundaries) < 1:
        # Fallback: create at least 1 clip
        if total_duration < 3.0:
            return [ClipBoundary(start=0.0, end=total_duration, duration=total_duration)]
        else:
            return _create_equal_segments(total_duration, min(3, int(total_duration / 3.0)))
    
    # Trim last clip to end if needed - smart extension
    # Extend last clip to cover full duration if reasonable (≤10s), otherwise create new clip
    if boundaries[-1].end < total_duration:
        new_end = total_duration
        new_duration = new_end - boundaries[-1].start
        
        # Smart extension: extend if new duration ≤ 10s (reasonable limit)
        if new_duration <= 10.0:
            # Extend the last boundary to cover full duration
            prev_boundary = boundaries[-1]
            boundaries[-1] = ClipBoundary(
                start=prev_boundary.start,
                end=new_end,
                duration=new_duration
            )
            logger.info(f"Extended last boundary to cover full duration: {prev_boundary.end:.1f}s -> {new_end:.1f}s (duration: {new_duration:.1f}s)")
        else:
            # If extending would exceed 10s, create additional clip if there's enough time
            remaining_time = total_duration - boundaries[-1].end
            if remaining_time >= 3.0 and len(boundaries) < max_clips:
                boundaries.append(ClipBoundary(
                    start=boundaries[-1].end,
                    end=total_duration,
                    duration=remaining_time
                ))
                logger.info(f"Created additional clip for remaining {remaining_time:.1f}s (last clip would have been {new_duration:.1f}s)")
            else:
                # If we can't create a new clip (too short or max_clips reached), extend anyway
                # This ensures we cover the full audio duration
                prev_boundary = boundaries[-1]
                boundaries[-1] = ClipBoundary(
                    start=prev_boundary.start,
                    end=new_end,
                    duration=new_duration
                )
                logger.info(f"Extended last boundary beyond 10s limit to cover full duration: {prev_boundary.end:.1f}s -> {new_end:.1f}s (duration: {new_duration:.1f}s)")
    
    # Final validation: ensure all boundaries have duration >= 3.0 and <= 10.0
    # Allow last boundary to extend up to 10s to cover full audio, but prefer 3-7s range
    # Filter out any boundaries that don't meet the range and merge/skip as needed
    validated_boundaries = []
    for i, boundary in enumerate(boundaries):
        # Last boundary can be up to 10s (to cover full audio), others should be 3-7s
        max_duration = 10.0 if i == len(boundaries) - 1 else 7.0
        if 3.0 <= boundary.duration <= max_duration:
            validated_boundaries.append(boundary)
        elif boundary.duration < 3.0:
            # If duration < 3.0, try to merge with previous or next boundary
            if len(validated_boundaries) > 0:
                # Merge with previous boundary
                prev_boundary = validated_boundaries[-1]
                new_end = min(boundary.end, total_duration)
                new_duration = new_end - prev_boundary.start
                # Ensure merged duration is still <= 7.0
                if new_duration <= 7.0:
                    # Create new boundary with merged end
                    validated_boundaries[-1] = ClipBoundary(
                        start=prev_boundary.start,
                        end=new_end,
                        duration=new_duration
                    )
                else:
                    # Can't merge without violating 7s maximum, skip this boundary
                    continue
            elif i < len(boundaries) - 1:
                # Merge with next boundary (skip this one, extend next)
                next_boundary = boundaries[i + 1]
                new_start = boundary.start
                new_duration = next_boundary.end - new_start
                if new_duration <= 7.0:
                    validated_boundaries.append(ClipBoundary(
                        start=new_start,
                        end=next_boundary.end,
                        duration=new_duration
                    ))
            else:
                # Last boundary - extend to ensure >= 3.0
                new_end = max(boundary.start + 3.0, total_duration)
                new_duration = new_end - boundary.start
                if new_duration <= 7.0:
                    validated_boundaries.append(ClipBoundary(
                        start=boundary.start,
                        end=new_end,
                        duration=new_duration
                    ))
        elif boundary.duration > 7.0:
            # If duration > 7.0, allow it if it's the last boundary and ≤ 10s
            # Otherwise, cap at 7.0
            if i == len(boundaries) - 1 and boundary.duration <= 10.0:
                # Last boundary can extend up to 10s to cover full audio
                validated_boundaries.append(boundary)
            else:
                # Cap at 7.0 for non-last boundaries
                validated_boundaries.append(ClipBoundary(
                    start=boundary.start,
                    end=min(boundary.start + 7.0, total_duration),
                    duration=min(7.0, total_duration - boundary.start)
                ))
    
    # Use validated boundaries if we filtered any out, otherwise use original
    # Only replace if we have validated boundaries (don't lose all boundaries)
    if len(validated_boundaries) > 0 and len(validated_boundaries) != len(boundaries):
        boundaries = validated_boundaries
    elif len(validated_boundaries) == 0:
        # All boundaries were invalid - this shouldn't happen, but ensure we have at least one
        # Extend the last boundary to meet minimum
        if boundaries:
            last_boundary = boundaries[-1]
            last_boundary = ClipBoundary(
                start=last_boundary.start,
                end=max(last_boundary.start + 3.0, total_duration),
                duration=max(3.0, min(7.0, total_duration - last_boundary.start))
            )
            boundaries = [last_boundary]
    
    logger.info(f"Generated {len(boundaries)} beat-aligned clip boundaries")
    return boundaries[:max_clips]


def _create_equal_segments(duration: float, num_segments: int) -> List[ClipBoundary]:
    """Create equal-length segments, ensuring durations are in 3-7s range."""
    # For very short songs, we may need to adjust
    # If total duration is less than 9s, we already handled it in the main function
    # This function is called when we need minimum 3 clips but can't fit 3-7s each
    # In that case, we'll create segments that are as close to 3s as possible
    
    if duration < 9.0:
        # For songs <9s, create 3 segments with minimum 3s each where possible
        # But if duration < 9s, we already handled it above, so this shouldn't be called
        # However, if it is called, ensure minimum 3s per segment
        min_segment_duration = max(3.0, duration / num_segments)
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
            
            # Ensure duration is at least 3s (or as close as possible)
            if seg_duration < 3.0 and i < num_segments - 1:
                end_time = min(current_time + 3.0, duration)
                seg_duration = end_time - current_time
            
            # Ensure duration doesn't exceed 7s
            if seg_duration > 7.0:
                end_time = current_time + 7.0
                seg_duration = 7.0
            
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
    
    # Ensure segment duration is in 3-7s range
    if segment_duration < 3.0:
        # If segments would be too short, reduce number of segments
        num_segments = max(3, int(duration / 3.0))
        segment_duration = duration / num_segments
    elif segment_duration > 7.0:
        # If segments would be too long, increase number of segments
        num_segments = max(3, int(duration / 7.0))
        segment_duration = duration / num_segments
    
    return [
        ClipBoundary(
            start=i * segment_duration,
            end=(i + 1) * segment_duration if i < num_segments - 1 else duration,
            duration=segment_duration if i < num_segments - 1 else (duration - (num_segments - 1) * segment_duration)
        )
        for i in range(num_segments)
    ]
