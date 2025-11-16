"""
Time estimation service.

Calculates estimated remaining time for video generation jobs based on
environment, current stage, and job parameters.
"""

from typing import Optional, Dict, Any
from shared.config import settings


# Stage duration defaults by environment (in seconds)
STAGE_DEFAULTS = {
    "development": {
        "audio_parser": {"base": 10, "per_second": 0.1},
        "scene_planner": {"base": 15, "per_second": 0},
        "reference_generator": {"base": 0, "per_image": 8, "concurrency": 4},
        "prompt_generator": {"base": 10, "per_second": 0},
        "video_generator": {"base": 0, "per_clip": 30, "concurrency": 3},
        "composer": {"base": 5, "per_second": 0.5},
    },
    "production": {
        "audio_parser": {"base": 15, "per_second": 0.15},
        "scene_planner": {"base": 20, "per_second": 0},
        "reference_generator": {"base": 0, "per_image": 10, "concurrency": 4},
        "prompt_generator": {"base": 15, "per_second": 0},
        "video_generator": {"base": 0, "per_clip": 45, "concurrency": 5},
        "composer": {"base": 10, "per_second": 0.6},
    },
}


def get_environment_defaults(environment: str) -> Dict[str, Dict[str, Any]]:
    """
    Get stage duration defaults for the given environment.
    
    Args:
        environment: Environment string ("development", "staging", or "production")
        
    Returns:
        Dictionary of stage defaults for the environment
    """
    if environment in ["production", "staging"]:
        return STAGE_DEFAULTS["production"]
    return STAGE_DEFAULTS["development"]


async def calculate_estimated_remaining(
    job_id: str,
    current_stage: str,
    progress: int,
    audio_duration: Optional[float],
    environment: str,
    num_clips: Optional[int] = None,
    num_images: Optional[int] = None,
) -> Optional[int]:
    """
    Calculate estimated remaining time in seconds.
    
    Uses environment-based defaults and scales based on job parameters.
    
    Args:
        job_id: Job ID (for logging/debugging)
        current_stage: Current pipeline stage name
        progress: Current progress percentage (0-100)
        audio_duration: Audio duration in seconds (None if not available)
        environment: Environment string ("development", "staging", or "production")
        num_clips: Number of video clips (for video_generator stage)
        num_images: Number of reference images (for reference_generator stage)
        
    Returns:
        Estimated remaining time in seconds, or None if calculation not possible
    """
    # If audio duration not available, can't calculate accurate estimate
    if audio_duration is None:
        return None
    
    try:
        defaults = get_environment_defaults(environment)
        
        # Stage progress percentages (cumulative)
        # Audio Parser: 1-10% (10% of total)
        # Scene Planner: 12-20% (8% of total)
        # Reference Generator: 25-30% (10% of total)
        # Prompt Generator: 30-40% (10% of total)
        # Video Generator: 50-85% (45% of total)
        # Composer: 85-100% (15% of total)
        
        stage_progress_ranges = {
            "audio_parser": (1, 10),
            "scene_planner": (12, 20),
            "reference_generator": (25, 30),
            "prompt_generator": (30, 40),
            "video_generator": (50, 85),
            "composer": (85, 100),
        }
        
        # Calculate remaining stages
        remaining_stages = []
        current_stage_started = False
        
        for stage_name, (start_progress, end_progress) in stage_progress_ranges.items():
            if stage_name == current_stage:
                current_stage_started = True
                # Calculate remaining time for current stage
                # Clamp progress to stage range
                clamped_progress = max(start_progress, min(progress, end_progress))
                stage_progress_ratio = max(0.0, (end_progress - clamped_progress) / (end_progress - start_progress))
                remaining_stages.append((stage_name, stage_progress_ratio))
            elif current_stage_started:
                # Future stages
                remaining_stages.append((stage_name, 1.0))
        
        # If current stage not found, return None
        if not current_stage_started:
            return None
        
        # Calculate total remaining time
        total_remaining = 0
        
        for stage_name, progress_ratio in remaining_stages:
            stage_defaults = defaults.get(stage_name, {})
            
            if stage_name == "audio_parser":
                # Base + (audio_duration * per_second_rate)
                base = stage_defaults.get("base", 0)
                per_second = stage_defaults.get("per_second", 0)
                stage_time = base + (audio_duration * per_second)
                total_remaining += stage_time * progress_ratio
                
            elif stage_name == "scene_planner":
                # Fixed duration
                base = stage_defaults.get("base", 15)
                total_remaining += base * progress_ratio
                
            elif stage_name == "reference_generator":
                # (per_image * num_images) / concurrency
                if num_images is None:
                    # Default to 4 images (2 scenes + 2 characters)
                    num_images = 4
                per_image = stage_defaults.get("per_image", 8)
                concurrency = stage_defaults.get("concurrency", 4)
                stage_time = (per_image * num_images) / concurrency
                total_remaining += stage_time * progress_ratio
                
            elif stage_name == "prompt_generator":
                # Fixed duration
                base = stage_defaults.get("base", 10)
                total_remaining += base * progress_ratio
                
            elif stage_name == "video_generator":
                # (per_clip * num_clips) / concurrency
                if num_clips is None:
                    # Estimate based on audio duration (assume 6s clips)
                    num_clips = max(3, int(audio_duration / 6))
                per_clip = stage_defaults.get("per_clip", 30)
                concurrency = stage_defaults.get("concurrency", 3)
                stage_time = (per_clip * num_clips) / concurrency
                total_remaining += stage_time * progress_ratio
                
            elif stage_name == "composer":
                # Base + (audio_duration * per_second_rate)
                base = stage_defaults.get("base", 5)
                per_second = stage_defaults.get("per_second", 0.5)
                stage_time = base + (audio_duration * per_second)
                total_remaining += stage_time * progress_ratio
        
        # Round to nearest integer
        return int(round(total_remaining))
        
    except Exception as e:
        # Log error but don't crash - return None to indicate estimate unavailable
        from shared.logging import get_logger
        logger = get_logger(__name__)
        logger.warning(
            "Failed to calculate estimated remaining time",
            exc_info=e,
            extra={"job_id": job_id, "current_stage": current_stage}
        )
        return None

