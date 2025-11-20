"""
Context builder for LLM prompt modification.

Builds rich context for LLM while limiting token usage by summarizing
older conversation history and extracting relevant scene plan information.
"""

from typing import Dict, Any, List, Optional
from shared.models.scene import ScenePlan
from shared.logging import get_logger

logger = get_logger("clip_regenerator.context_builder")


def build_llm_context(
    original_prompt: str,
    scene_plan: ScenePlan,
    user_instruction: str,
    conversation_history: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Build context dictionary for LLM prompt template.
    
    Extracts style info, character names, scene locations, and mood from scene plan.
    Builds conversation context from recent messages.
    
    Args:
        original_prompt: Original video generation prompt
        scene_plan: ScenePlan object with style, characters, scenes, mood
        user_instruction: User's modification instruction
        conversation_history: List of conversation messages
        
    Returns:
        Context dictionary with:
        - original_prompt: Original prompt
        - style_info: Visual style information
        - character_names: List of character names
        - scene_locations: List of scene locations
        - mood: Overall mood
        - user_instruction: User instruction
        - recent_conversation: Formatted conversation text
    """
    # Extract style info
    style_info = "Not specified"
    if scene_plan.style and scene_plan.style.visual_style:
        style_info = scene_plan.style.visual_style
    
    # Extract character names
    character_names = []
    if scene_plan.characters:
        for character in scene_plan.characters:
            if character.name:
                character_names.append(character.name)
            elif character.id:
                # Use ID as fallback
                character_names.append(character.id)
    
    # Extract scene locations from scene descriptions
    # Note: Scene model doesn't have a 'location' field, so we extract from description
    scene_locations = []
    if scene_plan.scenes:
        for scene in scene_plan.scenes:
            # Use description as location info (scenes typically describe location)
            if scene.description:
                scene_locations.append(scene.description)
    
    # Extract mood
    mood = "Not specified"
    if scene_plan.style and scene_plan.style.mood:
        mood = scene_plan.style.mood
    
    # Build conversation context
    recent_conversation = build_conversation_context(conversation_history, max_messages=3)
    
    context = {
        "original_prompt": original_prompt,
        "style_info": style_info,
        "character_names": character_names,
        "scene_locations": scene_locations,
        "mood": mood,
        "user_instruction": user_instruction,
        "recent_conversation": recent_conversation
    }
    
    logger.debug(
        "Built LLM context",
        extra={
            "style_info_length": len(style_info),
            "num_characters": len(character_names),
            "num_scenes": len(scene_locations),
            "conversation_messages": len(conversation_history)
        }
    )
    
    return context


def build_conversation_context(
    conversation_history: List[Dict[str, str]],
    max_messages: int = 3
) -> str:
    """
    Build conversation context for LLM.
    
    Includes only last max_messages, summarizes older if needed.
    
    Args:
        conversation_history: List of conversation messages
        max_messages: Maximum number of recent messages to include
        
    Returns:
        Formatted conversation text string
    """
    if not conversation_history:
        return ""
    
    # Include only last max_messages
    if len(conversation_history) <= max_messages:
        recent = conversation_history
        older = []
    else:
        recent = conversation_history[-max_messages:]
        older = conversation_history[:-max_messages]
    
    # Format recent messages
    conversation_lines = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            conversation_lines.append(f"User: {content}")
        elif role == "assistant":
            conversation_lines.append(f"Assistant: {content}")
    
    # Summarize older messages if needed (future enhancement)
    if older:
        summary = summarize_older_messages(older)
        if summary:
            conversation_lines.insert(0, summary)
    
    return "\n".join(conversation_lines)


def summarize_older_messages(older_messages: List[Dict[str, str]]) -> str:
    """
    Summarize older conversation messages.
    
    Simple summary for now: "Previous requests: made clip brighter, added motion"
    Future enhancement: Could use LLM to generate better summaries.
    
    Args:
        older_messages: List of older conversation messages
        
    Returns:
        Summary string or empty string if no older messages
    """
    if not older_messages:
        return ""
    
    # Extract user instructions from older messages
    user_instructions = []
    for msg in older_messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content:
                # Truncate long instructions
                if len(content) > 50:
                    content = content[:50] + "..."
                user_instructions.append(content)
    
    if user_instructions:
        return f"Previous requests: {', '.join(user_instructions)}"
    
    return ""

