"""
Audio Parser Module.

Comprehensive audio analysis to extract beats, tempo, song structure, lyrics, mood, and clip boundaries.
"""

from modules.audio_parser.parser import parse_audio
from modules.audio_parser.main import process_audio_analysis
from shared.errors import AudioAnalysisError, ValidationError
from shared.logging import get_logger

logger = get_logger("audio_parser")

__all__ = [
    "parse_audio",
    "process_audio_analysis",
    "AudioAnalysisError",
    "ValidationError",
]

