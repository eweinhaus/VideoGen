"""
Director knowledge base loader.

Loads and formats the comprehensive music video director knowledge base
for inclusion in LLM system prompts.
"""

from pathlib import Path
from shared.logging import get_logger

logger = get_logger("scene_planner")


def get_director_knowledge() -> str:
    """
    Load director knowledge base from markdown file.
    
    Returns:
        Formatted director knowledge text for LLM system prompt
        
    Raises:
        FileNotFoundError: If knowledge base file not found
        IOError: If file cannot be read
    """
    # Path to director knowledge markdown file
    # Located in project/backend/data/scene_planner_director_knowledge.md
    # This ensures it's available in production (Railway Root Directory is project/backend)
    
    # Calculate path relative to this file: go up to backend root, then into data/
    # __file__ is at: project/backend/modules/scene_planner/director_knowledge.py
    # Need to go: ../.. to get to project/backend/, then /data/scene_planner_director_knowledge.md
    backend_root = Path(__file__).parent.parent.parent  # project/backend/
    knowledge_path = backend_root / "data" / "scene_planner_director_knowledge.md"
    
    try:
        with open(knowledge_path, "r", encoding="utf-8") as f:
            knowledge_text = f.read()
        
        logger.debug(f"Loaded director knowledge base from {knowledge_path} ({len(knowledge_text)} characters)")
        return knowledge_text
        
    except FileNotFoundError:
        logger.error(f"Director knowledge file not found: {knowledge_path}")
        logger.error(f"Backend root: {backend_root}")
        logger.error(f"Current working directory: {Path.cwd()}")
        raise FileNotFoundError(f"Director knowledge file not found: {knowledge_path}")
    except IOError as e:
        logger.error(f"Failed to read director knowledge file: {str(e)}")
        raise IOError(f"Failed to read director knowledge file: {str(e)}") from e


def extract_relevant_knowledge(
    mood: str,
    energy_level: str,
    bpm: float
) -> str:
    """
    Extract relevant sections from director knowledge based on audio analysis.
    
    This function filters the full knowledge base to include only relevant
    sections based on mood, energy level, and BPM. This helps reduce
    prompt size while maintaining context.
    
    Args:
        mood: Primary mood (e.g., "energetic", "calm", "dark", "bright")
        energy_level: Energy level ("low", "medium", "high")
        bpm: Beats per minute
        
    Returns:
        Filtered director knowledge text
    """
    full_knowledge = get_director_knowledge()
    
    # For now, return full knowledge base
    # Future optimization: Parse markdown and extract relevant sections
    # based on mood/energy/BPM matching
    
    # Determine energy category from BPM and energy_level
    if bpm > 130 or energy_level == "high":
        energy_category = "high"
    elif bpm < 90 or energy_level == "low":
        energy_category = "low"
    else:
        energy_category = "medium"
    
    logger.debug(
        f"Extracting knowledge for mood={mood}, energy={energy_category}, bpm={bpm}",
        extra={"mood": mood, "energy_level": energy_level, "bpm": bpm}
    )
    
    # Return full knowledge for now (comprehensive context is better)
    # The LLM will naturally focus on relevant sections
    return full_knowledge

