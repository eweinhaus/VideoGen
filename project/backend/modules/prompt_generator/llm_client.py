"""
LLM integration for prompt optimization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import GenerationError, RetryableError, ValidationError
from shared.logging import get_logger
from shared.retry import retry_with_backoff

logger = get_logger("prompt_generator")

_client: Optional[AsyncOpenAI] = None


@dataclass
class LLMResult:
    prompts: List[str]
    model: str
    input_tokens: int
    output_tokens: int


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _calculate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    if model == "gpt-4o":
        return (Decimal(input_tokens) / 1000 * Decimal("0.005")) + (
            Decimal(output_tokens) / 1000 * Decimal("0.015")
        )
    if model == "claude-3-5-sonnet":
        return (Decimal(input_tokens) / 1000 * Decimal("0.003")) + (
            Decimal(output_tokens) / 1000 * Decimal("0.015")
        )
    return (Decimal(input_tokens) / 1000 * Decimal("0.005")) + (
        Decimal(output_tokens) / 1000 * Decimal("0.015")
    )


def _build_system_prompt(style_keywords: List[str]) -> str:
    style_phrase = ", ".join(style_keywords[:5]) if style_keywords else "cinematic"
    return f"""You are an elite text-to-video prompt engineer.

Guidelines:
- Respect clip order and durations exactly as provided.
- Output concise prompts (<200 words) optimized for Stable Video Diffusion and CogVideoX.
- Do not include shot lists or numbered steps.
- Integrate the shared style vocabulary so every prompt feels cohesive.
- Mention action → motion → camera → style → color → lighting → quality modifiers.
- Never include actual URLs; reference images are passed separately.
- Enforce consistent tone using style keywords: {style_phrase}.

Output JSON with the following shape:
{{
  "prompts": [
    {{"clip_index": 0, "prompt": "final optimized prompt"}}
  ]
}}
"""


def _build_user_payload(base_prompts: List[Dict[str, Any]]) -> str:
    instructions = """
Transform each base prompt below into a polished text-to-video prompt.

Requirements:
- Keep the same clip_index order
- Keep durations implicit (do not restate numbers unless stylistically necessary)
- If reference_mode is "text_only" lean on textual detail.
- If characters are present, remind model to keep appearances consistent.
- Inject style keywords naturally.
- No bullet lists, no numbering, no ALL CAPS.
"""
    return instructions + "\n\n" + json.dumps(base_prompts, indent=2)


@retry_with_backoff(max_attempts=3, base_delay=2)
async def optimize_prompts(
    job_id: UUID,
    base_prompts: List[Dict[str, Any]],
    style_keywords: List[str],
) -> LLMResult:
    if not base_prompts:
        raise ValidationError("Base prompts are required for optimization", job_id=job_id)

    model = settings.prompt_generator_llm_model or "gpt-4o"
    if model != "gpt-4o":
        logger.warning(
            "Configured model %s not fully supported yet, falling back to gpt-4o",
            model,
        )
        model = "gpt-4o"

    system_prompt = _build_system_prompt(style_keywords)
    user_payload = _build_user_payload(base_prompts)

    try:
        client = _get_client()
        logger.info(
            "Calling LLM for prompt optimization",
            extra={"job_id": str(job_id), "model": model, "clip_count": len(base_prompts)},
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=3000,
            timeout=90.0,
        )

        content = response.choices[0].message.content
        if not content:
            raise GenerationError("LLM returned empty response", job_id=job_id)

        payload = json.loads(content)
        prompts = payload.get("prompts")
        if not isinstance(prompts, list) or len(prompts) != len(base_prompts):
            raise RetryableError(
                "LLM returned unexpected prompt count",
                job_id=job_id,
            )

        final_prompts = []
        for base, generated in zip(base_prompts, prompts):
            text = generated.get("prompt")
            if not text:
                text = base.get("draft_prompt", "")
            final_prompts.append(text.strip())

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = _calculate_llm_cost(model, input_tokens, output_tokens)

        await cost_tracker.track_cost(
            job_id=job_id,
            stage_name="prompt_generator",
            api_name=model,
            cost=cost,
        )

        logger.info(
            "Prompt optimization completed",
            extra={
                "job_id": str(job_id),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": float(cost),
            },
        )

        return LLMResult(
            prompts=final_prompts,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    except RateLimitError as exc:
        logger.warning("LLM rate limit", extra={"job_id": str(job_id)})
        raise RetryableError(str(exc), job_id=job_id) from exc
    except APITimeoutError as exc:
        logger.warning("LLM timeout", extra={"job_id": str(job_id)})
        raise RetryableError(str(exc), job_id=job_id) from exc
    except APIError as exc:
        logger.error("LLM API error", extra={"job_id": str(job_id), "status": getattr(exc, 'status_code', None)})
        if getattr(exc, "status_code", 500) >= 500:
            raise RetryableError(str(exc), job_id=job_id) from exc
        raise GenerationError(str(exc), job_id=job_id) from exc
    except RetryableError:
        raise
    except ValidationError:
        raise
    except Exception as exc:
        logger.error("Unexpected LLM error", extra={"job_id": str(job_id)}, exc_info=True)
        raise GenerationError(str(exc), job_id=job_id) from exc

