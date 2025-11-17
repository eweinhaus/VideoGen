"""
Beat detection component.

Extract BPM and precise beat timestamps using Librosa.
"""

import librosa
import numpy as np
from typing import Tuple, List
from shared.logging import get_logger

logger = get_logger("audio_parser")


def detect_beats(audio: np.ndarray, sr: int = 22050) -> Tuple[float, List[float], float]:
    """
    Detect beats in audio using Librosa.
    
    Args:
        audio: Audio signal (numpy array)
        sr: Sample rate (default: 22050)
        
    Returns:
        (bpm, beat_timestamps, confidence)
    """
    duration = len(audio) / sr  # Calculate duration from audio length
    
    try:
        # Extract tempo and beats
        tempo, beats = librosa.beat.beat_track(y=audio, sr=sr)
        
        # Convert tempo to scalar (librosa may return numpy array)
        # Use .item() to extract scalar from numpy array to avoid deprecation warning
        if hasattr(tempo, 'item'):
            tempo = float(tempo.item())
        else:
            tempo = float(tempo)
        
        # Validate BPM range
        if tempo < 60:
            logger.warning(f"BPM {tempo} below 60, clamping to 60")
            tempo = 60.0
            confidence = 0.5  # Low confidence due to clamping
        elif tempo > 200:
            logger.warning(f"BPM {tempo} above 200, clamping to 200")
            tempo = 200.0
            confidence = 0.5
        else:
            # Librosa doesn't return confidence directly, estimate from beat consistency
            # Calculate confidence based on beat interval consistency
            if len(beats) > 1:
                beat_intervals = np.diff(beats)
                interval_std = np.std(beat_intervals)
                interval_mean = np.mean(beat_intervals)
                # Lower std relative to mean = higher confidence
                confidence = max(0.0, min(1.0, 1.0 - (interval_std / interval_mean) if interval_mean > 0 else 0.5))
            else:
                confidence = 0.5
        
        # Convert frames to timestamps
        beat_timestamps = librosa.frames_to_time(beats, sr=sr).tolist()
        
        # Check if fallback needed
        if confidence < 0.6 or len(beat_timestamps) == 0:
            logger.warning(f"Low confidence ({confidence}) or no beats, using tempo-based fallback")
            return _tempo_based_fallback(tempo, duration)
        
        logger.info(f"Detected {len(beat_timestamps)} beats at {tempo:.1f} BPM (confidence: {confidence:.2f})")
        return tempo, beat_timestamps, confidence
        
    except Exception as e:
        # Fallback on any error
        logger.warning(f"Beat detection failed: {str(e)}, using tempo-based fallback")
        return _tempo_based_fallback(120.0, duration)  # Default 120 BPM


def _tempo_based_fallback(bpm: float, duration: float) -> Tuple[float, List[float], float]:
    """
    Generate tempo-based beats as fallback.
    
    Args:
        bpm: Tempo in beats per minute
        duration: Audio duration in seconds
        
    Returns:
        (bpm, beat_timestamps, confidence)
    """
    beat_interval = 60.0 / bpm
    beat_timestamps = []
    current_time = 0.0
    while current_time < duration:
        beat_timestamps.append(current_time)
        current_time += beat_interval
    logger.info(f"Generated {len(beat_timestamps)} tempo-based beats at {bpm:.1f} BPM (fallback)")
    return bpm, beat_timestamps, 0.5  # Low confidence indicates fallback used


def detect_beat_subdivisions(
    beat_timestamps: List[float], 
    bpm: float,
    duration: float
) -> dict:
    """
    Detect eighth and sixteenth note subdivisions.
    
    Uses simple interpolation: divides each beat interval equally.
    This works well for most music with steady tempo.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        bpm: Beats per minute
        duration: Audio duration in seconds
        
    Returns:
        Dict with 'eighth_notes' and 'sixteenth_notes' lists
    """
    if not beat_timestamps or len(beat_timestamps) < 2:
        return {"eighth_notes": [], "sixteenth_notes": []}
    
    eighth_notes = []
    sixteenth_notes = []
    
    # Calculate average beat interval for last beat estimation
    beat_intervals = [beat_timestamps[i+1] - beat_timestamps[i] 
                     for i in range(len(beat_timestamps)-1)]
    avg_interval = sum(beat_intervals) / len(beat_intervals) if beat_intervals else 60.0 / bpm
    
    # Generate subdivisions for each beat interval
    for i in range(len(beat_timestamps) - 1):
        start = beat_timestamps[i]
        end = beat_timestamps[i + 1]
        interval = end - start
        
        # Eighth notes (divide by 2)
        eighth_1 = start + interval / 2
        eighth_notes.append(eighth_1)
        
        # Sixteenth notes (divide by 4)
        sixteenth_1 = start + interval / 4
        sixteenth_2 = start + interval / 2  # Same as eighth
        sixteenth_3 = start + 3 * interval / 4
        sixteenth_notes.extend([sixteenth_1, sixteenth_2, sixteenth_3])
    
    # Handle last beat (estimate next beat interval)
    if beat_timestamps:
        last_beat = beat_timestamps[-1]
        if last_beat < duration:
            next_beat_est = last_beat + avg_interval
            if next_beat_est <= duration:
                interval = next_beat_est - last_beat
                eighth_notes.append(last_beat + interval / 2)
                sixteenth_notes.extend([
                    last_beat + interval / 4,
                    last_beat + interval / 2,
                    last_beat + 3 * interval / 4
                ])
    
    # Sort and deduplicate (eighth notes are also in sixteenth)
    eighth_notes = sorted(set(eighth_notes))
    sixteenth_notes = sorted(set(sixteenth_notes))
    
    # Ensure all timestamps are within [0, duration]
    eighth_notes = [t for t in eighth_notes if 0 <= t <= duration]
    sixteenth_notes = [t for t in sixteenth_notes if 0 <= t <= duration]
    
    logger.info(f"Detected {len(eighth_notes)} eighth notes, {len(sixteenth_notes)} sixteenth notes")
    
    return {
        "eighth_notes": eighth_notes,
        "sixteenth_notes": sixteenth_notes
    }


def classify_beat_strength(
    beat_timestamps: List[float],
    audio: np.ndarray,
    sr: int,
    bpm: float
) -> List[str]:
    """
    Classify each beat as 'downbeat' or 'upbeat'.
    
    Uses pattern-based approach: assumes 4/4 time signature.
    In 4/4: beats 0, 2, 4, 6... (1 and 3) are downbeats.
    
    Args:
        beat_timestamps: List of beat timestamps in seconds
        audio: Audio signal (for future energy-based validation)
        sr: Sample rate
        bpm: Beats per minute
        
    Returns:
        List of 'downbeat' or 'upbeat' strings (same length as beat_timestamps)
    """
    if not beat_timestamps:
        return []
    
    beat_strength = []
    
    # Pattern: downbeat, upbeat, downbeat, upbeat (1, 2, 3, 4 in 4/4)
    # In 4/4: beats 0, 2, 4, 6... are downbeats (1 and 3)
    for i, beat_time in enumerate(beat_timestamps):
        if i % 4 == 0 or i % 4 == 2:
            strength = "downbeat"
        else:
            strength = "upbeat"
        
        beat_strength.append(strength)
    
    downbeat_count = sum(1 for s in beat_strength if s == "downbeat")
    logger.info(f"Classified {downbeat_count} downbeats, {len(beat_strength) - downbeat_count} upbeats")
    
    return beat_strength
