"""
Style keyword extraction and enforcement utilities.
"""

from __future__ import annotations

import re
from typing import List

from shared.models.scene import Style

DEFAULT_STYLE_FALLBACK = ["cinematic", "high-contrast", "professional"]


def extract_style_keywords(style: Style) -> List[str]:
    """
    Convert Style model into canonical list of keywords.
    """
    keywords: List[str] = []

    def _add(value: str) -> None:
        if not value:
            return
        tokens = re.split(r"[,/]| and | & ", value)
        for token in tokens:
            token = token.strip().lower()
            if token and token not in keywords:
                keywords.append(token)

    _add(style.visual_style)
    _add(style.mood)
    _add(style.lighting)
    _add(style.cinematography)
    for color in style.color_palette:
        normalized = color.replace("#", "").upper()
        if normalized and normalized not in keywords:
            keywords.append(f"#{normalized}")

    if not keywords:
        keywords.extend(DEFAULT_STYLE_FALLBACK)

    return keywords[:10]


def apply_style_keywords(prompt: str, style_keywords: List[str]) -> str:
    """
    Append canonical style keywords near the end of the prompt.
    """
    if not style_keywords:
        return prompt

    keywords = style_keywords[:3]
    phrase = ", ".join(keywords)
    addition = f"in a {phrase} style"
    if addition.lower() in prompt.lower():
        return prompt

    appended = f"{prompt}, {addition}"
    return appended


def ensure_global_consistency(prompts: List[str], style_keywords: List[str]) -> List[str]:
    """
    Ensure each prompt includes at least one of the canonical keywords.
    """
    if not style_keywords:
        return prompts

    result: List[str] = []
    lowered_keywords = [kw.lower() for kw in style_keywords]
    primary = style_keywords[0]

    for prompt in prompts:
        lower_prompt = prompt.lower()
        if any(kw in lower_prompt for kw in lowered_keywords):
            result.append(prompt)
        else:
            result.append(f"{prompt}, {primary} influence")

    return result

