"""
Mood classification using audio features.

Classify mood (energetic/calm/dark/bright) with confidence scores.
"""

import numpy as np
from typing import List

import librosa
from shared.models.audio import Mood, SongStructure
from shared.logging import get_logger

logger = get_logger("audio_parser")


def classify_mood(
    y: np.ndarray,
    sr: int,
    bpm: float,
    structure: List[SongStructure]
) -> Mood:
    """
    Classify mood using rule-based approach.
    
    Args:
        y: Audio signal array
        sr: Sample rate
        bpm: Beats per minute
        structure: List of song structure segments
        
    Returns:
        Mood model
    """
    try:
        # 1. Extract features
        # Tempo (BPM): Already available
        # Spectral centroid: Brightness indicator
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        centroid_mean = np.mean(spectral_centroid)
        
        # Zero crossing rate: Texture indicator
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        zcr_mean = np.mean(zcr)
        
        # Spectral rolloff: High-frequency content
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        rolloff_mean = np.mean(rolloff)
        
        # Energy: RMS across entire track
        rms = librosa.feature.rms(y=y)[0]
        energy = np.mean(rms)
        # Normalize energy to 0-1 range (rough estimate)
        energy_norm = min(energy / 0.5, 1.0) if energy > 0 else 0.0
        
        logger.debug(
            f"Mood features: BPM={bpm:.2f}, centroid={centroid_mean:.2f} Hz, "
            f"energy={energy_norm:.2f}, rolloff={rolloff_mean:.2f} Hz"
        )
        
        # 2. Rule-based classification
        # Primary mood
        primary_mood = None
        secondary_mood = None
        confidence = 0.5
        
        # Check energetic condition
        if bpm > 130 and energy_norm > 0.7:
            primary_mood = "energetic"
            confidence = 0.8
        # Check calm condition
        elif bpm < 90 and energy_norm < 0.4:
            primary_mood = "calm"
            confidence = 0.8
        # Check dark condition (low spectral centroid)
        elif centroid_mean < 2000:
            primary_mood = "dark"
            confidence = 0.7
        # Check bright condition (high spectral centroid)
        elif centroid_mean > 4000:
            primary_mood = "bright"
            confidence = 0.7
        # Default based on BPM
        else:
            if bpm > 100:
                primary_mood = "energetic"
                confidence = 0.6
            else:
                primary_mood = "calm"
                confidence = 0.6
        
        # Secondary mood based on complementary features
        if primary_mood == "energetic":
            if centroid_mean > 3500:
                secondary_mood = "bright"
            elif centroid_mean < 2000:
                secondary_mood = "dark"
        elif primary_mood == "calm":
            if centroid_mean > 3000:
                secondary_mood = "bright"
            elif centroid_mean < 2000:
                secondary_mood = "dark"
        elif primary_mood == "dark":
            if bpm > 100:
                secondary_mood = "energetic"
            else:
                secondary_mood = "calm"
        elif primary_mood == "bright":
            if bpm > 100:
                secondary_mood = "energetic"
            else:
                secondary_mood = "calm"
        
        # Adjust confidence based on feature agreement
        feature_agreement = 0
        total_features = 0
        
        # BPM agreement
        if (primary_mood == "energetic" and bpm > 100) or (primary_mood == "calm" and bpm < 100):
            feature_agreement += 1
        total_features += 1
        
        # Energy agreement
        if (primary_mood in ["energetic", "bright"] and energy_norm > 0.5) or \
           (primary_mood in ["calm", "dark"] and energy_norm < 0.5):
            feature_agreement += 1
        total_features += 1
        
        # Centroid agreement
        if (primary_mood in ["bright"] and centroid_mean > 3000) or \
           (primary_mood in ["dark"] and centroid_mean < 2500):
            feature_agreement += 1
        total_features += 1
        
        if total_features > 0:
            agreement_ratio = feature_agreement / total_features
            confidence = min(confidence + (agreement_ratio * 0.2), 1.0)
        
        # Energy level
        if energy_norm < 0.4 or bpm < 90:
            energy_level = "low"
        elif energy_norm > 0.7 or bpm > 130:
            energy_level = "high"
        else:
            energy_level = "medium"
        
        logger.info(
            f"Mood classification: primary={primary_mood}, secondary={secondary_mood}, "
            f"energy={energy_level}, confidence={confidence:.2f}"
        )
        
        return Mood(
            primary=primary_mood,
            secondary=secondary_mood,
            energy_level=energy_level,
            confidence=confidence
        )
        
    except Exception as e:
        logger.error(f"Mood classification failed: {str(e)}")
        # Fallback: default mood
        return Mood(
            primary="energetic" if bpm > 100 else "calm",
            secondary=None,
            energy_level="medium",
            confidence=0.5
        )

