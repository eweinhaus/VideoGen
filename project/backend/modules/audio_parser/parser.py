"""
Core audio parser orchestration.

Coordinates all audio analysis components.
"""

import librosa
import io
from uuid import UUID
from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

from modules.audio_parser.beat_detection import detect_beats, detect_beat_subdivisions, classify_beat_strength
from modules.audio_parser.structure_analysis import analyze_structure
from modules.audio_parser.mood_classifier import classify_mood
from modules.audio_parser.boundaries import generate_boundaries
from modules.audio_parser.lyrics_extraction import extract_lyrics

logger = get_logger("audio_parser")


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
        
        # 2. Clip Boundaries (generate first - these will be used for structure)
        clip_boundaries = generate_boundaries(beat_timestamps, bpm, duration)
        logger.info(f"Clip boundaries: {len(clip_boundaries)} clips")
        
        # 3. Structure Analysis (uses clip boundaries as base, then classifies each segment)
        from modules.audio_parser.structure_analysis import analyze_structure_from_clips
        structure_result = analyze_structure_from_clips(audio, sr, clip_boundaries, duration, beat_timestamps)
        if isinstance(structure_result, tuple):
            song_structure, structure_fallback = structure_result
        else:
            # Handle case where it returns just the list (backward compatibility)
            song_structure = structure_result
            structure_fallback = False
        
        if structure_fallback:
            fallbacks_used.append("structure_analysis")
        logger.info(f"Structure analysis: {len(song_structure)} segments (aligned with {len(clip_boundaries)} clips)")
        
        # 4. Mood Classification (uses BPM, structure energy, spectral features)
        mood = classify_mood(audio, sr, bpm, song_structure)
        if mood.confidence < 0.3:
            fallbacks_used.append("mood_classification")
        logger.info(f"Mood classification: {mood.primary}, confidence={mood.confidence:.2f}")
        
        # 5. Lyrics Extraction (independent, can run in parallel but sequential for simplicity)
        lyrics = await extract_lyrics(audio_bytes, job_id, duration)
        if len(lyrics) == 0:
            # Check if this was a fallback (instrumental) or actual failure
            # For now, empty lyrics is valid (instrumental tracks)
            pass
        logger.info(f"Lyrics extraction: {len(lyrics)} words")
        
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
                "fallbacks_used": fallbacks_used,
                "subdivision_count": len(subdivisions.get("eighth_notes", [])) + len(subdivisions.get("sixteenth_notes", [])),
                "downbeat_count": sum(1 for s in beat_strength if s == "downbeat"),
                "intensity_distribution": {
                    "high": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "high"),
                    "medium": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "medium"),
                    "low": sum(1 for s in song_structure if getattr(s, 'beat_intensity', None) == "low")
                }
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
