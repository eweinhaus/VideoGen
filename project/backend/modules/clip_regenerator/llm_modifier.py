"""
LLM prompt modification for clip regeneration.

Modifies video generation prompts based on user instructions while preserving
style consistency. Uses GPT-4o or Claude 3.5 Sonnet with retry logic.
"""

import re
from typing import Dict, Any, List, Optional
from uuid import UUID
from decimal import Decimal

from openai import AsyncOpenAI
from openai import APIError, RateLimitError, APITimeoutError

from shared.config import settings
from shared.cost_tracking import cost_tracker
from shared.errors import GenerationError, RetryableError
from shared.logging import get_logger
from shared.retry import retry_with_backoff

logger = get_logger("clip_regenerator.llm_modifier")


# Initialize OpenAI client
_openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Get or create OpenAI async client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


def get_system_prompt() -> str:
    """
    Get system prompt for prompt modification.
    
    Returns:
        System prompt string
    """
    return """You are a video editing assistant. Modify video generation prompts based on user instructions while preserving style consistency.

Your task:
1. Understand the user's instruction
2. Modify the original prompt to incorporate the instruction
3. Preserve visual style, character consistency, and scene coherence
4. Keep prompt under 200 words
5. Maintain reference image compatibility

Output only the modified prompt, no explanations."""


def build_user_prompt(
    original_prompt: str,
    user_instruction: str,
    context: Dict[str, Any],
    conversation_history: List[Dict[str, str]]
) -> str:
    """
    Build user prompt template for LLM.
    
    Includes original prompt, scene plan summary, user instruction, and recent conversation.
    
    Args:
        original_prompt: Original video generation prompt
        user_instruction: User's modification instruction
        context: Context dictionary with style_info, character_names, scene_locations, mood
        conversation_history: List of conversation messages (last 2-3 messages)
        
    Returns:
        Formatted user prompt string
    """
    # Build conversation context
    conversation_text = ""
    if conversation_history:
        recent_messages = conversation_history[-3:]  # Last 3 messages only
        conversation_lines = []
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                conversation_lines.append(f"User: {content}")
            elif role == "assistant":
                conversation_lines.append(f"Assistant: {content}")
        conversation_text = "\n".join(conversation_lines)
    
    # Build scene plan summary
    style_info = context.get("style_info", "Not specified")
    character_names = context.get("character_names", [])
    scene_locations = context.get("scene_locations", [])
    mood = context.get("mood", "Not specified")
    
    character_names_str = ", ".join(character_names) if character_names else "None"
    scene_locations_str = ", ".join(scene_locations) if scene_locations else "None"
    
    user_prompt = f"""Original Prompt: {original_prompt}

Scene Plan Summary:
- Style: {style_info}
- Characters: {character_names_str}
- Scenes: {scene_locations_str}
- Overall Mood: {mood}

User Instruction: {user_instruction}"""

    if conversation_text:
        user_prompt += f"""

Recent Conversation (last 3 messages):
{conversation_text}"""

    user_prompt += """

Modify the prompt to incorporate the user's instruction while maintaining consistency."""

    return user_prompt


def parse_llm_prompt_response(response: str) -> str:
    """
    Parse and clean LLM response to extract just the modified prompt.
    
    Handles cases where LLM adds explanations or markdown formatting despite instructions.
    
    Args:
        response: Raw LLM response string
        
    Returns:
        Cleaned prompt string
    """
    response = response.strip()
    
    # Remove markdown code blocks if present
    if response.startswith("```"):
        lines = response.split("\n")
        # Remove first line (```) and last line (```)
        if len(lines) > 2:
            response = "\n".join(lines[1:-1]).strip()
        elif len(lines) == 2:
            # Single line in code block
            response = lines[0].replace("```", "").strip()
    
    # Remove common prefixes LLM might add
    prefixes_to_remove = [
        "Modified prompt:",
        "Here's the modified prompt:",
        "The modified prompt is:",
        "Prompt:",
        "Modified:",
    ]
    for prefix in prefixes_to_remove:
        if response.lower().startswith(prefix.lower()):
            response = response[len(prefix):].strip()
            # Remove colon if present
            if response.startswith(":"):
                response = response[1:].strip()
    
    # If response contains explanation (e.g., "The prompt is: ... because...")
    # Try to extract just the prompt part
    if "because" in response.lower() or "this" in response.lower():
        # Look for the longest sentence/paragraph (likely the prompt)
        sentences = re.split(r'[.!?]\s+', response)
        if len(sentences) > 1:
            # Take the longest sentence as the prompt
            longest = max(sentences, key=len)
            if len(longest) > 50:  # Reasonable prompt length
                response = longest.strip()
    
    # Fallback: Return full response if parsing fails
    # Better to have a prompt with extra text than no prompt
    return response.strip()


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    
    Simple estimation: ~4 characters per token (rough approximation).
    For more accurate counting, would need tiktoken library.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated token count
    """
    # Rough estimation: 4 characters per token
    return len(text) // 4


def _truncate_context_if_needed(
    context: Dict[str, Any],
    max_tokens: int = 2000
) -> Dict[str, Any]:
    """
    Truncate context if it exceeds token budget.
    
    Priority: style > characters > scenes
    
    Args:
        context: Context dictionary
        max_tokens: Maximum token budget
        
    Returns:
        Truncated context dictionary
    """
    # Estimate current token usage
    style_info = context.get("style_info", "")
    character_names = context.get("character_names", [])
    scene_locations = context.get("scene_locations", [])
    
    current_tokens = (
        _estimate_tokens(style_info) +
        _estimate_tokens(", ".join(character_names)) +
        _estimate_tokens(", ".join(scene_locations))
    )
    
    # If within budget, return as-is
    if current_tokens <= max_tokens:
        return context
    
    # Truncate in priority order: scenes first (lowest priority)
    truncated_context = context.copy()
    
    # Truncate scene locations if needed
    if current_tokens > max_tokens and scene_locations:
        # Keep only first 2 scenes
        truncated_context["scene_locations"] = scene_locations[:2]
        current_tokens = (
            _estimate_tokens(style_info) +
            _estimate_tokens(", ".join(character_names)) +
            _estimate_tokens(", ".join(truncated_context["scene_locations"]))
        )
    
    # Truncate character names if still needed
    if current_tokens > max_tokens and character_names:
        # Keep only first 3 characters
        truncated_context["character_names"] = character_names[:3]
        current_tokens = (
            _estimate_tokens(style_info) +
            _estimate_tokens(", ".join(truncated_context["character_names"])) +
            _estimate_tokens(", ".join(truncated_context.get("scene_locations", [])))
        )
    
    # Truncate style info if still needed (last resort)
    if current_tokens > max_tokens and style_info:
        # Truncate to first 200 characters
        truncated_context["style_info"] = style_info[:200]
    
    return truncated_context


@retry_with_backoff(max_attempts=3, base_delay=2)
async def modify_prompt_with_llm(
    original_prompt: str,
    user_instruction: str,
    context: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    job_id: Optional[UUID] = None
) -> str:
    """
    Modify prompt using LLM.
    
    Uses GPT-4o to modify the original prompt based on user instruction
    while preserving style consistency.
    
    Args:
        original_prompt: Original video generation prompt
        user_instruction: User's modification instruction
        context: Context dictionary with style_info, character_names, scene_locations, mood
        conversation_history: List of conversation messages (last 2-3 messages)
        job_id: Optional job ID for cost tracking
        
    Returns:
        Modified prompt string
        
    Raises:
        GenerationError: If LLM call fails after retries
        RetryableError: If transient error occurs (will be retried)
    """
    model = "gpt-4o"  # Preferred model
    
    try:
        # Truncate context if needed to stay within token budget
        truncated_context = _truncate_context_if_needed(context, max_tokens=2000)
        
        # Build prompts
        system_prompt = get_system_prompt()
        user_prompt = build_user_prompt(
            original_prompt,
            user_instruction,
            truncated_context,
            conversation_history[-3:]  # Last 3 messages only
        )
        
        # Estimate token usage
        estimated_input_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt)
        if estimated_input_tokens > 2000:
            logger.warning(
                f"Estimated input tokens ({estimated_input_tokens}) exceeds budget (2000)",
                extra={
                    "job_id": str(job_id) if job_id else None,
                    "estimated_tokens": estimated_input_tokens
                }
            )
        
        logger.info(
            f"Calling LLM for prompt modification",
            extra={
                "job_id": str(job_id) if job_id else None,
                "model": model,
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
                "estimated_input_tokens": estimated_input_tokens
            }
        )
        
        # Call OpenAI API
        client = get_openai_client()
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=300,  # Output only (prompt should be under 200 words)
            timeout=30.0
        )
        
        # Extract response
        content = response.choices[0].message.content
        if not content:
            raise GenerationError("Empty response from LLM", job_id=job_id)
        
        # Parse and clean response
        modified_prompt = parse_llm_prompt_response(content)
        
        # Track cost
        if job_id:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = _calculate_llm_cost(model, input_tokens, output_tokens)
            
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="clip_regeneration",
                api_name=model,
                cost=cost,
                metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "operation": "prompt_modification"
                }
            )
        
        logger.info(
            f"Successfully modified prompt via LLM",
            extra={
                "job_id": str(job_id) if job_id else None,
                "original_length": len(original_prompt),
                "modified_length": len(modified_prompt)
            }
        )
        
        return modified_prompt
        
    except RateLimitError as e:
        logger.warning(f"Rate limit error in LLM call: {e}", extra={"job_id": str(job_id) if job_id else None})
        raise RetryableError(f"Rate limit error: {str(e)}", job_id=job_id) from e
    except APITimeoutError as e:
        logger.warning(f"Timeout error in LLM call: {e}", extra={"job_id": str(job_id) if job_id else None})
        raise RetryableError(f"Timeout error: {str(e)}", job_id=job_id) from e
    except APIError as e:
        logger.error(f"API error in LLM call: {e}", extra={"job_id": str(job_id) if job_id else None}, exc_info=True)
        raise RetryableError(f"API error: {str(e)}", job_id=job_id) from e
    except Exception as e:
        logger.error(f"Unexpected error in LLM call: {e}", extra={"job_id": str(job_id) if job_id else None}, exc_info=True)
        raise GenerationError(f"LLM call failed: {str(e)}", job_id=job_id) from e


def _calculate_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int
) -> Decimal:
    """
    Calculate LLM API cost based on token usage.
    
    Args:
        model: Model name ("gpt-4o")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Cost in USD
    """
    # Pricing as of 2024
    if model == "gpt-4o":
        # GPT-4o: $0.005 per 1K input tokens, $0.015 per 1K output tokens
        input_cost = Decimal(input_tokens) / 1000 * Decimal("0.005")
        output_cost = Decimal(output_tokens) / 1000 * Decimal("0.015")
        return input_cost + output_cost
    else:
        logger.warning(f"Unknown model {model}, using GPT-4o pricing")
        input_cost = Decimal(input_tokens) / 1000 * Decimal("0.005")
        output_cost = Decimal(output_tokens) / 1000 * Decimal("0.015")
        return input_cost + output_cost


def estimate_llm_cost() -> Decimal:
    """
    Estimate LLM cost for prompt modification.
    
    Returns:
        Estimated cost in USD
    """
    # Rough estimate: ~500 input tokens, ~200 output tokens
    return _calculate_llm_cost("gpt-4o", 500, 200)

