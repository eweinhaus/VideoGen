"""
Composer module.

Final stage of video generation pipeline. Stitches video clips together,
handles duration mismatches, applies transitions, syncs audio, and produces
final MP4 video.
"""

from modules.composer.process import process

__all__ = ["process"]

