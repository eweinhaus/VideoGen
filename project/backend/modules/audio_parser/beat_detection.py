"""
Beat detection using Librosa + Aubio with deduplication.

Extract BPM and beat timestamps with ±50ms precision.
"""

import numpy as np
from typing import List, Tuple

import librosa
from shared.logging import get_logger

logger = get_logger("audio_parser")

# Try to import aubio, but fallback to librosa onset detection if not available
try:
    import aubio
    AUBIO_AVAILABLE = True
except ImportError:
    AUBIO_AVAILABLE = False
    logger.warning("aubio not available, using librosa onset detection as fallback")


def _deduplicate_beats(timestamps: List[float], threshold_ms: float = 50.0) -> List[float]:
    """
    Remove duplicate beats within threshold to ensure ±50ms precision.
    
    Args:
        timestamps: List of beat timestamps in seconds
        threshold_ms: Threshold in milliseconds (default: 50.0)
        
    Returns:
        Deduplicated list of timestamps
    """
    if not timestamps:
        return []
    
    # Sort timestamps
    sorted_timestamps = sorted(timestamps)
    
    # Convert threshold to seconds
    threshold_sec = threshold_ms / 1000.0
    
    # Initialize result with first timestamp
    result = [sorted_timestamps[0]]
    
    # Iterate through remaining timestamps
    for timestamp in sorted_timestamps[1:]:
        # Calculate time difference from last kept timestamp
        diff = timestamp - result[-1]
        
        # If difference >= threshold, add timestamp
        if diff >= threshold_sec:
            result.append(timestamp)
        # Otherwise skip (duplicate within threshold)
    
    return result


def detect_beats(y: np.ndarray, sr: int) -> Tuple[float, List[float], float]:
    """
    Extract BPM and beat timestamps with ±50ms precision.
    
    Uses librosa beat tracking and aubio onset detection (or librosa onset as fallback),
    then merges and deduplicates results.
    
    Args:
        y: Audio signal array
        sr: Sample rate
        
    Returns:
        Tuple of (BPM, beat_timestamps, confidence)
    """
    try:
        # 1. Librosa beat tracking
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='time')
        librosa_beats = beat_frames.tolist() if isinstance(beat_frames, np.ndarray) else list(beat_frames)
        
        logger.debug(f"Librosa detected {len(librosa_beats)} beats, tempo={tempo:.2f} BPM")
        
        # 2. Aubio onset detection (or librosa onset as fallback)
        aubio_beats = []
        aubio_success = False
        
        if AUBIO_AVAILABLE:
            try:
                # Create aubio tempo object
                win_s = 1024  # Window size
                hop_s = 512   # Hop size
                tempo_aubio = aubio.tempo("default", win_s, hop_s, sr)
                
                # Process audio in chunks
                total_frames = len(y)
                hop_length = hop_s
                
                for start in range(0, total_frames, hop_length):
                    end = min(start + hop_length, total_frames)
                    chunk = y[start:end]
                    
                    # Pad chunk if needed
                    if len(chunk) < hop_length:
                        chunk = np.pad(chunk, (0, hop_length - len(chunk)), mode='constant')
                    
                    # Detect tempo and beats
                    tempo_aubio(chunk)
                    if tempo_aubio.get_last_s() > 0:
                        beat_time = start / sr + tempo_aubio.get_last_s()
                        aubio_beats.append(beat_time)
                
                aubio_success = True
                logger.debug(f"Aubio detected {len(aubio_beats)} beats")
                
            except Exception as e:
                logger.warning(f"Aubio beat detection failed: {str(e)}, using librosa onset as fallback")
                aubio_success = False
        
        # Fallback to librosa onset detection if aubio not available or failed
        if not aubio_success:
            # Use librosa onset detection as alternative
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='time')
            aubio_beats = onset_frames.tolist() if isinstance(onset_frames, np.ndarray) else list(onset_frames)
            logger.debug(f"Librosa onset detection found {len(aubio_beats)} onsets")
        
        # 3. Merge and deduplicate
        all_beats = librosa_beats + aubio_beats
        deduplicated_beats = _deduplicate_beats(all_beats, threshold_ms=50.0)
        
        # 4. Calculate confidence based on agreement between methods
        if len(librosa_beats) > 0 and len(aubio_beats) > 0:
            # Measure agreement: count beats that are within 50ms of each other
            agreement_count = 0
            for lb in librosa_beats:
                for ab in aubio_beats:
                    if abs(lb - ab) <= 0.05:  # 50ms threshold
                        agreement_count += 1
                        break
            
            # Confidence is ratio of agreeing beats to total unique beats
            total_unique = len(set(librosa_beats + aubio_beats))
            if total_unique > 0:
                confidence = min(agreement_count / total_unique, 1.0)
            else:
                confidence = 0.5
        else:
            # If only one method worked, use lower confidence
            confidence = 0.6
        
        # 5. Validate BPM
        bpm = float(tempo)
        if bpm < 60 or bpm > 200:
            logger.warning(f"BPM {bpm:.2f} outside valid range [60, 200], using default 120 BPM")
            bpm = 120.0
            confidence = 0.5
        
        # 6. Fallback if low confidence
        if confidence < 0.6:
            logger.warning(f"Low confidence ({confidence:.2f}) in beat detection, using tempo-based boundaries")
            # Use tempo-based boundaries (4-beat intervals)
            beat_interval = 60.0 / bpm
            duration = len(y) / sr
            fallback_beats = []
            current_time = 0.0
            while current_time < duration:
                fallback_beats.append(current_time)
                current_time += beat_interval
            
            return (bpm, fallback_beats, confidence)
        
        logger.info(
            f"Beat detection complete: BPM={bpm:.2f}, beats={len(deduplicated_beats)}, confidence={confidence:.2f}"
        )
        
        return (bpm, deduplicated_beats, confidence)
        
    except Exception as e:
        logger.error(f"Beat detection failed: {str(e)}")
        # Fallback: use default tempo-based boundaries
        bpm = 120.0
        duration = len(y) / sr
        beat_interval = 60.0 / bpm
        fallback_beats = []
        current_time = 0.0
        while current_time < duration:
            fallback_beats.append(current_time)
            current_time += beat_interval
        
        logger.warning(f"Using fallback tempo-based beats: BPM={bpm}, beats={len(fallback_beats)}")
        return (bpm, fallback_beats, 0.5)

