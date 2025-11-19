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
