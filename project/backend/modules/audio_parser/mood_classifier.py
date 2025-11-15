"""
Mood classification component.

Rule-based mood classification using BPM, energy, and spectral features.
"""

import librosa
import numpy as np
from typing import List
from shared.models.audio import Mood, SongStructure, EnergyLevel
from shared.logging import get_logger

logger = get_logger("audio_parser")


def classify_mood(
    audio: np.ndarray,
    sr: int,
    bpm: float,
    song_structure: List[SongStructure]
) -> Mood:
    """
    Classify mood using rule-based approach.
    
    Args:
        audio: Audio signal array
        sr: Sample rate
        bpm: Beats per minute
        song_structure: List of song structure segments with energy
        
    Returns:
        Mood object with primary, secondary, energy_level, confidence
    """
    try:
        # 1. Extract features
        # Energy: Mean energy from structure analysis segments
        energy_mean = np.mean([_energy_to_float(seg.energy) for seg in song_structure]) if song_structure else 0.5
        
        # Spectral Centroid: Mean frequency (brightness indicator)
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
        centroid_mean = np.mean(spectral_centroid)
        
        # Spectral Rolloff: Frequency below which 85% of energy is contained
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr)[0]
        rolloff_mean = np.mean(spectral_rolloff)
        
        # Chroma variance (for complexity)
        chroma = librosa.feature.chroma(y=audio, sr=sr)
        chroma_variance = np.var(chroma)
        
        logger.debug(
            f"Mood features: BPM={bpm:.1f}, energy={energy_mean:.2f}, "
            f"centroid={centroid_mean:.0f}Hz, rolloff={rolloff_mean:.0f}Hz"
        )
        
        # 2. Calculate rule match scores
        scores = {
            'energetic': 0.0,
            'calm': 0.0,
            'dark': 0.0,
            'bright': 0.0
        }
        
        # Energetic: BPM >120 AND energy_mean >0.6 AND spectral_centroid >3000 Hz
        if bpm > 120 and energy_mean > 0.6 and centroid_mean > 3000:
            scores['energetic'] = min(1.0, (bpm/200) * (energy_mean/1.0) * (centroid_mean/5000))
        
        # Calm: BPM <90 AND energy_mean <0.4 AND spectral_rolloff <4000 Hz
        if bpm < 90 and energy_mean < 0.4 and rolloff_mean < 4000:
            scores['calm'] = min(1.0, ((90-bpm)/90) * ((0.4-energy_mean)/0.4) * ((4000-rolloff_mean)/4000))
        
        # Dark: Energy_mean <0.5 AND spectral_centroid <2500 Hz
        if energy_mean < 0.5 and centroid_mean < 2500:
            scores['dark'] = min(1.0, ((0.5-energy_mean)/0.5) * ((2500-centroid_mean)/2500))
        
        # Bright: Energy_mean >0.5 AND spectral_centroid >3500 Hz
        if energy_mean > 0.5 and centroid_mean > 3500:
            scores['bright'] = min(1.0, ((energy_mean-0.5)/0.5) * ((centroid_mean-3500)/3500))
        
        # 3. Select primary and secondary moods
        primary_mood = max(scores, key=scores.get)
        primary_score = scores[primary_mood]
        
        # Remove primary from consideration
        scores.pop(primary_mood)
        secondary_mood = max(scores, key=scores.get) if scores else None
        secondary_score = scores.get(secondary_mood, 0.0)
        
        # Only set secondary if score >0.3
        if secondary_score < 0.3:
            secondary_mood = None
        
        # 4. Set energy level
        if bpm > 120 and energy_mean > 0.6:
            energy_level = EnergyLevel.HIGH
        elif bpm < 90:
            energy_level = EnergyLevel.LOW
        else:
            energy_level = EnergyLevel.MEDIUM
        
        # 5. Calculate confidence
        confidence = primary_score
        
        # Fallback if all scores are too low
        if confidence < 0.3:
            logger.warning(f"Low confidence mood classification ({confidence:.2f}), using fallback")
            return Mood(
                primary="energetic",
                secondary=None,
                energy_level=EnergyLevel.MEDIUM,
                confidence=0.5
            )
        
        logger.info(
            f"Classified mood: primary={primary_mood}, secondary={secondary_mood}, "
            f"energy={energy_level.value}, confidence={confidence:.2f}"
        )
        
        return Mood(
            primary=primary_mood,
            secondary=secondary_mood,
            energy_level=energy_level,
            confidence=confidence
        )
        
    except Exception as e:
        logger.warning(f"Mood classification failed: {str(e)}, using fallback")
        return Mood(
            primary="energetic",
            secondary=None,
            energy_level=EnergyLevel.MEDIUM,
            confidence=0.5
        )


def _energy_to_float(energy: EnergyLevel) -> float:
    """Convert EnergyLevel enum to float value."""
    if energy == EnergyLevel.LOW:
        return 0.3
    elif energy == EnergyLevel.MEDIUM:
        return 0.6
    elif energy == EnergyLevel.HIGH:
        return 0.9
    else:
        return 0.5

