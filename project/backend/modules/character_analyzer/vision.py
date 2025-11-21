"""
Vision integration for character analysis.

Implements mock mode now; real GPT-4V integration stubbed for Phase 1.2.
"""

import os
from typing import Any, Dict, Optional
from uuid import UUID

from .config import is_character_analysis_mock_enabled
from .models import CharacterAnalysis
from .normalizer import (
    normalize_age_range,
    normalize_gender_presentation,
    normalize_hair_color,
    normalize_hair_style,
    normalize_eye_color,
    normalize_skin_tone,
    normalize_build,
    normalize_height_bucket,
    normalize_style,
    bin_overall_confidence,
)
from shared.retry import retry_with_backoff
from shared.cost_tracking import cost_tracker  # type: ignore
from shared.logging import get_logger  # type: ignore
from .cache import get_cached_analysis, store_cached_analysis
import httpx
import hashlib
import json
from decimal import Decimal
from openai import AsyncOpenAI

logger = get_logger(__name__)


MOCK_ANALYSIS: Dict[str, Any] = {
    "age_range": "mid_20s",
    "gender_presentation": "masculine",
    "hair_color": "dark_brown",
    "hair_style": "short_wavy",
    "eye_color": "blue",
    "build": "athletic",
    "height_bucket": "tall",
    "skin_tone": "fair",
    "style": "photo_realistic",
    "distinctive_features": ["scar_left_cheek"],
    "clothing": ["hoodie", "jeans"],
    "confidence": 0.82,
    "confidence_binned": "high",
    "confidence_per_attribute": {"hair_color": 0.9, "eye_color": 0.88},
    "analysis_version": "v1",
}


@retry_with_backoff(max_attempts=3, base_delay=2)
async def _call_gpt4v(image_url: str) -> Dict[str, Any]:
    """
    Call OpenAI GPT-4V to extract character features.
    
    Returns:
        Parsed JSON with raw attributes
    """
    client = AsyncOpenAI()  # uses OPENAI_API_KEY from env
    system_prompt = (
        "You analyze a single person image and return JSON of visual attributes.\n"
        "Return ONLY valid JSON. Do not include explanations.\n"
        "Use these keys: age_range, gender_presentation, hair_color, hair_style, eye_color, build, "
        "height_bucket, skin_tone, style, distinctive_features (array of tokens), clothing (array of tokens)."
    )
    user_instructions = (
        "Analyze this image and output JSON with the keys specified. "
        "Use short, normalized phrases where possible. "
        "If uncertain, choose your best guess; avoid 'unspecified'."
    )
    # Vision message with image_url
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_instructions},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]
    # Use a vision-capable model
    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # vision-capable, cost-effective
        messages=messages,
        temperature=0.2,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to repair trivial issues
        content = content.strip().strip("`")
        try:
            return json.loads(content)
        except Exception:
            return {}


async def analyze_character_image(
    image_url: str,
    job_id: UUID,
    user_id: Optional[str] = None,
    use_mock: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Analyze a character image and return a normalized analysis dict.
    
    Returns a dict suitable for constructing CharacterAnalysis and API response.
    """
    if use_mock is None:
        use_mock = is_character_analysis_mock_enabled()
    if use_mock:
        return {"analysis": MOCK_ANALYSIS, "warnings": [], "used_cache": False}

    # Attempt to download image and compute hash for caching
    image_hash: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            data = resp.content
            image_hash = hashlib.sha256(data).hexdigest()
    except Exception:
        image_hash = None

    # Try cache by image hash
    if image_hash:
        cached = await get_cached_analysis(image_hash)
        if cached:
            return cached

    # Call GPT-4V to get raw features
    raw = await _call_gpt4v(image_url)
    # Map provider keys to our expected fields with safe defaults
    raw_age = raw.get("age_range") or ""
    raw_gender = raw.get("gender_presentation") or raw.get("gender") or ""
    raw_hair_color = raw.get("hair_color") or ""
    raw_hair_style = raw.get("hair_style") or ""
    raw_eye_color = raw.get("eye_color") or ""
    raw_build = raw.get("build") or ""
    raw_height = raw.get("height_bucket") or raw.get("height") or ""
    raw_skin = raw.get("skin_tone") or ""
    raw_style = raw.get("style") or ""

    age, c_age = normalize_age_range(raw_age)
    gender, c_gender = normalize_gender_presentation(raw_gender)
    hair_color, c_hair_color = normalize_hair_color(raw_hair_color)
    hair_style, c_hair_style = normalize_hair_style(raw_hair_style)
    eye_color, c_eye = normalize_eye_color(raw_eye_color)
    skin, c_skin = normalize_skin_tone(raw_skin)
    build, c_build = normalize_build(raw_build)
    height, c_height = normalize_height_bucket(raw_height)
    style, c_style = normalize_style(raw_style)

    per_attr = {
        "age_range": c_age,
        "gender_presentation": c_gender,
        "hair_color": c_hair_color,
        "hair_style": c_hair_style,
        "eye_color": c_eye,
        "skin_tone": c_skin,
        "build": c_build,
        "height_bucket": c_height,
        "style": c_style,
    }

    analysis = CharacterAnalysis(
        age_range=age,
        gender_presentation=gender,
        hair_color=hair_color,
        hair_style=hair_style,
        eye_color=eye_color,
        build=build,
        height_bucket=height,
        skin_tone=skin,
        style=style,
        distinctive_features=list(raw.get("distinctive_features", [])) if isinstance(raw.get("distinctive_features"), list) else [],
        clothing=list(raw.get("clothing", [])) if isinstance(raw.get("clothing"), list) else None,
        confidence=sum(per_attr.values()) / len(per_attr),
        confidence_binned=bin_overall_confidence(per_attr),
        confidence_per_attribute=per_attr,
        analysis_version="v1",
    )

    result = {
        "analysis": analysis.model_dump(),
        "warnings": [],
        "used_cache": False,
    }
    # Track analysis cost (approximate per PRD)
    try:
        await cost_tracker.track_cost(
            job_id=job_id,
            stage_name="character_analysis",
            api_name="gpt-4v",
            cost=Decimal("0.01"),
        )
    except Exception:
        pass
    # Store in DB cache if possible
    try:
        if user_id and image_hash:
            await store_cached_analysis(
                user_id=user_id,
                image_url=image_url,
                image_hash=image_hash,
                normalized_analysis=result["analysis"],
                raw_provider_output={},  # redacted
                provider="openai_gpt4v",
            )
    except Exception:
        pass

    return result


