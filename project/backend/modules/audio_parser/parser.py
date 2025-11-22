"""
Core audio parser orchestration.

Coordinates all audio analysis components.
"""

import librosa
import io
import math
from uuid import UUID
from typing import List, Tuple
from shared.models.audio import AudioAnalysis, ClipBoundary, SongStructure
from shared.logging import get_logger

from modules.audio_parser.beat_detection import detect_beats, detect_beat_subdivisions, classify_beat_strength
from modules.audio_parser.structure_analysis import analyze_structure, analyze_segment_appropriateness
from modules.audio_parser.mood_classifier import classify_mood
from modules.audio_parser.boundaries import (
    generate_boundaries,
    generate_boundaries_with_breakpoints,
    validate_boundaries
)
from modules.audio_parser.lyrics_extraction import extract_lyrics
from modules.audio_parser.breakpoint_detection import (
    detect_lyrics_breakpoints,
    detect_energy_breakpoints,
    detect_silence_breakpoints,
    detect_harmonic_breakpoints,
    aggregate_breakpoints
)

logger = get_logger("audio_parser")


def ensure_full_coverage(
    clip_boundaries: List[ClipBoundary],
    total_duration: float,
    tolerance: float = 0.1
) -> Tuple[List[ClipBoundary], List[str]]:
    """
    Ensure clip boundaries cover the full audio duration.
    
    Fixes:
    - Gaps between boundaries
    - Last boundary not reaching total_duration
    - Overlaps between boundaries
    
    Args:
        clip_boundaries: List of clip boundaries (may have gaps/overlaps)
        total_duration: Total audio duration in seconds
        tolerance: Tolerance for floating point precision (default: 0.1s)
        
    Returns:
        Tuple of (fixed_boundaries, fixes_applied)
    """
    if not clip_boundaries:
        return [], ["No boundaries to process"]
    
    fixes_applied = []
    fixed_boundaries = []
    
    # Sort boundaries by start time (should already be sorted, but ensure)
    sorted_boundaries = sorted(clip_boundaries, key=lambda b: b.start)
    
    # Fix 1: Ensure first boundary starts at 0.0
    if sorted_boundaries[0].start > tolerance:
        gap = sorted_boundaries[0].start
        fixes_applied.append(f"Fixed gap at start: {gap:.2f}s")
        # Extend first boundary to start at 0.0
        first = sorted_boundaries[0]
        fixed_boundaries.append(ClipBoundary(
            start=0.0,
            end=first.end,
            duration=first.end,
            metadata={**(first.metadata or {}), "fix": "extended_to_start"}
        ))
        sorted_boundaries = sorted_boundaries[1:]
    else:
        fixed_boundaries.append(sorted_boundaries[0])
        sorted_boundaries = sorted_boundaries[1:]
    
    # Fix 2: Process remaining boundaries, fixing gaps and overlaps
    for i, boundary in enumerate(sorted_boundaries):
        prev_boundary = fixed_boundaries[-1]
        
        # Check for gap
        gap = boundary.start - prev_boundary.end
        if gap > tolerance:
            fixes_applied.append(
                f"Fixed gap between boundaries: {gap:.2f}s "
                f"({prev_boundary.end:.2f}s -> {boundary.start:.2f}s)"
            )
            # Minimum duration for ClipBoundary is 3 seconds (model validation constraint)
            MIN_CLIP_DURATION = 3.0
            
            if gap < MIN_CLIP_DURATION:
                # Gap is too small (< 3s) to create a separate boundary - must extend previous
                # Even if it exceeds 8.5s, we must merge to avoid validation error
                new_end = boundary.start
                new_duration = new_end - prev_boundary.start
                fixed_boundaries[-1] = ClipBoundary(
                    start=prev_boundary.start,
                    end=new_end,
                    duration=new_duration,
                    metadata={**(prev_boundary.metadata or {}), "fix": "extended_to_fill_small_gap"}
                )
            elif gap < 4.0:
                # Gap is 3-4s: try to extend previous boundary if it won't exceed limits too much
                new_end = boundary.start
                new_duration = new_end - prev_boundary.start
                if new_duration <= 8.5:  # Allow slight over 8s to fix gap
                    fixed_boundaries[-1] = ClipBoundary(
                        start=prev_boundary.start,
                        end=new_end,
                        duration=new_duration,
                        metadata={**(prev_boundary.metadata or {}), "fix": "extended_to_fill_gap"}
                    )
                else:
                    # Gap is large enough (>= 3s) but extending would exceed limits - create new boundary
                    fixed_boundaries.append(ClipBoundary(
                        start=prev_boundary.end,
                        end=boundary.start,
                        duration=gap,
                        metadata={"fix": "created_to_fill_gap"}
                    ))
            else:
                # Large gap (>= 4s): create new boundary
                fixed_boundaries.append(ClipBoundary(
                    start=prev_boundary.end,
                    end=boundary.start,
                    duration=gap,
                    metadata={"fix": "created_to_fill_gap"}
                ))
        
        # Check for overlap
        overlap = prev_boundary.end - boundary.start
        if overlap > tolerance:
            fixes_applied.append(
                f"Fixed overlap between boundaries: {overlap:.2f}s"
            )
            # Adjust current boundary to start where previous ends
            new_start = prev_boundary.end
            new_duration = boundary.end - new_start
            # Minimum duration for ClipBoundary is 3 seconds (model validation constraint)
            # Production quality prefers >= 4.0s, so we use 4.0 as threshold here
            if new_duration >= 4.0:  # Only keep if still valid (>= 4s for production quality)
                fixed_boundaries.append(ClipBoundary(
                    start=new_start,
                    end=boundary.end,
                    duration=new_duration,
                    metadata={**(boundary.metadata or {}), "fix": "adjusted_for_overlap"}
                ))
            # Otherwise skip this boundary (it's been merged - duration would be < 4s)
        else:
            # No gap or overlap, add boundary as-is
            fixed_boundaries.append(boundary)
    
    # Fix 3: Ensure last boundary reaches total_duration
    if fixed_boundaries:
        last_boundary = fixed_boundaries[-1]
        remaining = total_duration - last_boundary.end
        
        if remaining > tolerance:
            fixes_applied.append(
                f"Fixed incomplete coverage: {remaining:.2f}s remaining "
                f"(last boundary ends at {last_boundary.end:.2f}s, "
                f"total duration is {total_duration:.2f}s)"
            )
            
            # Minimum duration for ClipBoundary is 3 seconds (model validation constraint)
            MIN_CLIP_DURATION = 3.0
            
            if remaining < MIN_CLIP_DURATION:
                # Very small remainder (< 3s): must extend last boundary to avoid validation error
                new_end = total_duration
                new_duration = new_end - last_boundary.start
                fixed_boundaries[-1] = ClipBoundary(
                    start=last_boundary.start,
                    end=new_end,
                    duration=new_duration,
                    metadata={**(last_boundary.metadata or {}), "fix": "extended_to_end"}
                )
            elif remaining < 4.0:
                # Small remainder (3-4s): extend last boundary (production quality prefers >4s)
                new_end = total_duration
                new_duration = new_end - last_boundary.start
                fixed_boundaries[-1] = ClipBoundary(
                    start=last_boundary.start,
                    end=new_end,
                    duration=new_duration,
                    metadata={**(last_boundary.metadata or {}), "fix": "extended_to_end"}
                )
            else:
                # Large remainder (>= 4s): create additional boundary
                fixed_boundaries.append(ClipBoundary(
                    start=last_boundary.end,
                    end=total_duration,
                    duration=remaining,
                    metadata={"fix": "created_to_cover_remainder"}
                ))
    
    return fixed_boundaries, fixes_applied


async def parse_audio(audio_bytes: bytes, job_id: UUID) -> AudioAnalysis:
    """
    Parse audio file and extract all analysis data.
    
    Args:
        audio_bytes: Audio file bytes
        job_id: Job ID for tracking
        
    Returns:
        AudioAnalysis object with all analysis results
    """
    fallbacks_used = []
    
    try:
        # Load audio
        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
        duration = len(audio) / sr
        
        logger.info(f"Loaded audio: duration={duration:.2f}s, sample_rate={sr}Hz, samples={len(audio)}")
        
        # 1. Beat Detection
        bpm, beat_timestamps, beat_confidence = detect_beats(audio, sr)
        if beat_confidence < 0.6:
            fallbacks_used.append("beat_detection")
        logger.info(f"Beat detection: BPM={bpm:.1f}, beats={len(beat_timestamps)}, confidence={beat_confidence:.2f}")
        
        # 1a. Beat Subdivisions (eighth and sixteenth notes)
        subdivisions = detect_beat_subdivisions(beat_timestamps, bpm, duration)
        logger.info(f"Beat subdivisions: {len(subdivisions['eighth_notes'])} eighth, {len(subdivisions['sixteenth_notes'])} sixteenth notes")
        
        # 1b. Beat Strength Classification (downbeat/upbeat)
        beat_strength = classify_beat_strength(beat_timestamps, audio, sr, bpm)
        downbeat_count = sum(1 for s in beat_strength if s == "downbeat")
        logger.info(f"Beat strength: {downbeat_count} downbeats, {len(beat_strength) - downbeat_count} upbeats")

        # 2. Structure Analysis (FIRST - to determine segment types and intensities)
        structure_result = analyze_structure(audio, sr, beat_timestamps, duration)
        if isinstance(structure_result, tuple):
            song_structure, structure_fallback = structure_result
        else:
            # Handle case where it returns just the list (backward compatibility)
            song_structure = structure_result
            structure_fallback = False

        if structure_fallback:
            fallbacks_used.append("structure_analysis")
        logger.info(f"Structure analysis: {len(song_structure)} segments detected")

        # 3. Clip Boundaries (generate AFTER structure, using segment-specific parameters)
        # Generate boundaries for each structure segment with content-based durations

        # PHASE 2.4: Preprocess segments to merge very short ones (<4s) with adjacent segments
        # This ensures we don't lose audio and don't create clips < 4s (production quality minimum)
        MIN_SEGMENT_DURATION = 4.0  # Production quality minimum
        merged_segments = []
        i = 0
        while i < len(song_structure):
            segment = song_structure[i]
            segment_duration = segment.end - segment.start

            # If segment is too short, try to merge with next or previous
            if segment_duration < MIN_SEGMENT_DURATION:
                if i < len(song_structure) - 1:
                    # Merge with next segment (prefer forward merge)
                    next_segment = song_structure[i + 1]
                    # Create merged segment using current segment's type (first segment dominates)
                    merged = SongStructure(
                        type=segment.type,
                        start=segment.start,
                        end=next_segment.end,
                        energy=segment.energy,
                        beat_intensity=segment.beat_intensity or next_segment.beat_intensity
                    )
                    merged_segments.append(merged)
                    logger.info(f"Merged short segment {segment.type}({segment_duration:.1f}s) with next segment, new duration: {merged.end - merged.start:.1f}s")
                    i += 2  # Skip next segment since we merged it
                elif len(merged_segments) > 0:
                    # Merge with previous segment (last segment, merge backward)
                    prev_segment = merged_segments[-1]
                    # Update previous segment to extend to current segment's end
                    merged = SongStructure(
                        type=prev_segment.type,
                        start=prev_segment.start,
                        end=segment.end,
                        energy=prev_segment.energy,
                        beat_intensity=prev_segment.beat_intensity or segment.beat_intensity
                    )
                    merged_segments[-1] = merged
                    logger.info(f"Merged short segment {segment.type}({segment_duration:.1f}s) with previous segment, new duration: {merged.end - merged.start:.1f}s")
                    i += 1
                else:
                    # Only one segment and it's short - keep it anyway
                    merged_segments.append(segment)
                    logger.warning(f"Single short segment {segment.type}({segment_duration:.1f}s), keeping as-is")
                    i += 1
            else:
                # Segment is long enough, keep as-is
                merged_segments.append(segment)
                i += 1

        logger.info(f"Segment preprocessing: {len(song_structure)} original segments → {len(merged_segments)} merged segments")

        # 4. Lyrics Extraction (needed for breakpoint detection)
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        if len(lyrics) == 0:
            # Check if this was a fallback (instrumental) or actual failure
            # For now, empty lyrics is valid (instrumental tracks)
            pass
        
        # Calculate average lyrics confidence
        lyrics_confidence = 0.0
        if lyrics:
            lyrics_confidence = sum(
                lyric.confidence or 0.5 for lyric in lyrics
            ) / len(lyrics)
        
        logger.info(
            f"Lyrics extraction: {len(lyrics)} words, "
            f"avg confidence={lyrics_confidence:.2f}"
        )
        
        # 3a. Analyze long segments for appropriateness
        LONG_SEGMENT_THRESHOLD = 20.0  # Segments >20s should be analyzed
        segment_analyses = {}  # Key: (start, end) tuple, Value: analysis dict
        
        for segment in merged_segments:
            segment_duration = segment.end - segment.start
            if segment_duration > LONG_SEGMENT_THRESHOLD:
                analysis = analyze_segment_appropriateness(
                    segment, audio, sr, beat_timestamps, lyrics, duration
                )
                # Use (start, end) tuple as key since SongStructure is not hashable
                segment_key = (segment.start, segment.end)
                segment_analyses[segment_key] = analysis
                
                if not analysis["is_appropriate"]:
                    logger.warning(
                        f"Long segment [{segment.start:.1f}s - {segment.end:.1f}s] "
                        f"({segment_duration:.1f}s) may be inappropriate: "
                        f"confidence={analysis['confidence']:.2f}, "
                        f"reasons={analysis['reasons'][:2]}"
                    )
                    
                    # If very inappropriate and very long, consider forcing subdivision
                    if analysis["recommendation"] == "force_subdivision":
                        logger.warning(
                            f"⚠️ FORCING SUBDIVISION for segment [{segment.start:.1f}s - {segment.end:.1f}s] "
                            f"due to low appropriateness (confidence={analysis['confidence']:.2f})"
                        )
                else:
                    logger.info(
                        f"Long segment [{segment.start:.1f}s - {segment.end:.1f}s] "
                        f"({segment_duration:.1f}s) is appropriate: "
                        f"confidence={analysis['confidence']:.2f}"
                    )
        
        # 5. Breakpoint Detection and Boundary Generation
        # Detect breakpoints for each merged structure segment
        clip_boundaries = []
        breakpoint_stats = {
            "total_detected": 0,
            "lyrics": 0,
            "energy": 0,
            "silence": 0,
            "harmonic": 0
        }
        
        for segment in merged_segments:
            # Extract beats within this segment and make them relative to segment start
            segment_beats_absolute = [b for b in beat_timestamps if segment.start <= b <= segment.end]
            segment_beats = [b - segment.start for b in segment_beats_absolute]  # Make relative
            segment_duration = segment.end - segment.start
            
            # Detect breakpoints for this segment
            segment_breakpoints = []
            
            # Lyrics breakpoints
            if lyrics:
                lyrics_bps = detect_lyrics_breakpoints(lyrics, segment.start, segment.end)
                segment_breakpoints.extend(lyrics_bps)
                breakpoint_stats["lyrics"] += len(lyrics_bps)
            
            # Energy breakpoints
            energy_bps = detect_energy_breakpoints(audio, sr, segment.start, segment.end)
            segment_breakpoints.extend(energy_bps)
            breakpoint_stats["energy"] += len(energy_bps)
            
            # Silence breakpoints
            silence_bps = detect_silence_breakpoints(audio, sr, segment.start, segment.end)
            segment_breakpoints.extend(silence_bps)
            breakpoint_stats["silence"] += len(silence_bps)
            
            # Harmonic breakpoints
            harmonic_bps = detect_harmonic_breakpoints(
                audio, sr, segment.start, segment.end, song_structure
            )
            segment_breakpoints.extend(harmonic_bps)
            breakpoint_stats["harmonic"] += len(harmonic_bps)
            
            # Aggregate breakpoints (merge nearby ones, weight by confidence)
            aggregated_breakpoints = aggregate_breakpoints(
                segment_breakpoints, segment.start, segment.end
            )
            breakpoint_stats["total_detected"] += len(aggregated_breakpoints)
            
            # Convert breakpoints to segment-relative coordinates
            from shared.models.audio import Breakpoint
            relative_breakpoints = [
                Breakpoint(
                    timestamp=bp.timestamp - segment.start,
                    confidence=bp.confidence,
                    source=bp.source,
                    type=bp.type,
                    metadata=bp.metadata
                )
                for bp in aggregated_breakpoints
            ]
            
            # Generate boundaries with breakpoints (or fallback to beat-aligned if no breakpoints)
            # If segment is inappropriate, force more aggressive subdivision
            segment_key = (segment.start, segment.end)
            segment_analysis = segment_analyses.get(segment_key)
            max_clips_override = None
            
            if segment_analysis and segment_analysis["recommendation"] == "force_subdivision":
                # Force subdivision by ensuring max_clips is high enough
                min_clips_needed = math.ceil(segment_duration / 8.0)  # At least 8s per clip
                max_clips_override = max(min_clips_needed, 10)  # Force at least 10 clips for long segments
                logger.info(
                    f"Forcing subdivision: segment {segment_duration:.1f}s "
                    f"will generate at least {min_clips_needed} clips"
                )
            
            if relative_breakpoints:
                segment_boundaries = generate_boundaries_with_breakpoints(
                    beat_timestamps=segment_beats,
                    bpm=bpm,
                    total_duration=segment_duration,
                    breakpoints=relative_breakpoints,
                    max_clips=max_clips_override,  # Use override if forcing subdivision
                    segment_type=segment.type.value if hasattr(segment.type, 'value') else segment.type,
                    beat_intensity=segment.beat_intensity or "medium"
                )
            else:
                # Fallback to beat-aligned generation if no breakpoints detected
                logger.debug(
                    f"No breakpoints detected for segment [{segment.start:.1f}s - {segment.end:.1f}s], "
                    f"using beat-aligned generation"
                )
                segment_boundaries = generate_boundaries(
                    beat_timestamps=segment_beats,
                    bpm=bpm,
                    total_duration=segment_duration,
                    max_clips=max_clips_override,  # Use override if forcing subdivision
                    segment_type=segment.type.value if hasattr(segment.type, 'value') else segment.type,
                    beat_intensity=segment.beat_intensity or "medium"
                )
            
            # Offset boundaries to match segment start time and add to list
            for boundary in segment_boundaries:
                # Create new ClipBoundary with offset times (Pydantic models are immutable)
                offset_boundary = ClipBoundary(
                    start=boundary.start + segment.start,
                    end=boundary.end + segment.start,
                    duration=boundary.duration,  # Duration stays the same
                    metadata={
                        **boundary.metadata,
                        "segment_type": segment.type.value if hasattr(segment.type, 'value') else segment.type,
                        "breakpoints_used": len([bp for bp in relative_breakpoints 
                                               if boundary.start <= bp.timestamp <= boundary.end])
                    }
                )
                clip_boundaries.append(offset_boundary)
        
        logger.info(
            f"Clip boundaries: {len(clip_boundaries)} clips generated from {len(merged_segments)} structure segments. "
            f"Breakpoints detected: {breakpoint_stats['total_detected']} total "
            f"(lyrics={breakpoint_stats['lyrics']}, energy={breakpoint_stats['energy']}, "
            f"silence={breakpoint_stats['silence']}, harmonic={breakpoint_stats['harmonic']})"
        )
        
        # 5a. Post-processing: Ensure full coverage
        clip_boundaries, coverage_fixes = ensure_full_coverage(clip_boundaries, duration)
        coverage_fixes_count = len(coverage_fixes) if coverage_fixes else 0
        
        if coverage_fixes:
            logger.info(
                f"Post-processing applied {coverage_fixes_count} fixes to ensure full coverage: "
                f"{'; '.join(coverage_fixes[:3])}" + 
                (f" (and {coverage_fixes_count - 3} more)" if coverage_fixes_count > 3 else "")
            )
        else:
            logger.debug("Post-processing: All boundaries already have full coverage")
        
        # Validate all boundaries meet requirements (4-8s, full coverage, no gaps)
        is_valid, validation_errors = validate_boundaries(clip_boundaries, duration)
        if not is_valid:
            logger.warning(
                f"Boundary validation found {len(validation_errors)} issues: "
                f"{'; '.join(validation_errors[:3])}" + 
                (f" (and {len(validation_errors) - 3} more)" if len(validation_errors) > 3 else "")
            )
            # Log all errors for debugging
            for error in validation_errors:
                logger.debug(f"Validation error: {error}")
        else:
            logger.info("All boundaries validated successfully (4-8s range, full coverage, no gaps)")
        
        # 6. Mood Classification (uses BPM, structure energy, spectral features)
        mood = classify_mood(audio, sr, bpm, song_structure)
        if mood.confidence < 0.3:
            fallbacks_used.append("mood_classification")
        logger.info(f"Mood classification: {mood.primary}, confidence={mood.confidence:.2f}")
        
        # Create AudioAnalysis object
        analysis = AudioAnalysis(
            job_id=job_id,
            bpm=bpm,
            duration=duration,
            beat_timestamps=beat_timestamps,
            beat_subdivisions=subdivisions,
            beat_strength=beat_strength,
            song_structure=song_structure,
            lyrics=lyrics,
            mood=mood,
            clip_boundaries=clip_boundaries,
            metadata={
                "beat_detection_confidence": beat_confidence,
                "structure_confidence": 0.8 if not structure_fallback else 0.5,
                "mood_confidence": mood.confidence,
                "lyrics_count": len(lyrics),
                "lyrics_confidence": round(lyrics_confidence, 3),
                "fallbacks_used": fallbacks_used,
                "subdivision_count": len(subdivisions.get("eighth_notes", [])) + len(subdivisions.get("sixteenth_notes", [])),
                "downbeat_count": sum(1 for s in beat_strength if s == "downbeat"),
                "intensity_distribution": {
                    "high": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "high"),
                    "medium": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "medium"),
                    "low": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "low")
                },
                "breakpoint_stats": breakpoint_stats,
                "segment_appropriateness": {
                    f"{start:.1f}-{end:.1f}": {
                        "duration": analysis["segment_duration"],
                        "is_appropriate": analysis["is_appropriate"],
                        "confidence": analysis["confidence"],
                        "recommendation": analysis["recommendation"]
                    }
                    for (start, end), analysis in segment_analyses.items()
                } if segment_analyses else {},
                "coverage_fixes_applied": coverage_fixes_count
            }
        )
        
        logger.info(
            f"Audio analysis complete for job {job_id}: "
            f"BPM={bpm:.1f}, duration={duration:.2f}s, "
            f"beats={len(beat_timestamps)}, segments={len(song_structure)}, "
            f"clips={len(clip_boundaries)}, lyrics={len(lyrics)}"
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Failed to parse audio for job {job_id}: {str(e)}")
        raise
