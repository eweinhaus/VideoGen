"""
Breakpoint detection component.

Detects logical audio breakpoints from lyrics, energy, silence, and harmonic changes.
"""

import numpy as np
import librosa
from typing import List, Tuple
from shared.models.audio import Breakpoint, Lyric, SongStructure
from shared.logging import get_logger

logger = get_logger("audio_parser")


def detect_lyrics_breakpoints(
    lyrics: List[Lyric],
    segment_start: float,
    segment_end: float
) -> List[Breakpoint]:
    """
    Detect breakpoints from lyrics within a segment.
    
    Identifies phrase endings, sentence endings, and word gaps.
    
    Args:
        lyrics: List of lyric words with timestamps
        segment_start: Segment start time in seconds
        segment_end: Segment end time in seconds
        
    Returns:
        List of Breakpoint objects
    """
    if not lyrics:
        return []
    
    # Filter lyrics to segment range
    segment_lyrics = [
        lyric for lyric in lyrics
        if segment_start <= lyric.timestamp <= segment_end
    ]
    
    if len(segment_lyrics) < 2:
        return []
    
    breakpoints = []
    
    # Detect word gaps (phrase boundaries)
    for i in range(len(segment_lyrics) - 1):
        current_word = segment_lyrics[i]
        next_word = segment_lyrics[i + 1]
        
        # Estimate word duration (assume 0.3s average, or use gap if available)
        # For now, use gap between words
        gap = next_word.timestamp - current_word.timestamp
        
        # Phrase boundary: gap > 0.5s
        if gap > 0.5:
            # Use end of current word as breakpoint
            # Estimate word end as start + 0.3s (or use next word start - small buffer)
            breakpoint_time = min(current_word.timestamp + 0.3, next_word.timestamp - 0.1)
            
            # Confidence based on gap size
            confidence = min(0.9, 0.5 + (gap - 0.5) * 0.4)  # 0.5-0.9 based on gap
            
            breakpoints.append(Breakpoint(
                timestamp=breakpoint_time,
                confidence=confidence,
                source="lyrics",
                type="phrase_end" if gap < 1.0 else "sentence_end",
                metadata={"gap_duration": gap, "word": current_word.text}
            ))
    
    # Detect sentence endings (longer gaps or punctuation patterns)
    # For now, treat gaps > 1.0s as sentence endings (already handled above)
    
    logger.debug(
        f"Detected {len(breakpoints)} lyrics breakpoints in segment "
        f"[{segment_start:.1f}s - {segment_end:.1f}s]"
    )
    
    return breakpoints


def detect_energy_breakpoints(
    audio: np.ndarray,
    sr: int,
    segment_start: float,
    segment_end: float,
    hop_length: int = 512
) -> List[Breakpoint]:
    """
    Detect breakpoints from energy transitions.
    
    Identifies energy peaks, valleys, and significant transitions.
    
    Args:
        audio: Full audio signal array
        sr: Sample rate
        segment_start: Segment start time in seconds
        segment_end: Segment end time in seconds
        hop_length: Hop length for feature extraction
        
    Returns:
        List of Breakpoint objects
    """
    # Extract segment audio
    start_frame = int(segment_start * sr)
    end_frame = int(segment_end * sr)
    if end_frame > len(audio):
        end_frame = len(audio)
    if start_frame >= end_frame:
        return []
    
    segment_audio = audio[start_frame:end_frame]
    
    if len(segment_audio) == 0:
        return []
    
    # Compute RMS energy
    rms = librosa.feature.rms(y=segment_audio, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    times = times + segment_start  # Convert to absolute time
    
    if len(rms) < 3:
        return []
    
    # Normalize energy
    rms_max = np.max(rms)
    rms_min = np.min(rms)
    if rms_max == rms_min:
        return []
    
    rms_norm = (rms - rms_min) / (rms_max - rms_min)
    
    # Detect local peaks and valleys (simple implementation without scipy)
    def find_local_extrema(values, is_maxima=True, min_height=None, min_distance=1):
        """Simple peak/valley detection."""
        extrema = []
        for i in range(1, len(values) - 1):
            if is_maxima:
                is_extremum = values[i] > values[i-1] and values[i] > values[i+1]
            else:
                is_extremum = values[i] < values[i-1] and values[i] < values[i+1]
            
            if is_extremum:
                if min_height is None:
                    extrema.append(i)
                elif (is_maxima and values[i] >= min_height) or \
                     (not is_maxima and values[i] <= min_height):
                    # Check distance from previous extremum
                    if not extrema or (i - extrema[-1]) >= min_distance:
                        extrema.append(i)
        return extrema
    
    # Energy peaks (local maxima)
    peaks = find_local_extrema(rms_norm, is_maxima=True, min_height=0.3, min_distance=max(1, len(rms) // 10))
    
    # Energy valleys (local minima)
    valleys = find_local_extrema(rms_norm, is_maxima=False, min_height=-0.7, min_distance=max(1, len(rms) // 10))
    
    breakpoints = []
    
    # Add peak breakpoints (lower confidence, peaks are less definitive)
    for peak_idx in peaks:
        if peak_idx < len(times):
            breakpoints.append(Breakpoint(
                timestamp=times[peak_idx],
                confidence=0.5,
                source="energy",
                type="energy_peak",
                metadata={"energy_value": float(rms_norm[peak_idx])}
            ))
    
    # Add valley breakpoints (higher confidence, valleys indicate transitions)
    for valley_idx in valleys:
        if valley_idx < len(times):
            breakpoints.append(Breakpoint(
                timestamp=times[valley_idx],
                confidence=0.6,
                source="energy",
                type="energy_valley",
                metadata={"energy_value": float(rms_norm[valley_idx])}
            ))
    
    # Detect significant energy transitions (>30% change over 1s window)
    window_frames = int(1.0 * sr / hop_length)  # 1 second window
    for i in range(len(rms_norm) - window_frames):
        energy_start = rms_norm[i]
        energy_end = rms_norm[i + window_frames]
        change = abs(energy_end - energy_start)
        
        if change > 0.3:  # 30% change
            transition_time = times[i + window_frames // 2]
            confidence = min(0.8, 0.5 + change * 0.3)
            
            breakpoints.append(Breakpoint(
                timestamp=transition_time,
                confidence=confidence,
                source="energy",
                type="energy_transition",
                metadata={"change_magnitude": float(change)}
            ))
    
    logger.debug(
        f"Detected {len(breakpoints)} energy breakpoints in segment "
        f"[{segment_start:.1f}s - {segment_end:.1f}s]"
    )
    
    return breakpoints


def detect_silence_breakpoints(
    audio: np.ndarray,
    sr: int,
    segment_start: float,
    segment_end: float,
    hop_length: int = 512
) -> List[Breakpoint]:
    """
    Detect breakpoints from silence/pause regions.
    
    Identifies pauses and silence gaps that indicate phrase boundaries.
    
    Args:
        audio: Full audio signal array
        sr: Sample rate
        segment_start: Segment start time in seconds
        segment_end: Segment end time in seconds
        hop_length: Hop length for feature extraction
        
    Returns:
        List of Breakpoint objects
    """
    # Extract segment audio
    start_frame = int(segment_start * sr)
    end_frame = int(segment_end * sr)
    if end_frame > len(audio):
        end_frame = len(audio)
    if start_frame >= end_frame:
        return []
    
    segment_audio = audio[start_frame:end_frame]
    
    if len(segment_audio) == 0:
        return []
    
    # Compute RMS energy
    rms = librosa.feature.rms(y=segment_audio, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    times = times + segment_start  # Convert to absolute time
    
    if len(rms) == 0:
        return []
    
    # Calculate silence threshold (10% of segment average)
    rms_mean = np.mean(rms)
    silence_threshold = rms_mean * 0.1
    
    # Find silence regions
    silence_mask = rms < silence_threshold
    
    if not np.any(silence_mask):
        return []
    
    breakpoints = []
    
    # Group consecutive silence frames
    in_silence = False
    silence_start_idx = None
    
    for i, is_silent in enumerate(silence_mask):
        if is_silent and not in_silence:
            # Start of silence
            in_silence = True
            silence_start_idx = i
        elif not is_silent and in_silence:
            # End of silence
            in_silence = False
            silence_duration = times[i] - times[silence_start_idx]
            
            # Only consider significant pauses (>0.3s)
            if silence_duration >= 0.3:
                # Use start of silence as breakpoint
                breakpoint_time = times[silence_start_idx]
                
                # Confidence based on silence duration
                if silence_duration >= 1.0:
                    confidence = 0.8  # Long silence
                    bp_type = "silence_gap"
                else:
                    confidence = 0.7  # Brief pause
                    bp_type = "pause"
                
                breakpoints.append(Breakpoint(
                    timestamp=breakpoint_time,
                    confidence=confidence,
                    source="silence",
                    type=bp_type,
                    metadata={"silence_duration": silence_duration}
                ))
    
    # Handle silence at end of segment
    if in_silence and silence_start_idx is not None:
        silence_duration = segment_end - times[silence_start_idx]
        if silence_duration >= 0.3:
            breakpoint_time = times[silence_start_idx]
            confidence = 0.7 if silence_duration < 1.0 else 0.8
            bp_type = "pause" if silence_duration < 1.0 else "silence_gap"
            
            breakpoints.append(Breakpoint(
                timestamp=breakpoint_time,
                confidence=confidence,
                source="silence",
                type=bp_type,
                metadata={"silence_duration": silence_duration}
            ))
    
    logger.debug(
        f"Detected {len(breakpoints)} silence breakpoints in segment "
        f"[{segment_start:.1f}s - {segment_end:.1f}s]"
    )
    
    return breakpoints


def detect_harmonic_breakpoints(
    audio: np.ndarray,
    sr: int,
    segment_start: float,
    segment_end: float,
    structure_segments: List[SongStructure],
    hop_length: int = 512
) -> List[Breakpoint]:
    """
    Detect breakpoints from harmonic/chroma changes.
    
    Identifies chord changes and structure segment boundaries.
    
    Args:
        audio: Full audio signal array
        sr: Sample rate
        segment_start: Segment start time in seconds
        segment_end: Segment end time in seconds
        structure_segments: List of song structure segments
        hop_length: Hop length for feature extraction
        
    Returns:
        List of Breakpoint objects
    """
    breakpoints = []
    
    # Add structure segment boundaries that fall within this segment
    for structure_seg in structure_segments:
        # Check if structure boundary is within segment
        if (segment_start < structure_seg.start < segment_end) or \
           (segment_start < structure_seg.end < segment_end):
            # Structure boundary is a high-confidence breakpoint
            if segment_start < structure_seg.start < segment_end:
                breakpoints.append(Breakpoint(
                    timestamp=structure_seg.start,
                    confidence=0.9,
                    source="harmonic",
                    type="structure_boundary",
                    metadata={"segment_type": structure_seg.type.value}
                ))
            if segment_start < structure_seg.end < segment_end:
                breakpoints.append(Breakpoint(
                    timestamp=structure_seg.end,
                    confidence=0.9,
                    source="harmonic",
                    type="structure_boundary",
                    metadata={"segment_type": structure_seg.type.value}
                ))
    
    # Detect chroma changes within segment
    start_frame = int(segment_start * sr)
    end_frame = int(segment_end * sr)
    if end_frame > len(audio):
        end_frame = len(audio)
    if start_frame >= end_frame:
        return breakpoints
    
    segment_audio = audio[start_frame:end_frame]
    
    if len(segment_audio) < hop_length * 2:
        return breakpoints
    
    # Extract chroma features
    chroma = librosa.feature.chroma_stft(y=segment_audio, sr=sr, hop_length=hop_length)
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
    times = times + segment_start  # Convert to absolute time
    
    if chroma.shape[1] < 3:
        return breakpoints
    
    # Normalize chroma vectors
    chroma_norm = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-10)
    
    # Detect significant chroma changes (cosine similarity < 0.7)
    similarity_threshold = 0.7
    
    for i in range(chroma_norm.shape[1] - 1):
        vec1 = chroma_norm[:, i]
        vec2 = chroma_norm[:, i + 1]
        
        # Cosine similarity
        similarity = np.dot(vec1, vec2)
        
        if similarity < similarity_threshold:
            # Significant harmonic change
            change_time = times[i + 1]
            confidence = 0.7 - (similarity - 0.5) * 0.4  # 0.5-0.7 based on similarity
            
            breakpoints.append(Breakpoint(
                timestamp=change_time,
                confidence=max(0.5, confidence),
                source="harmonic",
                type="chord_change",
                metadata={"similarity": float(similarity)}
            ))
    
    logger.debug(
        f"Detected {len(breakpoints)} harmonic breakpoints in segment "
        f"[{segment_start:.1f}s - {segment_end:.1f}s]"
    )
    
    return breakpoints


def aggregate_breakpoints(
    all_breakpoints: List[Breakpoint],
    segment_start: float,
    segment_end: float,
    merge_distance: float = 0.5
) -> List[Breakpoint]:
    """
    Aggregate and deduplicate breakpoints.
    
    Merges breakpoints within merge_distance of each other, weighted by
    source priority and confidence.
    
    Args:
        all_breakpoints: List of all detected breakpoints
        segment_start: Segment start time in seconds
        segment_end: Segment end time in seconds
        merge_distance: Distance threshold for merging breakpoints (seconds)
        
    Returns:
        List of aggregated Breakpoint objects, sorted by timestamp
    """
    if not all_breakpoints:
        return []
    
    # Filter to segment range
    filtered = [
        bp for bp in all_breakpoints
        if segment_start <= bp.timestamp <= segment_end
    ]
    
    if not filtered:
        return []
    
    # Source priority weights
    source_weights = {
        "lyrics": 0.8,
        "silence": 0.7,
        "harmonic": 0.7,
        "energy": 0.6,
        "beat": 0.5
    }
    
    # Sort by timestamp
    filtered.sort(key=lambda bp: bp.timestamp)
    
    # Merge breakpoints within merge_distance
    merged = []
    i = 0
    
    while i < len(filtered):
        current = filtered[i]
        cluster = [current]
        
        # Find all breakpoints within merge_distance
        j = i + 1
        while j < len(filtered) and filtered[j].timestamp - current.timestamp <= merge_distance:
            cluster.append(filtered[j])
            j += 1
        
        if len(cluster) == 1:
            # No merging needed
            merged.append(current)
        else:
            # Merge cluster: weighted average timestamp, max confidence, highest priority source
            total_weight = 0.0
            weighted_time = 0.0
            max_confidence = 0.0
            best_source = None
            best_type = None
            combined_metadata = {}
            
            for bp in cluster:
                weight = source_weights.get(bp.source, 0.5) * bp.confidence
                total_weight += weight
                weighted_time += bp.timestamp * weight
                max_confidence = max(max_confidence, bp.confidence)
                
                # Use highest priority source
                if best_source is None or source_weights.get(bp.source, 0.5) > source_weights.get(best_source, 0.5):
                    best_source = bp.source
                    best_type = bp.type
                
                # Combine metadata
                combined_metadata.update(bp.metadata or {})
                combined_metadata[f"{bp.source}_confidence"] = bp.confidence
            
            # Calculate weighted average timestamp
            avg_timestamp = weighted_time / total_weight if total_weight > 0 else current.timestamp
            
            # Boost confidence if multiple sources agree
            if len(cluster) > 1:
                max_confidence = min(1.0, max_confidence + 0.1 * (len(cluster) - 1))
            
            merged.append(Breakpoint(
                timestamp=avg_timestamp,
                confidence=max_confidence,
                source=best_source or current.source,
                type=best_type or current.type,
                metadata={
                    **combined_metadata,
                    "merged_count": len(cluster),
                    "sources": list(set(bp.source for bp in cluster))
                }
            ))
        
        i = j
    
    logger.debug(
        f"Aggregated {len(all_breakpoints)} breakpoints to {len(merged)} "
        f"in segment [{segment_start:.1f}s - {segment_end:.1f}s]"
    )
    
    return merged

