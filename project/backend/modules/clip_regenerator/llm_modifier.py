"""
LLM prompt modification for clip regeneration.

Modifies video generation prompts based on user instructions while preserving
style consistency. Uses GPT-4o or Claude 3.5 Sonnet with retry logic.
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
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
1. Understand the user's instruction and determine the level of change requested
2. Modify the original prompt to incorporate the instruction
3. Determine appropriate temperature (0.0-1.0) based on the instruction:
   - Very low temperature (0.2-0.3): For "almost exactly the same" requests with minor fixes (e.g., "regenerate almost exactly the same, avoid weird right arm", "keep everything identical except fix X", "same scene just fix Y", "almost identical but correct Z")
   - Low temperature (0.3-0.4): For precise, minimal changes (e.g., "keep scene same, change hair color", "keep everything the same but...", "only change...")
   - Medium-low temperature (0.4-0.5): For small but noticeable changes (e.g., "slightly adjust lighting", "make it a bit brighter")
   - Medium temperature (0.6-0.7): For moderate changes (e.g., "change lighting and add motion", "make it brighter", "adjust the mood")
   - High temperature (0.8-1.0): For complete regeneration (e.g., "completely regenerate", "start over", "completely change", "redo this scene")
4. Preserve visual style, character consistency, and scene coherence
5. Keep prompt under 200 words
6. Maintain reference image compatibility

IMPORTANT: When user says "almost exactly the same", "almost identical", "keep everything the same", or similar phrases indicating minimal change, use temperature 0.2-0.3 to maximize consistency.

Output JSON format:
{
  "prompt": "modified prompt text",
  "temperature": 0.3,
  "reasoning": "brief explanation of temperature choice"
}

The temperature controls randomness in video generation:
- Lower temperature = more deterministic, preserves original scene better
- Higher temperature = more creative variation, allows larger changes"""


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


def refine_temperature_for_minimal_change(
    user_instruction: str,
    llm_temperature: float,
    llm_reasoning: str
) -> Tuple[float, str]:
    """
    Refine temperature downward if user instruction indicates "almost exactly the same".
    
    This provides a safety net to ensure very low temperatures (0.2-0.3) are used
    when user explicitly requests minimal changes, even if LLM chose a slightly higher value.
    
    Args:
        user_instruction: User's modification instruction
        llm_temperature: Temperature chosen by LLM
        llm_reasoning: LLM's reasoning for temperature choice
        
    Returns:
        Tuple of (refined_temperature, updated_reasoning)
    """
    # Phrases that indicate "almost exactly the same" - should use 0.2-0.3
    minimal_change_phrases = [
        "almost exactly the same",
        "almost identical",
        "keep everything the same",
        "keep everything identical",
        "same scene just",
        "same but fix",
        "same except",
        "identical except",
        "almost the same",
        "nearly identical",
        "regenerate almost exactly",
        "almost exactly",
    ]
    
    instruction_lower = user_instruction.lower()
    
    # Check if instruction contains minimal change phrases
    has_minimal_change_phrase = any(
        phrase in instruction_lower for phrase in minimal_change_phrases
    )
    
    # If LLM chose 0.4 or higher but instruction indicates minimal change, refine downward
    if has_minimal_change_phrase and llm_temperature >= 0.35:
        refined_temperature = min(0.3, llm_temperature - 0.1)  # Reduce by 0.1, cap at 0.3
        refined_temperature = max(0.2, refined_temperature)  # Ensure at least 0.2
        
        updated_reasoning = (
            f"{llm_reasoning} [Refined: Detected 'almost exactly the same' phrase, "
            f"adjusted temperature from {llm_temperature:.2f} to {refined_temperature:.2f} for maximum consistency]"
        )
        
        logger.info(
            f"Refined temperature for minimal change request",
            extra={
                "original_temperature": llm_temperature,
                "refined_temperature": refined_temperature,
                "instruction_preview": user_instruction[:100]
            }
        )
        
        return refined_temperature, updated_reasoning
    
    # No refinement needed
    return llm_temperature, llm_reasoning


@retry_with_backoff(max_attempts=3, base_delay=2)
async def modify_prompt_with_llm(
    original_prompt: str,
    user_instruction: str,
    context: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    job_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Modify prompt using LLM.
    
    Uses GPT-4o to modify the original prompt based on user instruction
    while preserving style consistency. Also determines appropriate temperature
    for video generation based on the level of change requested.
    
    Args:
        original_prompt: Original video generation prompt
        user_instruction: User's modification instruction
        context: Context dictionary with style_info, character_names, scene_locations, mood
        conversation_history: List of conversation messages (last 2-3 messages)
        job_id: Optional job ID for cost tracking
        
    Returns:
        Dictionary with keys:
        - "prompt": Modified prompt string
        - "temperature": Float between 0.0 and 1.0
        - "reasoning": Brief explanation of temperature choice
        
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
            max_tokens=400,  # Increased for JSON response with reasoning
            response_format={"type": "json_object"},  # Force JSON output
            timeout=30.0
        )
        
        # Extract response
        content = response.choices[0].message.content
        if not content:
            raise GenerationError("Empty response from LLM", job_id=job_id)
        
        # Parse JSON response
        try:
            result = json.loads(content)
            modified_prompt = result.get("prompt", "").strip()
            temperature = result.get("temperature", 0.7)  # Default to 0.7 if missing
            reasoning = result.get("reasoning", "")
            
            # Validate and clamp temperature to valid range
            try:
                temperature = float(temperature)
                temperature = max(0.0, min(1.0, temperature))  # Clamp to 0.0-1.0
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid temperature value '{temperature}', using default 0.7",
                    extra={"job_id": str(job_id) if job_id else None}
                )
                temperature = 0.7
            
            # If prompt is empty, try to extract from text fallback
            if not modified_prompt:
                logger.warning(
                    f"Empty prompt in JSON response, attempting text parsing fallback",
                    extra={"job_id": str(job_id) if job_id else None}
                )
                modified_prompt = parse_llm_prompt_response(content)
            
            logger.info(
                f"Successfully parsed JSON response from LLM",
                extra={
                    "job_id": str(job_id) if job_id else None,
                    "temperature": temperature,
                    "reasoning": reasoning[:100] if reasoning else "",  # Truncate for logging
                    "instruction_type": (
                        "precise" if temperature < 0.5 
                        else "moderate" if temperature < 0.8 
                        else "complete_regeneration"
                    )
                }
            )
            
            # Refine temperature if user instruction indicates "almost exactly the same"
            temperature, reasoning = refine_temperature_for_minimal_change(
                user_instruction,
                temperature,
                reasoning
            )
            
        except json.JSONDecodeError as e:
            # Fallback: Try to extract prompt from text response
            logger.warning(
                f"Failed to parse JSON response, falling back to text parsing: {e}",
                extra={"job_id": str(job_id) if job_id else None, "response_preview": content[:200]}
            )
            modified_prompt = parse_llm_prompt_response(content)
            temperature = 0.7  # Default fallback temperature
            reasoning = "JSON parsing failed, using default temperature"
            
            # Still refine temperature if user instruction indicates minimal change
            temperature, reasoning = refine_temperature_for_minimal_change(
                user_instruction,
                temperature,
                reasoning
            )
        
        # Track cost
        if job_id:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = _calculate_llm_cost(model, input_tokens, output_tokens)
            
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="clip_regeneration",
                api_name=model,
                cost=cost
            )
        
        logger.info(
            f"Successfully modified prompt via LLM",
            extra={
                "job_id": str(job_id) if job_id else None,
                "original_length": len(original_prompt),
                "modified_length": len(modified_prompt),
                "temperature": temperature,
                "has_reasoning": bool(reasoning)
            }
        )
        
        return {
            "prompt": modified_prompt,
            "temperature": temperature,
            "reasoning": reasoning
        }
        
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

