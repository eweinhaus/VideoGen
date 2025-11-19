"""
Audio context matching for multi-clip instructions.

Matches clips to audio segments (chorus, verse, etc.) for context-aware instructions.
"""
from typing import List
from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

logger = get_logger("clip_regenerator.audio_context_matcher")


def identify_chorus_clips(audio_data: AudioAnalysis) -> List[int]:
    """
    Identify clips that correspond to chorus segments.
    
    This is a re-export from instruction_parser for convenience.
    See instruction_parser.identify_chorus_clips() for implementation.
    """
    from modules.clip_regenerator.instruction_parser import identify_chorus_clips as _identify_chorus_clips
    return _identify_chorus_clips(audio_data)


def identify_verse_clips(audio_data: AudioAnalysis) -> List[int]:
    """
    Identify clips that correspond to verse segments.
    
    This is a re-export from instruction_parser for convenience.
    See instruction_parser.identify_verse_clips() for implementation.
    """
    from modules.clip_regenerator.instruction_parser import identify_verse_clips as _identify_verse_clips
    return _identify_verse_clips(audio_data)

