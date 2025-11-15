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
