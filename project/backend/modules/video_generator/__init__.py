"""
Video Generator module.

Part 1: Foundation components (config, cost_estimator, image_handler)
Part 2: Generator (Replicate API integration)
Part 3: Process (parallel orchestration)
"""

from modules.video_generator.process import process

__all__ = ["process"]

