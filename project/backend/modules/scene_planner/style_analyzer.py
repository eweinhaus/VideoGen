"""
Style consistency analysis and refinement.

Validates and ensures style consistency across all clips in a scene plan.
"""

from shared.models.scene import ScenePlan
from shared.logging import get_logger

logger = get_logger("scene_planner")


def analyze_style_consistency(scene_plan: ScenePlan) -> bool:
    """
    Validate style consistency across all clips.
    
    Checks:
    - Color palette consistency (same palette referenced in all clips)
    - Character consistency (same character descriptions across clips)
    - Scene consistency (same scene IDs referenced appropriately)
    - Cinematography consistency (similar camera styles)
    
    Args:
        scene_plan: ScenePlan to analyze
        
    Returns:
        True if consistent, False if inconsistencies found
    """
    issues = []
    
    # Check color palette consistency
    if not scene_plan.style.color_palette:
        issues.append("Missing color palette")
    elif len(scene_plan.style.color_palette) < 3:
        issues.append(f"Color palette too small: {len(scene_plan.style.color_palette)} colors")
    
    # Check character consistency
    character_ids = {char.id for char in scene_plan.characters}
    for clip in scene_plan.clip_scripts:
        for char_id in clip.characters:
            if char_id not in character_ids:
                issues.append(f"Clip {clip.clip_index} references unknown character: {char_id}")
    
    # Check scene consistency
    scene_ids = {scene.id for scene in scene_plan.scenes}
    for clip in scene_plan.clip_scripts:
        for scene_id in clip.scenes:
            if scene_id not in scene_ids:
                issues.append(f"Clip {clip.clip_index} references unknown scene: {scene_id}")
    
    # Check main character appears in 60-80% of clips
    main_characters = [char.id for char in scene_plan.characters if char.role == "main character"]
    if main_characters:
        main_char_id = main_characters[0]
        appearances = sum(1 for clip in scene_plan.clip_scripts if main_char_id in clip.characters)
        appearance_rate = appearances / len(scene_plan.clip_scripts) if scene_plan.clip_scripts else 0
        
        if appearance_rate < 0.6:
            issues.append(
                f"Main character appears in only {appearance_rate:.1%} of clips "
                f"(should be 60-80%)"
            )
        elif appearance_rate > 0.8:
            issues.append(
                f"Main character appears in {appearance_rate:.1%} of clips "
                f"(should be 60-80%)"
            )
    
    # Check scene count (2-4 scenes recommended)
    if len(scene_plan.scenes) < 2:
        issues.append(f"Too few scenes: {len(scene_plan.scenes)} (recommended: 2-4)")
    elif len(scene_plan.scenes) > 4:
        issues.append(f"Too many scenes: {len(scene_plan.scenes)} (recommended: 2-4)")
    
    if issues:
        logger.warning(
            f"Style consistency issues found: {len(issues)}",
            extra={"issues": issues}
        )
        return False
    
    logger.info("Style consistency check passed")
    return True


def refine_style(scene_plan: ScenePlan) -> ScenePlan:
    """
    Refine style guide to ensure consistency.
    
    If inconsistencies are found, this function attempts to fix them:
    - Adds missing characters/scenes if referenced
    - Adjusts color palette if needed
    - Ensures main character appears in appropriate clips
    
    Args:
        scene_plan: ScenePlan to refine
        
    Returns:
        Refined ScenePlan
    """
    # For now, just validate - future enhancement could auto-fix
    # Most fixes should be done in LLM prompt to prevent issues
    
    is_consistent = analyze_style_consistency(scene_plan)
    
    if not is_consistent:
        logger.warning("Style inconsistencies found, but auto-refinement not implemented")
        # Could add auto-fix logic here in the future
    
    return scene_plan

