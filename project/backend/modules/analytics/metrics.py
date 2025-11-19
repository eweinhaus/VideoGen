"""
Analytics metric calculation functions.

Part 6: Comparison Tools & Analytics
"""
from typing import List, Dict
from decimal import Decimal
from collections import Counter

from shared.logging import get_logger

logger = get_logger("analytics.metrics")


def calculate_job_metrics(analytics_records: List[Dict]) -> Dict:
    """
    Calculate metrics for a job from analytics records.
    
    Args:
        analytics_records: List of regeneration analytics records
        
    Returns:
        Dict with metrics: total_regenerations, success_rate, average_cost,
        most_common_modifications, average_time_seconds
    """
    if not analytics_records:
        return {
            "total_regenerations": 0,
            "success_rate": 0.0,
            "average_cost": 0.0,
            "most_common_modifications": [],
            "average_time_seconds": None
        }
    
    total = len(analytics_records)
    success_count = sum(1 for r in analytics_records if r.get("success", False))
    success_rate = success_count / total if total > 0 else 0.0
    
    # Calculate average cost
    total_cost = sum(
        Decimal(str(r.get("cost", 0))) if r.get("cost") else Decimal(0)
        for r in analytics_records
    )
    average_cost = float(total_cost / total) if total > 0 else 0.0
    
    # Calculate most common modifications (top 5)
    instructions = [r.get("instruction", "") for r in analytics_records if r.get("instruction")]
    instruction_counts = Counter(instructions)
    most_common = [
        {"instruction": inst, "count": count}
        for inst, count in instruction_counts.most_common(5)
    ]
    
    # Average time not available in current schema (would need created_at differences)
    # Can be calculated from timestamps if needed
    
    return {
        "total_regenerations": total,
        "success_rate": success_rate,
        "average_cost": average_cost,
        "most_common_modifications": most_common,
        "average_time_seconds": None  # Not available in current schema
    }


def calculate_user_metrics(analytics_records: List[Dict]) -> Dict:
    """
    Calculate metrics for a user from analytics records.
    
    Args:
        analytics_records: List of regeneration analytics records across all jobs
        
    Returns:
        Dict with metrics: total_regenerations, most_used_templates, success_rate,
        total_cost, average_cost_per_regeneration, average_iterations_per_clip
    """
    if not analytics_records:
        return {
            "total_regenerations": 0,
            "most_used_templates": [],
            "success_rate": 0.0,
            "total_cost": 0.0,
            "average_cost_per_regeneration": 0.0,
            "average_iterations_per_clip": 0.0
        }
    
    total = len(analytics_records)
    success_count = sum(1 for r in analytics_records if r.get("success", False))
    success_rate = success_count / total if total > 0 else 0.0
    
    # Calculate total cost
    total_cost = sum(
        Decimal(str(r.get("cost", 0))) if r.get("cost") else Decimal(0)
        for r in analytics_records
    )
    average_cost_per_regeneration = float(total_cost / total) if total > 0 else 0.0
    
    # Calculate most used templates (top 5)
    templates = [
        r.get("template_id") for r in analytics_records
        if r.get("template_id")  # Only count template matches
    ]
    template_counts = Counter(templates)
    most_used_templates = [
        {"template_id": template_id, "count": count}
        for template_id, count in template_counts.most_common(5)
    ]
    
    # Calculate average iterations per clip
    # Group by (job_id, clip_index) and count regenerations per clip
    clip_regenerations = {}
    for r in analytics_records:
        key = (r.get("job_id"), r.get("clip_index"))
        clip_regenerations[key] = clip_regenerations.get(key, 0) + 1
    
    if clip_regenerations:
        average_iterations = sum(clip_regenerations.values()) / len(clip_regenerations)
    else:
        average_iterations = 0.0
    
    return {
        "total_regenerations": total,
        "most_used_templates": most_used_templates,
        "success_rate": success_rate,
        "total_cost": float(total_cost),
        "average_cost_per_regeneration": average_cost_per_regeneration,
        "average_iterations_per_clip": average_iterations
    }

