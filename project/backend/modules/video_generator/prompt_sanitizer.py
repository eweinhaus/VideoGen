"""
Prompt sanitization for content moderation errors.

Sanitizes prompts that trigger content moderation filters by replacing
potentially sensitive words/phrases with safer alternatives.
"""

from typing import Dict, List
from shared.logging import get_logger

logger = get_logger("video_generator.prompt_sanitizer")

# Word/phrase replacements for content moderation
# Maps potentially sensitive terms to safer alternatives
SENSITIVE_WORD_REPLACEMENTS: Dict[str, str] = {
    # "intimate" can trigger false positives in family contexts
    "intimate family moment": "close family moment",
    "intimate family": "close family",
    "intimate moment": "close moment",
    "intimate": "close",
    
    # Other potentially sensitive terms (add as needed)
    "sensual": "warm",
    "provocative": "striking",
}

# Phrases that should be removed entirely (too risky)
PHRASES_TO_REMOVE: List[str] = [
    # Add phrases that consistently trigger filters
]


def sanitize_prompt_for_content_moderation(prompt: str, job_id: str = None) -> str:
    """
    Sanitize a prompt that triggered content moderation filters.
    
    Replaces potentially sensitive words/phrases with safer alternatives.
    This helps avoid false positives from overly strict content filters.
    
    Args:
        prompt: Original prompt that was flagged
        job_id: Job ID for logging
        
    Returns:
        Sanitized prompt with sensitive terms replaced
    """
    sanitized = prompt
    
    # Apply word/phrase replacements
    replacements_made = []
    for sensitive_term, replacement in SENSITIVE_WORD_REPLACEMENTS.items():
        if sensitive_term.lower() in sanitized.lower():
            # Case-insensitive replacement, preserving original case where possible
            import re
            pattern = re.compile(re.escape(sensitive_term), re.IGNORECASE)
            sanitized = pattern.sub(replacement, sanitized)
            replacements_made.append(f"{sensitive_term} -> {replacement}")
    
    # Remove risky phrases entirely
    removed_phrases = []
    for phrase in PHRASES_TO_REMOVE:
        if phrase.lower() in sanitized.lower():
            import re
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            sanitized = pattern.sub("", sanitized)
            removed_phrases.append(phrase)
            # Clean up extra spaces
            sanitized = " ".join(sanitized.split())
    
    if replacements_made or removed_phrases:
        logger.info(
            f"Sanitized prompt for content moderation",
            extra={
                "job_id": job_id,
                "replacements": replacements_made,
                "removed_phrases": removed_phrases,
                "original_length": len(prompt),
                "sanitized_length": len(sanitized)
            }
        )
    else:
        logger.warning(
            f"No sanitization applied - prompt may still trigger filters",
            extra={"job_id": job_id, "prompt_preview": prompt[:200]}
        )
    
    return sanitized

