"""
Template matching system for common clip modifications.

Matches user instructions to predefined template transformations,
skipping LLM calls for faster, cheaper regeneration.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from shared.logging import get_logger

logger = get_logger("clip_regenerator.template_matcher")


@dataclass
class TemplateMatch:
    """Template match result."""
    
    template_id: str
    transformation: str
    cost_savings: float


# Template definitions for common modifications
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "brighter": {
        "keywords": ["brighter", "brighten", "more light", "lighter"],
        "transformation": "bright lighting, well-lit, high exposure",
        "cost_savings": 0.01  # Skip LLM call
    },
    "darker": {
        "keywords": ["darker", "darken", "less light", "dimmer"],
        "transformation": "dark lighting, low exposure, shadowy",
        "cost_savings": 0.01
    },
    "nighttime": {
        "keywords": ["nighttime", "night", "dark sky", "stars"],
        "transformation": "nighttime scene, dark sky, stars visible, night lighting, cool tones",
        "cost_savings": 0.01
    },
    "daytime": {
        "keywords": ["daytime", "day", "bright sky", "sunny"],
        "transformation": "daytime scene, bright sky, natural daylight, warm tones",
        "cost_savings": 0.01
    },
    "more_motion": {
        "keywords": ["more motion", "add motion", "dynamic", "movement"],
        "transformation": "dynamic camera movement, motion blur, fast-paced action",
        "cost_savings": 0.01
    },
    "less_motion": {
        "keywords": ["less motion", "calm", "still", "static"],
        "transformation": "static camera, minimal movement, calm composition",
        "cost_savings": 0.01
    }
}


def match_template(instruction: str) -> Optional[TemplateMatch]:
    """
    Match user instruction to template.
    
    Uses first match wins strategy - templates checked in order defined in TEMPLATES dict.
    All matches are logged for future analysis and template expansion.
    
    Args:
        instruction: User instruction string
        
    Returns:
        TemplateMatch if found, None otherwise
        
    Example:
        >>> match = match_template("make it nighttime")
        >>> match.template_id
        'nighttime'
        >>> match.transformation
        'nighttime scene, dark sky, stars visible, night lighting, cool tones'
    """
    if not instruction or not instruction.strip():
        return None
    
    instruction_lower = instruction.lower().strip()
    matches = []  # Track all matches for logging
    
    # Check templates in order (first match wins)
    for template_id, template in TEMPLATES.items():
        for keyword in template["keywords"]:
            # Check if keyword appears in instruction
            # For multi-word keywords, check exact phrase match
            if " " in keyword:
                # Multi-word keyword: check if phrase appears in instruction
                if keyword in instruction_lower:
                    match = TemplateMatch(
                        template_id=template_id,
                        transformation=template["transformation"],
                        cost_savings=template["cost_savings"]
                    )
                    matches.append(match)
                    # First match wins
                    logger.info(
                        f"Template matched: {template_id}",
                        extra={
                            "instruction": instruction,
                            "template_id": template_id,
                            "keyword": keyword,
                            "all_matches": [m.template_id for m in matches]
                        }
                    )
                    return match
            else:
                # Single-word keyword: check if word appears in instruction
                if keyword in instruction_lower:
                    match = TemplateMatch(
                        template_id=template_id,
                        transformation=template["transformation"],
                        cost_savings=template["cost_savings"]
                    )
                    matches.append(match)
                    # First match wins
                    logger.info(
                        f"Template matched: {template_id}",
                        extra={
                            "instruction": instruction,
                            "template_id": template_id,
                            "keyword": keyword,
                            "all_matches": [m.template_id for m in matches]
                        }
                    )
                    return match
    
    # No match found
    if not matches:
        logger.debug(
            f"No template match found for instruction",
            extra={"instruction": instruction}
        )
    
    return None


def apply_template(original_prompt: str, template: TemplateMatch) -> str:
    """
    Apply template transformation to prompt.
    
    Appends the transformation to the original prompt with proper formatting.
    
    Args:
        original_prompt: Original video generation prompt
        template: TemplateMatch object with transformation
        
    Returns:
        Modified prompt with transformation appended
        
    Example:
        >>> original = "A cyberpunk street scene"
        >>> template = TemplateMatch("nighttime", "nighttime scene, dark sky, stars visible, night lighting, cool tones", 0.01)
        >>> apply_template(original, template)
        'A cyberpunk street scene, nighttime scene, dark sky, stars visible, night lighting, cool tones'
    """
    if not original_prompt:
        return template.transformation
    
    # Append transformation with comma separator
    modified_prompt = f"{original_prompt}, {template.transformation}"
    
    logger.debug(
        "Template applied to prompt",
        extra={
            "template_id": template.template_id,
            "original_length": len(original_prompt),
            "modified_length": len(modified_prompt)
        }
    )
    
    return modified_prompt

