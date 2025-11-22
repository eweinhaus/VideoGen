"""
LLM integration for prompt optimization.
"""

from __future__ import annotations

import asyncio
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


def _build_system_prompt(style_keywords: List[str], clip_count: int) -> str:
    style_phrase = ", ".join(style_keywords[:5]) if style_keywords else "cinematic"
    return f"""You are an elite text-to-video prompt engineer.

Guidelines:
- Respect clip order and durations exactly as provided.
- Provide detailed, descriptive ACTION and SCENE descriptions (max 500 words per prompt).
- Note: Style and character details will be appended separately after optimization (~200-300 additional words).
- Focus on what's happening in the scene - action, motion, camera work, atmosphere.
- Do not include shot lists or numbered steps.
- Integrate the shared style vocabulary so every prompt feels cohesive.
- Describe action → motion → camera → atmosphere naturally and with detail.
- Never include actual URLs; reference images are passed separately.
- Enforce consistent tone using style keywords: {style_phrase}.
- If character descriptions are present, preserve them EXACTLY as written (do not summarize or modify).
- Be descriptive and specific to give the video model rich detail, but stay within 500 words.

CRITICAL: You MUST return exactly {clip_count} prompts, one for each clip_index from 0 to {clip_count - 1}.
Do not skip any clips. If you cannot generate all prompts, return the base prompts unchanged.
Each prompt should be detailed but not exceed 500 words (style/character blocks will be added later).

Output JSON with the following shape:
{{
  "prompts": [
    {{"clip_index": 0, "prompt": "final optimized prompt"}},
    {{"clip_index": 1, "prompt": "final optimized prompt"}},
    ...
    {{"clip_index": {clip_count - 1}, "prompt": "final optimized prompt"}}
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


async def _optimize_batch(
    job_id: UUID,
    batch_prompts: List[Dict[str, Any]],
    style_keywords: List[str],
    model: str,
) -> Optional[LLMResult]:
    """
    Optimize a single batch of prompts.
    
    Returns LLMResult if successful, None if failed (will use deterministic fallback).
    """
    if not batch_prompts:
        return None
    
    # Retry logic: try up to 2 times, return None on final failure
    # Track if we need to use max tokens due to truncation
    use_max_tokens = False
    
    for attempt in range(2):
        try:
            client = _get_client()
            batch_size = len(batch_prompts)
            first_clip_idx = batch_prompts[0].get("clip_index", 0)
            last_clip_idx = batch_prompts[-1].get("clip_index", batch_size - 1)
            
            logger.info(
                "Processing LLM batch",
                extra={
                    "job_id": str(job_id),
                    "model": model,
                    "batch_size": batch_size,
                    "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                    "attempt": attempt + 1,
                    "using_max_tokens": use_max_tokens,
                },
            )
            
            system_prompt = _build_system_prompt(style_keywords, batch_size)
            user_payload = _build_user_payload(batch_prompts)
            
            # Calculate max_tokens for this batch
            # Each prompt can be up to 500 words (~650 tokens), plus JSON structure overhead
            # For 15 clips: 15 * 650 = 9750 tokens for prompts + ~2000 for JSON = ~12k minimum
            # Use higher estimate to avoid truncation
            if use_max_tokens:
                max_tokens = 16000  # Use maximum on retry after truncation
            else:
                estimated_tokens = max(12000, batch_size * 700 + 2000)
                max_tokens = min(estimated_tokens, 16000)  # Cap at 16k for gpt-4o
            
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=max_tokens,
                timeout=90.0,
            )
            
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            if not content:
                logger.warning(
                    "LLM returned empty response for batch",
                    extra={"job_id": str(job_id), "clip_indices": f"{first_clip_idx}-{last_clip_idx}"},
                )
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                return None
            
            # Check if response was truncated
            if finish_reason == "length":
                logger.warning(
                    "LLM response truncated (hit max_tokens limit)",
                    extra={
                        "job_id": str(job_id),
                        "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                        "max_tokens": max_tokens,
                        "content_length": len(content),
                    },
                )
                # Retry with higher max_tokens if we have attempts left
                if attempt < 1:
                    logger.info(
                        "Retrying batch with higher max_tokens",
                        extra={
                            "job_id": str(job_id),
                            "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                            "old_max_tokens": max_tokens,
                            "new_max_tokens": 16000,
                        },
                    )
                    # Mark to use max tokens on retry
                    use_max_tokens = True
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                # If no retries left, try to parse what we have (will likely fail gracefully)
            
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as json_err:
                # Check if error suggests truncation (unterminated string, unexpected EOF, etc.)
                error_str = str(json_err).lower()
                is_truncation = (
                    finish_reason == "length" or
                    "unterminated" in error_str or
                    "unexpected eof" in error_str or
                    (content and not content.rstrip().endswith("}") and not content.rstrip().endswith("]"))
                )
                
                logger.warning(
                    "Failed to parse LLM JSON response",
                    extra={
                        "job_id": str(job_id),
                        "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                        "error": str(json_err),
                        "finish_reason": finish_reason,
                        "content_length": len(content),
                        "likely_truncation": is_truncation,
                    },
                )
                # If truncated and we have retries, retry with maximum max_tokens
                if is_truncation and attempt < 1:
                    logger.info(
                        "Retrying with maximum max_tokens due to JSON truncation",
                        extra={
                            "job_id": str(job_id),
                            "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                            "old_max_tokens": max_tokens,
                            "finish_reason": finish_reason,
                        },
                    )
                    use_max_tokens = True
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                # Otherwise, retry or fail
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                return None
            prompts = payload.get("prompts")
            
            if not isinstance(prompts, list) or len(prompts) != batch_size:
                logger.warning(
                    "LLM returned invalid batch response",
                    extra={
                        "job_id": str(job_id),
                        "expected_count": batch_size,
                        "actual_count": len(prompts) if isinstance(prompts, list) else 0,
                        "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
                    },
                )
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                return None
            
            # Extract prompts in order, matching clip_index
            final_prompts = []
            prompt_dict = {p.get("clip_index"): p.get("prompt", "") for p in prompts if isinstance(p, dict)}
            
            for base_prompt in batch_prompts:
                clip_idx = base_prompt.get("clip_index")
                text = prompt_dict.get(clip_idx, base_prompt.get("draft_prompt", ""))
                final_prompts.append(text.strip() if text else "")
            
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
                "Batch optimization completed",
                extra={
                    "job_id": str(job_id),
                    "model": model,
                    "batch_size": batch_size,
                    "clip_indices": f"{first_clip_idx}-{last_clip_idx}",
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
        
        except (RateLimitError, APITimeoutError) as exc:
            # Retryable errors - wait and retry if not last attempt
            if attempt < 1:  # 0-indexed, so attempt 0 means 1 more try
                delay = 2 * (attempt + 1)  # 2s, 4s
                logger.warning(
                    "LLM batch retryable error, retrying",
                    extra={
                        "job_id": str(job_id),
                        "error": str(exc),
                        "attempt": attempt + 1,
                        "delay": delay,
                    },
                )
                await asyncio.sleep(delay)
                continue
            else:
                logger.warning(
                    "LLM batch failed after retries, will use deterministic fallback",
                    extra={
                        "job_id": str(job_id),
                        "error": str(exc),
                        "clip_indices": f"{batch_prompts[0].get('clip_index', 0)}-{batch_prompts[-1].get('clip_index', len(batch_prompts)-1)}",
                    },
                )
                return None
        except (APIError, RetryableError, GenerationError) as exc:
            # Non-retryable or final failure
            logger.warning(
                "LLM batch failed, will use deterministic fallback",
                extra={
                    "job_id": str(job_id),
                    "error": str(exc),
                    "clip_indices": f"{batch_prompts[0].get('clip_index', 0)}-{batch_prompts[-1].get('clip_index', len(batch_prompts)-1)}",
                },
            )
            return None
        except Exception as exc:
            logger.error(
                "Unexpected error in batch optimization",
                extra={"job_id": str(job_id), "attempt": attempt + 1},
                exc_info=True,
            )
            if attempt < 1:
                import asyncio
                await asyncio.sleep(2 * (attempt + 1))
                continue
            return None
    
    # If we get here, all attempts failed
    return None


async def optimize_prompts(
    job_id: UUID,
    base_prompts: List[Dict[str, Any]],
    style_keywords: List[str],
) -> LLMResult:
    """
    Optimize prompts using LLM with batching support.
    
    Splits prompts into batches of 15 (configurable) to avoid token limits and timeouts.
    If a batch fails, uses deterministic prompts for that batch only.
    """
    if not base_prompts:
        raise ValidationError("Base prompts are required for optimization", job_id=job_id)

    model = settings.prompt_generator_llm_model or "gpt-4o"
    if model != "gpt-4o":
        logger.warning(
            "Configured model %s not fully supported yet, falling back to gpt-4o",
            model,
        )
        model = "gpt-4o"
    
    batch_size = settings.prompt_generator_batch_size or 15
    total_clips = len(base_prompts)
    
    logger.info(
        "Calling LLM for prompt optimization with batching",
        extra={
            "job_id": str(job_id),
            "model": model,
            "total_clips": total_clips,
            "batch_size": batch_size,
            "num_batches": (total_clips + batch_size - 1) // batch_size,
        },
    )
    
    # Split prompts into batches
    batches = []
    for i in range(0, total_clips, batch_size):
        batches.append(base_prompts[i:i + batch_size])
    
    # Process batches sequentially (to avoid rate limits)
    all_prompts = []
    total_input_tokens = 0
    total_output_tokens = 0
    successful_batches = 0
    failed_batches = 0
    
    for batch_idx, batch in enumerate(batches):
        batch_result = await _optimize_batch(job_id, batch, style_keywords, model)
        
        if batch_result:
            # LLM optimization succeeded for this batch
            all_prompts.extend(batch_result.prompts)
            total_input_tokens += batch_result.input_tokens
            total_output_tokens += batch_result.output_tokens
            successful_batches += 1
        else:
            # LLM failed for this batch, use deterministic prompts
            logger.warning(
                "Using deterministic prompts for failed batch",
                extra={
                    "job_id": str(job_id),
                    "batch_index": batch_idx,
                    "clip_indices": f"{batch[0].get('clip_index', 0)}-{batch[-1].get('clip_index', len(batch)-1)}",
                },
            )
            # Use draft_prompt from base templates as fallback
            for base_prompt in batch:
                fallback_prompt = base_prompt.get("draft_prompt", "")
                all_prompts.append(fallback_prompt.strip() if fallback_prompt else "")
            failed_batches += 1
    
    # Ensure we have the right number of prompts
    if len(all_prompts) != total_clips:
        logger.error(
            "Prompt count mismatch after batching",
            extra={
                "job_id": str(job_id),
                "expected": total_clips,
                "actual": len(all_prompts),
            },
        )
        # Fill missing prompts with deterministic fallbacks
        while len(all_prompts) < total_clips:
            idx = len(all_prompts)
            if idx < len(base_prompts):
                fallback = base_prompts[idx].get("draft_prompt", "")
                all_prompts.append(fallback.strip() if fallback else "")
            else:
                all_prompts.append("")
    
    logger.info(
        "Prompt optimization completed (batched)",
        extra={
            "job_id": str(job_id),
            "model": model,
            "total_clips": total_clips,
            "successful_batches": successful_batches,
            "failed_batches": failed_batches,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
        },
    )
    
    return LLMResult(
        prompts=all_prompts,
        model=model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )

