"""
ScenePlan validation and refinement.

Validates ScenePlan output against audio data and fixes issues.
"""

from shared.models.scene import ScenePlan
from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

logger = get_logger("scene_planner")


def validate_scene_plan(
    scene_plan: ScenePlan,
    audio_data: AudioAnalysis
) -> ScenePlan:
    """
    Validate ScenePlan against audio data and fix issues.
    
    Validates:
    - Clip boundaries match audio clip_boundaries count
    - Clip start/end times align with boundaries (±0.5s tolerance)
    - Transitions match clip count (N-1 for N clips)
    - Character/scene references are valid
    - Style guide completeness
    
    Args:
        scene_plan: ScenePlan to validate
        audio_data: AudioAnalysis with clip boundaries
        
    Returns:
        Validated (and potentially fixed) ScenePlan
    """
    issues = []
    
    # Validate clip boundaries count
    expected_clip_count = len(audio_data.clip_boundaries)
    actual_clip_count = len(scene_plan.clip_scripts)
    
    if actual_clip_count != expected_clip_count:
        issues.append(
            f"Clip count mismatch: {actual_clip_count} clips, "
            f"expected {expected_clip_count}"
        )
        logger.warning(
            f"Clip count mismatch: {actual_clip_count} vs {expected_clip_count}",
            extra={"expected": expected_clip_count, "actual": actual_clip_count}
        )
    
    # Validate clip boundary alignment
    for i, (clip_script, boundary) in enumerate(
        zip(scene_plan.clip_scripts[:expected_clip_count], audio_data.clip_boundaries)
    ):
        tolerance = 0.5
        
        if abs(clip_script.start - boundary.start) > tolerance:
            issues.append(
                f"Clip {i} start time mismatch: {clip_script.start:.1f}s vs "
                f"{boundary.start:.1f}s (tolerance: ±{tolerance}s)"
            )
            # Fix: align to boundary
            clip_script.start = boundary.start
        
        if abs(clip_script.end - boundary.end) > tolerance:
            issues.append(
                f"Clip {i} end time mismatch: {clip_script.end:.1f}s vs "
                f"{boundary.end:.1f}s (tolerance: ±{tolerance}s)"
            )
            # Fix: align to boundary
            clip_script.end = boundary.end
    
    # Validate transitions count (N-1 for N clips)
    expected_transition_count = max(0, len(scene_plan.clip_scripts) - 1)
    actual_transition_count = len(scene_plan.transitions)
    
    if actual_transition_count != expected_transition_count:
        issues.append(
            f"Transition count mismatch: {actual_transition_count} transitions, "
            f"expected {expected_transition_count}"
        )
        logger.warning(
            f"Transition count mismatch: {actual_transition_count} vs {expected_transition_count}"
        )
    
    # Validate transition indices
    for transition in scene_plan.transitions:
        if transition.from_clip < 0 or transition.from_clip >= len(scene_plan.clip_scripts):
            issues.append(
                f"Invalid transition from_clip index: {transition.from_clip}"
            )
        if transition.to_clip < 0 or transition.to_clip >= len(scene_plan.clip_scripts):
            issues.append(
                f"Invalid transition to_clip index: {transition.to_clip}"
            )
        if transition.to_clip != transition.from_clip + 1:
            issues.append(
                f"Transition {transition.from_clip}->{transition.to_clip} "
                f"should be sequential"
            )
    
    # Validate character references
    character_ids = {char.id for char in scene_plan.characters}
    for clip in scene_plan.clip_scripts:
        for char_id in clip.characters:
            if char_id not in character_ids:
                issues.append(
                    f"Clip {clip.clip_index} references unknown character: {char_id}"
                )
                # Fix: remove invalid reference
                clip.characters = [c for c in clip.characters if c != char_id]
    
    # Validate scene references
    scene_ids = {scene.id for scene in scene_plan.scenes}
    for clip in scene_plan.clip_scripts:
        for scene_id in clip.scenes:
            if scene_id not in scene_ids:
                issues.append(
                    f"Clip {clip.clip_index} references unknown scene: {scene_id}"
                )
                # Fix: remove invalid reference
                clip.scenes = [s for s in clip.scenes if s != scene_id]
    
    # Validate time_of_day for all scenes
    valid_times_of_day = {
        "dawn", "morning", "midday", "afternoon",
        "dusk", "evening", "night", "midnight"
    }
    for scene in scene_plan.scenes:
        if not hasattr(scene, 'time_of_day') or not scene.time_of_day:
            issues.append(f"Scene '{scene.id}' is missing required 'time_of_day' field")
        elif scene.time_of_day.lower() not in valid_times_of_day:
            issues.append(
                f"Scene '{scene.id}' has invalid time_of_day '{scene.time_of_day}'. "
                f"Must be one of: {', '.join(sorted(valid_times_of_day))}"
            )

    # Validate style guide
    if not scene_plan.style.color_palette:
        issues.append("Missing color palette")
    elif len(scene_plan.style.color_palette) < 3:
        issues.append(
            f"Color palette too small: {len(scene_plan.style.color_palette)} colors "
            f"(minimum: 3)"
        )

    if not scene_plan.style.visual_style:
        issues.append("Missing visual style description")

    if not scene_plan.style.mood:
        issues.append("Missing mood description")

    if not scene_plan.style.lighting:
        issues.append("Missing lighting description")

    if not scene_plan.style.cinematography:
        issues.append("Missing cinematography description")
    
    # Log issues
    if issues:
        logger.warning(
            f"Validation found {len(issues)} issues",
            extra={"issues": issues[:10]}  # Limit log size
        )
    else:
        logger.info("ScenePlan validation passed")
    
    return scene_plan

