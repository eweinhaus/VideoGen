"""
Core audio parsing orchestration.

Coordinate all analysis steps and assemble final result.
"""

import io
import time
from typing import Dict, Any
from uuid import UUID

import librosa
import numpy as np

from shared.models.audio import AudioAnalysis
from shared.errors import AudioAnalysisError
from shared.logging import get_logger, set_job_id

from modules.audio_parser.beat_detection import detect_beats
from modules.audio_parser.structure_analysis import analyze_structure
from modules.audio_parser.mood_classifier import classify_mood
from modules.audio_parser.whisper_client import extract_lyrics
from modules.audio_parser.boundaries import generate_boundaries

logger = get_logger("audio_parser")


async def parse_audio(audio_bytes: bytes, job_id: UUID) -> AudioAnalysis:
    """
    Coordinate all analysis steps and assemble final result.
    
    Args:
        audio_bytes: Audio file bytes
        job_id: Job ID
        
    Returns:
        AudioAnalysis model
        
    Raises:
        AudioAnalysisError: If processing fails
    """
    # Set job_id in context for logging
    set_job_id(job_id)
    
    start_time = time.time()
    metadata: Dict[str, Any] = {
        "cache_hit": False,
        "fallback_used": {},
        "confidence_scores": {}
    }
    
    try:
        # 1. Load audio file into librosa
        logger.info(f"Loading audio file for job {job_id}")
        audio_file = io.BytesIO(audio_bytes)
        y, sr = librosa.load(audio_file, sr=None)
        
        if len(y) == 0 or sr is None:
            raise AudioAnalysisError("Failed to load audio file: empty or invalid", job_id=job_id)
        
        # 2. Calculate duration
        duration = len(y) / sr
        logger.info(f"Audio loaded: duration={duration:.2f}s, sample_rate={sr} Hz")
        
        # 3. Extract BPM and beats
        logger.info("Detecting beats...")
        try:
            bpm, beat_timestamps, beat_confidence = detect_beats(y, sr)
            metadata["confidence_scores"]["beat_detection"] = beat_confidence
            logger.info(f"Beat detection complete: BPM={bpm:.2f}, beats={len(beat_timestamps)}, confidence={beat_confidence:.2f}")
        except Exception as e:
            logger.error(f"Beat detection failed: {str(e)}")
            metadata["fallback_used"]["beat_detection"] = True
            # Fallback: use tempo-based boundaries
            bpm = 120.0
            beat_interval = 60.0 / bpm
            beat_timestamps = []
            current_time = 0.0
            while current_time < duration:
                beat_timestamps.append(current_time)
                current_time += beat_interval
            beat_confidence = 0.5
            metadata["confidence_scores"]["beat_detection"] = beat_confidence
        
        # 4. Classify song structure
        logger.info("Analyzing song structure...")
        try:
            song_structure = analyze_structure(y, sr, beat_timestamps, duration)
            logger.info(f"Structure analysis complete: {len(song_structure)} segments")
        except Exception as e:
            logger.error(f"Structure analysis failed: {str(e)}")
            metadata["fallback_used"]["structure_analysis"] = True
            # Fallback: single segment
            from shared.models.audio import SongStructure
            song_structure = [SongStructure(
                type="verse",
                start=0.0,
                end=duration,
                energy="medium"
            )]
            logger.warning("Using fallback single-segment structure")
        
        # 5. Extract lyrics (async, with retry)
        logger.info("Extracting lyrics...")
        lyrics = []
        try:
            lyrics = await extract_lyrics(audio_bytes, job_id, duration)
            logger.info(f"Lyrics extraction complete: {len(lyrics)} words")
        except Exception as e:
            logger.error(f"Lyrics extraction failed: {str(e)}")
            metadata["fallback_used"]["lyrics"] = True
            # Fallback: empty lyrics array
            lyrics = []
            logger.warning("Using fallback empty lyrics (instrumental track)")
        
        # 6. Classify mood
        logger.info("Classifying mood...")
        try:
            mood = classify_mood(y, sr, bpm, song_structure)
            metadata["confidence_scores"]["mood"] = mood.confidence
            logger.info(f"Mood classification complete: {mood.primary}, confidence={mood.confidence:.2f}")
        except Exception as e:
            logger.error(f"Mood classification failed: {str(e)}")
            metadata["fallback_used"]["mood"] = True
            # Fallback: default mood
            from shared.models.audio import Mood
            mood = Mood(
                primary="energetic" if bpm > 100 else "calm",
                secondary=None,
                energy_level="medium",
                confidence=0.5
            )
            logger.warning("Using fallback default mood")
        
        # 7. Generate clip boundaries
        logger.info("Generating clip boundaries...")
        try:
            clip_boundaries = generate_boundaries(
                beat_timestamps=beat_timestamps,
                duration=duration,
                bpm=bpm,
                min_clips=3,
                min_duration=4.0,
                max_duration=8.0
            )
            logger.info(f"Boundary generation complete: {len(clip_boundaries)} boundaries")
        except Exception as e:
            logger.error(f"Boundary generation failed: {str(e)}")
            metadata["fallback_used"]["boundaries"] = True
            # Fallback: uniform boundaries
            from shared.models.audio import ClipBoundary
            n_clips = max(3, int(duration / 6.0))
            clip_duration = duration / n_clips
            clip_boundaries = []
            for i in range(n_clips):
                start = i * clip_duration
                end = (i + 1) * clip_duration if i < n_clips - 1 else duration
                clip_boundaries.append(ClipBoundary(
                    start=start,
                    end=end,
                    duration=end - start
                ))
            logger.warning("Using fallback uniform boundaries")
        
        # 8. Assemble AudioAnalysis model
        processing_time = time.time() - start_time
        metadata["processing_time"] = processing_time
        
        analysis = AudioAnalysis(
            job_id=job_id,
            bpm=bpm,
            duration=duration,
            beat_timestamps=beat_timestamps,
            song_structure=song_structure,
            lyrics=lyrics,
            mood=mood,
            clip_boundaries=clip_boundaries,
            metadata=metadata
        )
        
        logger.info(
            f"Audio analysis complete for job {job_id}: "
            f"duration={duration:.2f}s, processing_time={processing_time:.2f}s, "
            f"beats={len(beat_timestamps)}, segments={len(song_structure)}, "
            f"lyrics={len(lyrics)}, boundaries={len(clip_boundaries)}"
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Audio parsing failed for job {job_id}: {str(e)}")
        raise AudioAnalysisError(f"Failed to parse audio: {str(e)}", job_id=job_id) from e

