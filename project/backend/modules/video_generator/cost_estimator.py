"""
Cost estimation for video generation.

Simple formula: base_cost + (duration * per_second_rate)
"""
from decimal import Decimal
from typing import TYPE_CHECKING
from modules.video_generator.config import COST_PER_CLIP

if TYPE_CHECKING:
    from shared.models.video import ClipPrompts


def estimate_clip_cost(duration: float, environment: str) -> Decimal:
    """
    Estimate cost for single clip.
    
    Args:
        duration: Clip duration in seconds
        environment: "production" or "development"
        
    Returns:
        Estimated cost as Decimal
        
    Raises:
        ValueError: If environment is invalid
    """
    if environment not in COST_PER_CLIP:
        raise ValueError(f"Invalid environment: {environment}")
    
    costs = COST_PER_CLIP[environment]
    return costs["base_cost"] + (costs["per_second"] * Decimal(str(duration)))


def estimate_total_cost(clip_prompts: "ClipPrompts", environment: str) -> Decimal:
    """
    Estimate total cost for all clips.
    
    Args:
        clip_prompts: ClipPrompts model with list of clip prompts
        environment: "production" or "development"
        
    Returns:
        Total estimated cost as Decimal
    """
    total = Decimal("0.00")
    for cp in clip_prompts.clip_prompts:
        total += estimate_clip_cost(cp.duration, environment)
    return total

