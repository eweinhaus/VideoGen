"""
Test fixtures for Reference Generator module.
"""

from uuid import UUID
from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition


def create_mock_scene_plan(
    job_id: str = "550e8400-e29b-41d4-a716-446655440000",
    num_scenes: int = 2,
    num_characters: int = 2,
    style_variant: str = "default"
) -> ScenePlan:
    """
    Create a mock ScenePlan for testing.
    
    Args:
        job_id: Job ID string
        num_scenes: Number of scenes to generate
        num_characters: Number of characters to generate
        style_variant: Style variant ("default", "cyberpunk", "minimal")
        
    Returns:
        ScenePlan object
    """
    # Create characters
    characters = [
        Character(
            id=f"char{i+1}",
            description=f"Character {i+1} description",
            role="main character" if i == 0 else "background"
        )
        for i in range(num_characters)
    ]
    
    # Create scenes
    scenes = [
        Scene(
            id=f"scene{i+1}",
            description=f"Scene {i+1} location description",
            time_of_day="day" if i % 2 == 0 else "night"
        )
        for i in range(num_scenes)
    ]
    
    # Create style based on variant
    if style_variant == "cyberpunk":
        style = Style(
            color_palette=["#00FFFF", "#FF00FF", "#0000FF"],
            visual_style="Neo-noir cyberpunk",
            mood="dark",
            lighting="High-contrast neon with deep shadows",
            cinematography="Handheld tracking shots"
        )
    elif style_variant == "minimal":
        style = Style(
            color_palette=["#FFFFFF", "#000000", "#808080"],
            visual_style="Minimalist",
            mood="calm",
            lighting="Soft natural light",
            cinematography="Static wide shots"
        )
    else:  # default
        style = Style(
            color_palette=["#FF5733", "#33FF57", "#3357FF"],
            visual_style="realistic",
            mood="energetic",
            lighting="bright",
            cinematography="dynamic"
        )
    
    # Create clip scripts
    clip_scripts = [
        ClipScript(
            clip_index=i,
            start=float(i * 4),
            end=float((i + 1) * 4),
            visual_description=f"Clip {i+1} visual description",
            motion="tracking shot" if i % 2 == 0 else "static",
            camera_angle="wide" if i == 0 else "medium",
            characters=[f"char{1}"],
            scenes=[f"scene{1}"],
            lyrics_context=None,
            beat_intensity="high"
        )
        for i in range(3)
    ]
    
    # Create transitions
    transitions = [
        Transition(
            from_clip=i,
            to_clip=i + 1,
            type="cut" if i % 2 == 0 else "crossfade",
            duration=0.5,
            rationale="Beat-aligned transition"
        )
        for i in range(len(clip_scripts) - 1)
    ]
    
    return ScenePlan(
        job_id=UUID(job_id),
        video_summary="Test video summary",
        characters=characters,
        scenes=scenes,
        style=style,
        clip_scripts=clip_scripts,
        transitions=transitions
    )


def create_single_scene_plan() -> ScenePlan:
    """Create a ScenePlan with single scene and character (edge case)."""
    return create_mock_scene_plan(num_scenes=1, num_characters=1)


def create_duplicate_id_plan() -> ScenePlan:
    """Create a ScenePlan with duplicate IDs (for validation testing)."""
    plan = create_mock_scene_plan()
    # Add duplicate scene ID
    plan.scenes.append(Scene(
        id=plan.scenes[0].id,  # Duplicate ID
        description="Duplicate scene",
        time_of_day="day"
    ))
    return plan


def create_large_plan() -> ScenePlan:
    """Create a ScenePlan with many scenes and characters (for performance testing)."""
    return create_mock_scene_plan(num_scenes=5, num_characters=3)

