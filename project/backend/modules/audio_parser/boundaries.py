"""
Clip boundary generation component.

Generate beat-aligned clip boundaries for video segmentation.
"""

import math
import numpy as np
from typing import List, Optional, Tuple
from shared.models.audio import ClipBoundary, Breakpoint
from shared.logging import get_logger

logger = get_logger("audio_parser")


def _get_target_duration_for_segment(segment_type: str, beat_intensity: str) -> float:
    """
    Get target duration for a segment based on type and beat intensity.

    PHASE 2.4: Content-based duration selection for better pacing.

    Args:
        segment_type: Type of segment (intro, verse, chorus, bridge, outro)
        beat_intensity: Beat intensity (low, medium, high)

    Returns:
        Target duration in seconds
    """
    # Base durations by segment type
    # Intro/Outro: Slightly shorter (6s) for pacing
    # Verse: Standard (7s) for storytelling
    # Chorus: Slightly longer (7.5s) to emphasize impact
    # Bridge: Varied based on intensity
    base_durations = {
        "intro": 6.0,
        "verse": 7.0,
        "chorus": 7.5,
        "bridge": 6.5,
        "outro": 6.0,
    }

    # Intensity adjustments
    # High intensity: Slightly shorter for faster pacing
    # Low intensity: Slightly longer for contemplative feel
    intensity_adjustments = {
        "high": -0.5,
        "medium": 0.0,
        "low": 0.5,
    }

    # Get base duration (default to 7.0 if segment type not recognized)
    base = base_durations.get(segment_type.lower(), 7.0)

    # Apply intensity adjustment (default to 0.0 if intensity not recognized)
    adjustment = intensity_adjustments.get(beat_intensity.lower(), 0.0)

    # Calculate target, ensuring it stays within 5-8s range
    target = base + adjustment
    return max(5.0, min(8.0, target))


def generate_boundaries(
    beat_timestamps: List[float],
    bpm: float,
    total_duration: float,
    max_clips: int = None,
    segment_type: str = "verse",
    beat_intensity: str = "medium"
) -> List[ClipBoundary]:
    """
    Generate clip boundaries aligned to beats.

    Args:
        beat_timestamps: List of beat timestamps in seconds
        bpm: Beats per minute
        total_duration: Total audio duration in seconds
        max_clips: Maximum number of clips (default: None, calculates based on duration)
                   Roughly targets ~22-25 clips for 3-minute songs at 8s per clip, but flexible
        segment_type: Type of segment (intro/verse/chorus/bridge/outro) for duration targeting
        beat_intensity: Beat intensity (low/medium/high) for duration targeting

    Returns:
        List of ClipBoundary objects
    """
    # PHASE 2.4: Get content-based target duration FIRST
    target_duration = _get_target_duration_for_segment(segment_type, beat_intensity)

    # Calculate target number of clips if not specified
    # Use content-based target duration instead of hardcoded 7s
    if max_clips is None:
        # CRITICAL: Ensure segments longer than 8s are ALWAYS subdivided
        # Final clips must be 8 seconds or less (Veo 3.1 limit)
        if total_duration > 8.0:
            # For segments > 8s, explicitly calculate number of clips needed
            # round(12.0 / 6.0) = round(2.0) = 2 clips of ~6s each
            # round(12.0 / 7.0) = round(1.714) = 2 clips of ~6s each
            target_clips = max(2, round(total_duration / target_duration))
        else:
            # For segments <= 8s, use normal calculation
            target_clips = round(total_duration / target_duration)
        # Cap at 25 clips maximum (for 3-minute videos and longer)
        # Minimum 1 clip for very short segments
        max_clips = max(1, min(25, target_clips))
        
        logger.info(
            f"Calculated max_clips={max_clips} for segment duration={total_duration:.1f}s, "
            f"target_duration={target_duration:.1f}s, target_clips={target_clips}"
        )

    # Edge case 1: Very short segments (<4s) → Should be merged by parser
    # If we get here, it means parser didn't merge properly - create single clip anyway
    if total_duration < 4.0:
        logger.warning(f"Segment too short ({total_duration:.1f}s < 4s production minimum), creating single clip anyway")
        # Use the full segment duration
        boundaries = [ClipBoundary(
            start=0.0,
            end=total_duration,
            duration=total_duration
        )]
        return boundaries
    
    # Edge case 2: No beats detected → Use tempo-based fallback
    if len(beat_timestamps) == 0:
        beat_interval = 60.0 / bpm
        boundaries = []
        current_time = 0.0
        while current_time < total_duration and len(boundaries) < max_clips:
            # Target ~7 seconds, using ~6 beats as base (approximately 7s at typical BPM)
            end_time = min(current_time + (6 * beat_interval), total_duration)
            duration = end_time - current_time
            # Ensure duration is within 5-8s range (prefer ~7s, most above 5s, cap at 8s for Veo 3.1)
            if duration < 5.0:
                end_time = min(current_time + 5.0, total_duration)
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
    # PHASE 2.4: Use content-based duration selection
    # Target duration already calculated above
    beat_interval = np.mean(np.diff(beat_timestamps)) if len(beat_timestamps) > 1 else (60.0 / bpm)
    base_beats_per_clip = max(1, math.ceil(target_duration / beat_interval))

    logger.info(
        f"Generating boundaries: segment_type={segment_type}, beat_intensity={beat_intensity}, "
        f"target_duration={target_duration:.1f}s, beat_interval={beat_interval:.3f}s, "
        f"base_beats_per_clip={base_beats_per_clip}"
    )
    
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
        # This creates natural variation in clip durations (roughly 5-8s range, prefer ~7s)
        # Reduced variation to ensure we stay closer to target and don't exceed Veo 3.1's 8s limit
        variation_pattern = [0, 1, -1, 0]  # Simpler pattern (repeats every 4 clips) to reduce over-generation
        beats_variation = variation_pattern[clip_index % len(variation_pattern)]
        beats_per_clip = max(1, base_beats_per_clip + beats_variation)
        
        end_idx = min(current_beat_idx + beats_per_clip, len(beat_timestamps) - 1)
        end = beat_timestamps[end_idx]
        duration = end - start

        # PHASE 2.4: Adjust duration to be close to target
        # Production quality range: 4-8s (Veo 3.1 limit is 8s, 4s is production minimum)
        # Allow range of target ±1.5s for flexibility
        min_duration = max(4.0, target_duration - 1.5)
        max_duration = min(8.0, target_duration + 1.5)

        # Adjust duration to be within acceptable range
        if duration < min_duration:
            # Extend to next beats to reach at least min_duration
            while end_idx < len(beat_timestamps) - 1 and duration < min_duration:
                end_idx += 1
                end = beat_timestamps[end_idx]
                duration = end - start
                if duration >= min_duration:
                    break

            # If we've run out of beats and duration is still < min_duration, extend to total_duration
            if duration < min_duration:
                # Extend to total_duration to ensure minimum duration
                end = min(start + min_duration, total_duration)
                duration = end - start
                # If extending to min_duration would exceed total_duration, we need to handle this differently
                if duration < 4.0:  # Production quality minimum
                    # This means we're near the end and can't create a 4s clip
                    # Merge with previous boundary if possible, or extend to end
                    if len(boundaries) > 0:
                        # Merge with previous boundary, but respect 25s model limit
                        MAX_DURATION = 25.0  # Model limit
                        prev_boundary = boundaries[-1]
                        merged_duration = total_duration - prev_boundary.start
                        if merged_duration > MAX_DURATION:
                            # Cap at 25s limit
                            boundaries[-1] = ClipBoundary(
                                start=prev_boundary.start,
                                end=prev_boundary.start + MAX_DURATION,
                                duration=MAX_DURATION
                            )
                        else:
                            # Create new boundary with merged end
                            boundaries[-1] = ClipBoundary(
                                start=prev_boundary.start,
                                end=total_duration,
                                duration=merged_duration
                            )
                        # Skip creating this boundary
                        break
                    else:
                        # First boundary - extend to at least 4s or total_duration
                        end = max(start + 4.0, total_duration)
                        duration = end - start
        
        # Cap duration at max_duration (based on target, not hardcoded 8s)
        if duration > max_duration:
            # Find the beat that keeps us closest to max_duration without going over
            # Backtrack to find a beat that gives us duration <= max_duration
            while end_idx > current_beat_idx and duration > max_duration:
                end_idx -= 1
                if end_idx > current_beat_idx:
                    end = beat_timestamps[end_idx]
                    duration = end - start
                else:
                    # Can't go back further, cap at max_duration
                    end = min(start + max_duration, total_duration)
                    duration = end - start
                    break
        
        # Ensure duration is at least 4.0 (production quality minimum) before creating boundary
        if duration < 4.0:
            # If we still can't reach 4s, skip this boundary or merge with previous
            if len(boundaries) > 0:
                # Merge with previous boundary, but respect 25s model limit
                prev_boundary = boundaries[-1]
                new_end = min(end, total_duration)
                new_duration = new_end - prev_boundary.start
                MAX_DURATION = 25.0  # Model limit
                # Ensure merged duration doesn't exceed 25s
                if new_duration <= MAX_DURATION:
                    # Create new boundary with merged end
                    boundaries[-1] = ClipBoundary(
                        start=prev_boundary.start,
                        end=new_end,
                        duration=new_duration
                    )
                # Skip creating this boundary
                continue
            else:
                # First boundary - must be at least 4s or use total_duration
                end = max(start + 4.0, total_duration)
                duration = end - start

        # Final validation: cap at max_duration if needed
        if duration > max_duration:
            # Cap at max_duration (based on target, not hardcoded 8s)
            end = min(start + max_duration, total_duration)
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
    
    # Ensure minimum 1 clip (for very short segments, we may have none)
    if len(boundaries) < 1:
        # Fallback: create at least 1 clip, but respect 8s Veo limit
        MAX_DURATION = 8.0  # Veo 3.1 limit
        if total_duration < 4.0:
            # Too short for production quality - should have been merged by parser
            logger.warning(f"Fallback: segment too short ({total_duration:.1f}s < 4s production minimum), creating clip anyway")
            return [ClipBoundary(
                start=0.0,
                end=total_duration,
                duration=total_duration
            )]
        else:
            # Create single clip for short segment, cap at 8s
            return [ClipBoundary(
                start=0.0,
                end=min(total_duration, MAX_DURATION),
                duration=min(total_duration, MAX_DURATION)
            )]
    
    # Trim last clip to end if needed - smart extension
    # PHASE 2.5: Smart last clip extension with multi-clip generation
    # Extend last clip to cover full duration if reasonable (≤8s), otherwise create new clip(s)
    if boundaries[-1].end < total_duration:
        new_end = total_duration
        new_duration = new_end - boundaries[-1].start
        remaining_time = total_duration - boundaries[-1].end

        # Smart extension: extend if new duration ≤ 8s (Veo 3.1 limit, reasonable for 7s target)
        if new_duration <= 8.0:
            # Extend the last boundary to cover full duration
            prev_boundary = boundaries[-1]
            boundaries[-1] = ClipBoundary(
                start=prev_boundary.start,
                end=new_end,
                duration=new_duration,
                metadata=prev_boundary.metadata
            )
            logger.info(f"Extended last boundary to cover full duration: {prev_boundary.end:.1f}s -> {new_end:.1f}s (duration: {new_duration:.1f}s)")
        # PHASE 2.5: If remaining > 8s and <= 24s, generate multiple clips instead of one extended clip
        elif 8.0 < remaining_time <= 24.0 and len(boundaries) < max_clips:
            # Calculate how many clips we can fit in the remaining time
            # Target 6s for outro clips (from _get_target_duration_for_segment)
            target_outro_duration = 6.0
            num_outro_clips = max(2, min(3, int(remaining_time / target_outro_duration)))

            # Distribute remaining time across outro clips
            outro_clip_duration = remaining_time / num_outro_clips

            # Ensure each outro clip is within 5-8s range
            if outro_clip_duration < 5.0:
                num_outro_clips = max(2, int(remaining_time / 5.0))
                outro_clip_duration = remaining_time / num_outro_clips
            elif outro_clip_duration > 8.0:
                num_outro_clips = max(2, int(math.ceil(remaining_time / 8.0)))
                outro_clip_duration = remaining_time / num_outro_clips

            # Generate multiple outro clips
            current_start = boundaries[-1].end
            for i in range(num_outro_clips):
                if i == num_outro_clips - 1:
                    # Last outro clip extends to end
                    clip_end = total_duration
                    clip_duration = clip_end - current_start
                else:
                    clip_end = min(current_start + outro_clip_duration, total_duration)
                    clip_duration = clip_end - current_start

                # Mark as outro extension clip
                boundaries.append(ClipBoundary(
                    start=current_start,
                    end=clip_end,
                    duration=clip_duration,
                    metadata={"is_outro_extension": True}
                ))
                current_start = clip_end

            logger.info(f"Created {num_outro_clips} outro extension clips for remaining {remaining_time:.1f}s")
        elif remaining_time >= 5.0 and len(boundaries) < max_clips:
            # Single additional clip for remaining time
            boundaries.append(ClipBoundary(
                start=boundaries[-1].end,
                end=total_duration,
                duration=remaining_time,
                metadata={"is_outro_extension": True}
            ))
            logger.info(f"Created additional clip for remaining {remaining_time:.1f}s (last clip would have been {new_duration:.1f}s)")
        else:
            # If we can't create a new clip (too short or max_clips reached), extend but cap at 25s
            # This ensures we cover the full audio duration while respecting model limit
            MAX_DURATION = 25.0  # Model limit: ClipBoundary.duration <= 25.0
            prev_boundary = boundaries[-1]
            capped_duration = min(new_duration, MAX_DURATION)
            capped_end = prev_boundary.start + capped_duration
            boundaries[-1] = ClipBoundary(
                start=prev_boundary.start,
                end=capped_end,
                duration=capped_duration,
                metadata=prev_boundary.metadata
            )
            if new_duration > MAX_DURATION:
                logger.warning(f"Capped last boundary at 25s model limit: {prev_boundary.end:.1f}s -> {capped_end:.1f}s (duration: {capped_duration:.1f}s, would have been {new_duration:.1f}s)")
            else:
                logger.info(f"Extended last boundary beyond 8s limit to cover full duration: {prev_boundary.end:.1f}s -> {capped_end:.1f}s (duration: {capped_duration:.1f}s)")
    
    # Final validation: ensure all boundaries have duration >= 4.0 and <= 8.0 (Veo 3.1 limit)
    # Production quality range: 4-8 seconds
    # Filter out any boundaries that don't meet the range and merge/skip as needed
    MAX_DURATION = 8.0  # Veo 3.1 limit: clips must be <= 8s

    # Calculate acceptable range based on target duration
    final_min_duration = max(4.0, target_duration - 1.5)
    final_max_duration = min(8.0, target_duration + 1.5)

    validated_boundaries = []
    for i, boundary in enumerate(boundaries):
        # All boundaries must be <= 8s (Veo 3.1 limit), but last can extend to cover remaining audio
        max_allowed = MAX_DURATION
        if final_min_duration <= boundary.duration <= max_allowed:
            validated_boundaries.append(boundary)
        elif boundary.duration < final_min_duration:
            # If duration < min, try to merge with previous or next boundary
            if len(validated_boundaries) > 0:
                # Merge with previous boundary
                prev_boundary = validated_boundaries[-1]
                new_end = min(boundary.end, total_duration)
                new_duration = new_end - prev_boundary.start
                # Ensure merged duration is still <= 25s (model limit)
                if new_duration <= MAX_DURATION:
                    # Create new boundary with merged end, preserve metadata
                    validated_boundaries[-1] = ClipBoundary(
                        start=prev_boundary.start,
                        end=new_end,
                        duration=new_duration,
                        metadata=prev_boundary.metadata
                    )
                else:
                    # Can't merge without violating 25s maximum, skip this boundary
                    continue
            elif i < len(boundaries) - 1:
                # Merge with next boundary (skip this one, extend next)
                next_boundary = boundaries[i + 1]
                new_start = boundary.start
                new_duration = next_boundary.end - new_start
                if new_duration <= MAX_DURATION:
                    # Preserve metadata from next boundary when merging
                    validated_boundaries.append(ClipBoundary(
                        start=new_start,
                        end=next_boundary.end,
                        duration=new_duration,
                        metadata=next_boundary.metadata
                    ))
            else:
                # Last boundary - extend to ensure >= min
                new_end = max(boundary.start + final_min_duration, total_duration)
                new_duration = new_end - boundary.start
                if new_duration <= MAX_DURATION:
                    # Preserve metadata from boundary when extending
                    validated_boundaries.append(ClipBoundary(
                        start=boundary.start,
                        end=new_end,
                        duration=new_duration,
                        metadata=boundary.metadata
                    ))
        elif boundary.duration > max_allowed:
            # If duration > max_allowed, cap it
            # Last boundary can extend up to 25s (model limit) to cover full audio
            if i == len(boundaries) - 1 and boundary.duration <= MAX_DURATION:
                # Last boundary can extend up to 25s (model limit) to cover full audio
                validated_boundaries.append(boundary)
            else:
                # Cap at max_allowed for non-last boundaries, or 25s if last boundary exceeds limit
                cap_duration = MAX_DURATION if i == len(boundaries) - 1 else final_max_duration
                # Preserve metadata when capping duration
                validated_boundaries.append(ClipBoundary(
                    start=boundary.start,
                    end=min(boundary.start + cap_duration, total_duration),
                    duration=min(cap_duration, total_duration - boundary.start),
                    metadata=boundary.metadata
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
            # Preserve metadata from last boundary
            last_boundary = ClipBoundary(
                start=last_boundary.start,
                end=max(last_boundary.start + final_min_duration, total_duration),
                duration=max(final_min_duration, min(final_max_duration, total_duration - last_boundary.start)),
                metadata=last_boundary.metadata
            )
            boundaries = [last_boundary]
    
    logger.info(f"Generated {len(boundaries)} beat-aligned clip boundaries")
    return boundaries[:max_clips]


def _create_equal_segments(duration: float, num_segments: int) -> List[ClipBoundary]:
    """Create equal-length segments, ensuring durations are in 5-8s range (prefer ~7s)."""
    # For very short songs, we may need to adjust
    # If total duration is less than 9s, we already handled it in the main function
    # This function is called when we need minimum 3 clips but can't fit 5-8s each
    # In that case, we'll create segments that are as close to 7s as possible (minimum 3s per model for very short songs)

    # If duration is less than 3s, we can't create any valid segments (model constraint)
    if duration < 3.0:
        logger.warning(f"_create_equal_segments: duration too short ({duration:.1f}s < 3s minimum), returning empty list")
        return []

    if duration < 9.0:
        # For songs <9s, create 3 segments with minimum 3s each where possible (model minimum)
        # But if duration < 9s, we already handled it above, so this shouldn't be called
        # However, if it is called, ensure minimum 3s per segment (model constraint)
        min_segment_duration = max(5.0, duration / num_segments)
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

            # Ensure duration is at least 5s (or as close as possible)
            if seg_duration < 5.0 and i < num_segments - 1:
                end_time = min(current_time + 5.0, duration)
                seg_duration = end_time - current_time

            # Ensure duration doesn't exceed 8s (Veo 3.1 limit)
            if seg_duration > 8.0:
                end_time = current_time + 8.0
                seg_duration = 8.0

            # Only append if duration meets minimum requirement (3s)
            if seg_duration >= 3.0:
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
    
    # Ensure segment duration is in 5-8s range (prefer ~7s)
    if segment_duration < 5.0:
        # If segments would be too short, reduce number of segments
        num_segments = max(3, int(duration / 5.0))
        segment_duration = duration / num_segments
    elif segment_duration > 8.0:
        # If segments would be too long, increase number of segments (Veo 3.1 limit)
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


def find_beat_aligned_time(
    start_time: float,
    target_duration: float,
    beat_timestamps: List[float],
    tolerance: float = 0.05
) -> float:
    """
    Find beat-aligned time closest to target duration from start.
    
    Args:
        start_time: Start time in seconds
        target_duration: Target duration in seconds
        beat_timestamps: List of beat timestamps
        tolerance: Maximum deviation from beat alignment (seconds)
        
    Returns:
        Timestamp of beat that gives duration closest to target
    """
    if not beat_timestamps:
        return start_time + target_duration
    
    target_time = start_time + target_duration
    
    # Find nearest beat to target time
    nearest_beat_idx = min(
        range(len(beat_timestamps)),
        key=lambda i: abs(beat_timestamps[i] - target_time)
    )
    
    nearest_beat = beat_timestamps[nearest_beat_idx]
    
    # Check if within tolerance
    if abs(nearest_beat - target_time) <= tolerance:
        return nearest_beat
    
    # Otherwise return target time (will be adjusted later)
    return target_time


def extend_to_minimum(
    start_time: float,
    min_duration: float,
    beat_timestamps: List[float],
    max_time: float
) -> float:
    """
    Extend from start_time to reach minimum duration.
    Aligns to nearest beat, caps at max_time.
    
    Args:
        start_time: Start time in seconds
        min_duration: Minimum duration required
        beat_timestamps: List of beat timestamps
        max_time: Maximum allowed time (segment end)
        
    Returns:
        End time that meets minimum duration
    """
    target_time = start_time + min_duration
    
    if target_time >= max_time:
        return max_time
    
    if not beat_timestamps:
        return min(target_time, max_time)
    
    # Find beats after target_time
    candidate_beats = [b for b in beat_timestamps if b >= target_time and b <= max_time]
    
    if candidate_beats:
        # Use first beat that meets minimum
        return candidate_beats[0]
    
    # No beats available, use max_time
    return max_time


def cap_at_maximum(
    start_time: float,
    max_duration: float,
    beat_timestamps: List[float]
) -> float:
    """
    Cap duration at maximum (8s for Veo 3.1).
    CRITICAL: This ensures subdivision works.
    
    Args:
        start_time: Start time in seconds
        max_duration: Maximum duration allowed (8.0s)
        beat_timestamps: List of beat timestamps
        
    Returns:
        End time capped at maximum duration
    """
    max_time = start_time + max_duration
    
    if not beat_timestamps:
        return max_time
    
    # Find beats before max_time
    candidate_beats = [b for b in beat_timestamps if b <= max_time]
    
    if candidate_beats:
        # Use last beat before max_time
        return candidate_beats[-1]
    
    # No beats available, use max_time
    return max_time


def align_breakpoint_to_beat(
    breakpoint_time: float,
    beat_timestamps: List[float],
    tolerance: float = 0.05
) -> float:
    """
    Align breakpoint to nearest beat within tolerance.
    
    Args:
        breakpoint_time: Breakpoint timestamp
        beat_timestamps: List of beat timestamps
        tolerance: Maximum deviation from beat (seconds)
        
    Returns:
        Aligned timestamp (beat-aligned if within tolerance, otherwise original)
    """
    if not beat_timestamps:
        return breakpoint_time
    
    # Find nearest beat
    nearest_beat_idx = min(
        range(len(beat_timestamps)),
        key=lambda i: abs(beat_timestamps[i] - breakpoint_time)
    )
    
    nearest_beat = beat_timestamps[nearest_beat_idx]
    
    # Align if within tolerance
    if abs(nearest_beat - breakpoint_time) <= tolerance:
        return nearest_beat
    
    return breakpoint_time


def generate_boundaries_with_breakpoints(
    beat_timestamps: List[float],
    bpm: float,
    total_duration: float,
    breakpoints: List[Breakpoint],
    max_clips: int = None,
    segment_type: str = "verse",
    beat_intensity: str = "medium"
) -> List[ClipBoundary]:
    """
    Generate clip boundaries using breakpoint-aware algorithm.
    
    Prioritizes logical breakpoints (lyrics, energy, silence, harmonic) over
    rigid target durations, while ensuring all clips are 4-8s.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds (relative to segment start)
        bpm: Beats per minute
        total_duration: Total segment duration in seconds
        breakpoints: List of detected breakpoints (relative to segment start)
        max_clips: Maximum number of clips (default: None, calculates based on duration)
        segment_type: Type of segment (intro/verse/chorus/bridge/outro)
        beat_intensity: Beat intensity (low/medium/high)
        
    Returns:
        List of ClipBoundary objects, all within 4-8s range
    """
    # Hard constraints for clip durations
    # MIN_DURATION lowered to 3.0s to allow smaller clips rather than leaving gaps
    # Better to have a 3-4s clip than to leave audio uncovered
    MIN_DURATION = 3.0
    MAX_DURATION = 8.0
    
    # Get target duration (used as fallback when no breakpoints available)
    target_duration = _get_target_duration_for_segment(segment_type, beat_intensity)
    
    # CRITICAL: Ensure subdivision works for segments >=8s
    # Calculate minimum clips required based on MAX_DURATION constraint (8s)
    min_clips_required = math.ceil(total_duration / MAX_DURATION)
    
    # Calculate max_clips if not specified
    if max_clips is None:
        target_clips = round(total_duration / target_duration)
        max_clips = max(min_clips_required, min(25, target_clips))
    else:
        # Ensure max_clips is at least the minimum required for subdivision
        max_clips = max(max_clips, min_clips_required)
    
    if total_duration >= 8.0:
        logger.info(
            f"Segment {total_duration:.1f}s >= 8s, forcing subdivision: "
            f"min_clips={min_clips_required}, max_clips={max_clips}"
        )
    
    # Edge case: Very short segments (<3s)
    if total_duration < MIN_DURATION:
        logger.warning(
            f"Segment too short ({total_duration:.1f}s < {MIN_DURATION}s minimum), "
            f"creating single clip anyway"
        )
        return [ClipBoundary(
            start=0.0,
            end=total_duration,
            duration=total_duration
        )]
    
    # Align breakpoints to beats (within tolerance)
    aligned_breakpoints = []
    for bp in breakpoints:
        aligned_time = align_breakpoint_to_beat(bp.timestamp, beat_timestamps, tolerance=0.05)
        aligned_breakpoints.append(Breakpoint(
            timestamp=aligned_time,
            confidence=bp.confidence,
            source=bp.source,
            type=bp.type,
            metadata=bp.metadata
        ))
    
    # Sort breakpoints by timestamp
    aligned_breakpoints.sort(key=lambda bp: bp.timestamp)
    
    # Filter breakpoints to valid range (not too close to boundaries)
    valid_breakpoints = [
        bp for bp in aligned_breakpoints
        if 1.0 <= bp.timestamp <= (total_duration - 1.0)
    ]
    
    boundaries = []
    current_time = 0.0
    clip_index = 0
    
    while current_time < total_duration and len(boundaries) < max_clips:
        # Calculate remaining time in segment
        remaining_time = total_duration - current_time
        
        # If less than 3s remaining, exit main loop and let continuation loop handle it
        # With MIN_DURATION=3.0s, we can create clips down to 3s in the main loop
        # Only exit if remaining time is truly too small (< 3s)
        if remaining_time < MIN_DURATION:
            break
        
        # Find next breakpoint within acceptable range (4-8s from current_time)
        candidate_breakpoints = [
            bp for bp in valid_breakpoints
            if (current_time + MIN_DURATION) <= bp.timestamp <= min(current_time + MAX_DURATION, total_duration)
        ]
        
        if candidate_breakpoints:
            # Use highest-confidence breakpoint
            best_breakpoint = max(candidate_breakpoints, key=lambda bp: bp.confidence)
            end_time = best_breakpoint.timestamp
            
            logger.debug(
                f"Clip {clip_index}: Using breakpoint at {end_time:.2f}s "
                f"(source={best_breakpoint.source}, confidence={best_breakpoint.confidence:.2f})"
            )
        else:
            # No breakpoint in range - use beat-aligned target duration
            end_time = find_beat_aligned_time(current_time, target_duration, beat_timestamps)
            
            # Ensure end_time is valid and within segment
            if end_time <= current_time:
                # Invalid - calculate based on remaining time
                if remaining_time <= MAX_DURATION:
                    end_time = total_duration
                else:
                    end_time = current_time + MAX_DURATION
            elif end_time > total_duration:
                # Would exceed segment - use remaining time
                if remaining_time <= MAX_DURATION:
                    end_time = total_duration
                else:
                    end_time = current_time + MAX_DURATION
        
        # Validate duration (4-8s)
        duration = end_time - current_time
        
        if duration < MIN_DURATION:
            # Extend to minimum
            end_time = extend_to_minimum(current_time, MIN_DURATION, beat_timestamps, total_duration)
            duration = end_time - current_time
        elif duration > MAX_DURATION:
            # Cap at maximum (CRITICAL for subdivision)
            end_time = cap_at_maximum(current_time, MAX_DURATION, beat_timestamps)
            duration = end_time - current_time
            logger.debug(
                f"Clip {clip_index}: Capped duration at {MAX_DURATION}s "
                f"(would have been {end_time - current_time:.2f}s)"
            )
        
        # Final validation
        if duration < MIN_DURATION:
            # Still too short - extend to total_duration if near end
            if total_duration - current_time < MIN_DURATION * 1.5:
                # Near end, extend last clip
                end_time = total_duration
                duration = end_time - current_time
            else:
                # Not near end, skip this boundary or merge
                logger.warning(
                    f"Clip {clip_index}: Duration {duration:.2f}s < {MIN_DURATION}s, "
                    f"extending to minimum"
                )
                end_time = extend_to_minimum(current_time, MIN_DURATION, beat_timestamps, total_duration)
                duration = end_time - current_time
        
        # Create boundary
        boundaries.append(ClipBoundary(
            start=current_time,
            end=end_time,
            duration=duration,
            metadata={
                "segment_type": segment_type,
                "beat_intensity": beat_intensity,
                "clip_index": clip_index
            }
        ))
        
        current_time = end_time
        clip_index += 1
        
        # Check if we've reached the end
        if current_time >= total_duration:
            break
    
    # CRITICAL: Ensure continuous coverage - NO GAPS ALLOWED
    # If loop exited early, continue generating clips until segment is fully covered
    # ALWAYS cover full segment, even if it means exceeding max_clips or creating very short clips
    while current_time < total_duration:
        # Calculate remaining time
        remaining_time = total_duration - current_time
        
        # If remaining time fits in one clip (4-8s), create it and we're done
        if MIN_DURATION <= remaining_time <= MAX_DURATION:
            boundaries.append(ClipBoundary(
                start=current_time,
                end=total_duration,
                duration=remaining_time,
                metadata={
                    "segment_type": segment_type,
                    "beat_intensity": beat_intensity,
                    "clip_index": len(boundaries),
                    "is_continuation": True
                }
            ))
            current_time = total_duration
            break
        
        # If remaining time > 8s, create an 8s clip and continue
        elif remaining_time > MAX_DURATION:
            # Find beat-aligned end time for 8s clip
            target_end = current_time + MAX_DURATION
            if beat_timestamps:
                # Find nearest beat to target_end
                candidate_beats = [b for b in beat_timestamps if current_time < b <= target_end]
                if candidate_beats:
                    end_time = candidate_beats[-1]  # Use last beat before target
                else:
                    end_time = target_end
            else:
                end_time = target_end
            
            # Ensure we don't exceed segment
            end_time = min(end_time, total_duration)
            duration = end_time - current_time
            
            # Validate duration
            if duration < MIN_DURATION:
                end_time = extend_to_minimum(current_time, MIN_DURATION, beat_timestamps, total_duration)
                duration = end_time - current_time
            
            boundaries.append(ClipBoundary(
                start=current_time,
                end=end_time,
                duration=duration,
                metadata={
                    "segment_type": segment_type,
                    "beat_intensity": beat_intensity,
                    "clip_index": len(boundaries),
                    "is_continuation": True
                }
            ))
            current_time = end_time
        
        # If remaining time < 3s, we MUST cover it - NO GAPS ALLOWED
        # Strategy: Try to extend last clip first, otherwise create small clip
        else:  # remaining_time < MIN_DURATION
            if boundaries:
                last_boundary = boundaries[-1]
                extended_duration = total_duration - last_boundary.start
                if extended_duration <= MAX_DURATION:
                    # Extend last clip to cover remainder - this is preferred
                    boundaries[-1] = ClipBoundary(
                        start=last_boundary.start,
                        end=total_duration,
                        duration=extended_duration,
                        metadata=last_boundary.metadata
                    )
                    logger.debug(f"Extended last clip to cover remaining {remaining_time:.2f}s")
                else:
                    # Can't extend without exceeding 8s - create small clip anyway
                    # CRITICAL: Better to have a small clip (even < 1s) than a gap!
                    # Blank space between clips is NOT acceptable
                    boundaries.append(ClipBoundary(
                        start=current_time,
                        end=total_duration,
                        duration=remaining_time,
                        metadata={
                            "segment_type": segment_type,
                            "beat_intensity": beat_intensity,
                            "clip_index": len(boundaries),
                            "is_continuation": True,
                            "warning": "clip_duration_below_minimum",
                            "note": "Created to prevent gap - better than blank space"
                        }
                    ))
                    logger.warning(
                        f"Created clip with duration {remaining_time:.2f}s < {MIN_DURATION}s "
                        f"to avoid gap (NO GAPS ALLOWED - blank space between clips is NOT acceptable)"
                    )
            else:
                # No boundaries yet - create one for remaining time (even if very short)
                boundaries.append(ClipBoundary(
                    start=current_time,
                    end=total_duration,
                    duration=remaining_time,
                    metadata={
                        "segment_type": segment_type,
                        "beat_intensity": beat_intensity,
                        "clip_index": 0,
                        "warning": "clip_duration_below_minimum" if remaining_time < MIN_DURATION else None
                    }
                ))
            current_time = total_duration
            break
    
    # CRITICAL FINAL CHECK: Ensure NO gaps WITHIN this segment - clips must be contiguous
    # This only checks gaps within the segment (not between segments, which are structure boundaries).
    for i in range(len(boundaries) - 1):
        gap = boundaries[i + 1].start - boundaries[i].end
        if gap > 0.01:  # More than 10ms gap (allowing for floating point precision)
            logger.error(
                f"CRITICAL: Gap detected within segment between clip {i} and {i+1}: {gap:.3f}s "
                f"({boundaries[i].end:.3f}s - {boundaries[i+1].start:.3f}s). "
                f"NO GAPS ALLOWED - fixing by making clip {i+1} start exactly at clip {i} end."
            )
            # Fix: Make next clip start exactly where previous ends (NO GAP)
            # This ensures continuous coverage within the segment
            new_start = boundaries[i].end
            new_duration = boundaries[i + 1].end - new_start
            
            # If adjusting start makes duration too short, extend the end (up to segment end)
            if new_duration < MIN_DURATION:
                # Try to extend end to reach minimum, but cap at total_duration (segment end)
                new_end = min(new_start + MIN_DURATION, total_duration)
                new_duration = new_end - new_start
            else:
                new_end = boundaries[i + 1].end
            
            boundaries[i + 1] = ClipBoundary(
                start=new_start,
                end=new_end,
                duration=new_duration,
                metadata=boundaries[i + 1].metadata
            )
    
    # CRITICAL: Ensure last boundary covers to the end - NO GAPS ALLOWED
    # This is a final safety check to catch any remaining uncovered time
    if boundaries and boundaries[-1].end < total_duration:
        remaining = total_duration - boundaries[-1].end
        
        # ALWAYS cover remaining time, no matter how small - blank space is NOT acceptable
        last_boundary = boundaries[-1]
        new_duration = total_duration - last_boundary.start
        
        if new_duration <= MAX_DURATION:
            # Extend last boundary to cover remainder
            boundaries[-1] = ClipBoundary(
                start=last_boundary.start,
                end=total_duration,
                duration=new_duration,
                metadata=last_boundary.metadata
            )
            logger.debug(f"Extended last boundary to cover remaining {remaining:.2f}s")
        else:
            # Can't extend without exceeding 8s - create small clip anyway
            # CRITICAL: Better to have a tiny clip than a gap!
            boundaries.append(ClipBoundary(
                start=last_boundary.end,
                end=total_duration,
                duration=remaining,
                metadata={
                    "segment_type": segment_type,
                    "beat_intensity": beat_intensity,
                    "clip_index": len(boundaries),
                    "is_remainder": True,
                    "warning": "clip_duration_below_minimum" if remaining < MIN_DURATION else None,
                    "note": "Created to prevent gap - better than blank space"
                }
            ))
            logger.warning(
                f"Created final clip with duration {remaining:.2f}s "
                f"{'(< MIN_DURATION)' if remaining < MIN_DURATION else ''} "
                f"to avoid gap (NO GAPS ALLOWED)"
            )
        elif remaining >= MIN_DURATION:
            # Create additional clip for remaining time
            boundaries.append(ClipBoundary(
                start=boundaries[-1].end,
                end=total_duration,
                duration=remaining,
                metadata={
                    "segment_type": segment_type,
                    "beat_intensity": beat_intensity,
                    "clip_index": len(boundaries),
                    "is_remainder": True
                }
            ))
    
    # Final validation: ensure all boundaries are 4-8s
    validated_boundaries = []
    for i, boundary in enumerate(boundaries):
        if boundary.duration < MIN_DURATION:
            logger.warning(
                f"Boundary {i}: duration {boundary.duration:.2f}s < {MIN_DURATION}s, "
                f"merging with previous or next"
            )
            # Try to merge with previous
            if validated_boundaries:
                prev = validated_boundaries[-1]
                merged_duration = boundary.end - prev.start
                if merged_duration <= MAX_DURATION:
                    validated_boundaries[-1] = ClipBoundary(
                        start=prev.start,
                        end=boundary.end,
                        duration=merged_duration,
                        metadata=prev.metadata
                    )
                    continue
            # Can't merge, skip this boundary
            continue
        elif boundary.duration > MAX_DURATION:
            logger.warning(
                f"Boundary {i}: duration {boundary.duration:.2f}s > {MAX_DURATION}s, "
                f"capping at maximum"
            )
            # Cap at maximum
            validated_boundaries.append(ClipBoundary(
                start=boundary.start,
                end=boundary.start + MAX_DURATION,
                duration=MAX_DURATION,
                metadata=boundary.metadata
            ))
        else:
            validated_boundaries.append(boundary)
    
    # Ensure we have at least one boundary
    if not validated_boundaries:
        logger.warning("No valid boundaries generated, creating fallback single clip")
        return [ClipBoundary(
            start=0.0,
            end=min(total_duration, MAX_DURATION),
            duration=min(total_duration, MAX_DURATION)
        )]
    
    logger.info(
        f"Generated {len(validated_boundaries)} breakpoint-aware clip boundaries "
        f"(used {len(valid_breakpoints)} breakpoints, "
        f"durations: {[f'{b.duration:.1f}s' for b in validated_boundaries]})"
    )
    
    return validated_boundaries[:max_clips]


def validate_boundaries(
    boundaries: List[ClipBoundary],
    total_duration: float,
    min_duration: float = 3.0,
    max_duration: float = 8.0
) -> Tuple[bool, List[str]]:
    """
    Validate all boundaries meet requirements.
    
    Args:
        boundaries: List of clip boundaries to validate
        total_duration: Total audio duration in seconds
        min_duration: Minimum allowed duration (default: 4.0s)
        max_duration: Maximum allowed duration (default: 8.0s)
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not boundaries:
        errors.append("No boundaries provided")
        return False, errors
    
    # Check duration range
    for i, boundary in enumerate(boundaries):
        if boundary.duration < min_duration:
            errors.append(
                f"Boundary {i} [{boundary.start:.2f}s - {boundary.end:.2f}s]: "
                f"duration {boundary.duration:.2f}s < {min_duration}s"
            )
        if boundary.duration > max_duration:
            errors.append(
                f"Boundary {i} [{boundary.start:.2f}s - {boundary.end:.2f}s]: "
                f"duration {boundary.duration:.2f}s > {max_duration}s"
            )
    
    # Check coverage
    if boundaries[0].start > 0.1:  # 100ms tolerance
        errors.append(
            f"First boundary doesn't start at 0.0s (starts at {boundaries[0].start:.2f}s)"
        )
    
    if boundaries[-1].end < total_duration - 0.1:  # 100ms tolerance
        errors.append(
            f"Last boundary doesn't cover full duration "
            f"(ends at {boundaries[-1].end:.2f}s, total duration is {total_duration:.2f}s)"
        )
    
    # Check no gaps
    for i in range(len(boundaries) - 1):
        gap = boundaries[i+1].start - boundaries[i].end
        if gap > 0.1:  # 100ms tolerance
            errors.append(
                f"Gap between boundary {i} and {i+1}: {gap:.2f}s "
                f"({boundaries[i].end:.2f}s -> {boundaries[i+1].start:.2f}s)"
            )
    
    # Check no overlaps (shouldn't happen, but validate)
    for i in range(len(boundaries) - 1):
        if boundaries[i].end > boundaries[i+1].start + 0.1:  # 100ms tolerance
            overlap = boundaries[i].end - boundaries[i+1].start
            errors.append(
                f"Overlap between boundary {i} and {i+1}: {overlap:.2f}s"
            )
    
    is_valid = len(errors) == 0
    return is_valid, errors
