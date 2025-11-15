"""
Core scene planning orchestration.

Coordinates all planning steps and assembles final ScenePlan result.
"""

from uuid import UUID
from shared.models.audio import AudioAnalysis
from shared.models.scene import ScenePlan
from shared.errors import GenerationError
from shared.logging import get_logger

from .director_knowledge import get_director_knowledge
from .llm_client import generate_scene_plan
from .script_generator import generate_clip_scripts
from .transition_planner import plan_transitions
from .style_analyzer import analyze_style_consistency, refine_style
from .validator import validate_scene_plan

logger = get_logger("scene_planner")


async def plan_scenes(
    job_id: UUID,
    user_prompt: str,
    audio_data: AudioAnalysis
) -> ScenePlan:
    """
    Coordinate all planning steps and assemble final ScenePlan.
    
    Steps:
    1. Load director knowledge
    2. Generate scene plan using LLM
    3. Transform LLM output to clip scripts
    4. Plan transitions between clips
    5. Validate consistency
    6. Validate against audio data
    7. Assemble and return ScenePlan
    
    Args:
        job_id: Job ID
        user_prompt: User's creative prompt (50-500 characters)
        audio_data: AudioAnalysis with BPM, mood, structure, boundaries
        
    Returns:
        Complete ScenePlan model
        
    Raises:
        GenerationError: If planning fails
        ValidationError: If inputs are invalid
    """
    logger.info(
        f"Starting scene planning",
        extra={
            "job_id": str(job_id),
            "user_prompt_length": len(user_prompt),
            "clip_count": len(audio_data.clip_boundaries)
        }
    )
    
    try:
        # Step 1: Load director knowledge
        director_knowledge = get_director_knowledge()
        logger.debug("Loaded director knowledge base")
        
        # Step 2: Generate scene plan using LLM
        llm_output = await generate_scene_plan(
            job_id=job_id,
            user_prompt=user_prompt,
            audio_data=audio_data,
            director_knowledge=director_knowledge
        )
        logger.debug("Generated scene plan from LLM")
        
        # Step 3: Transform LLM output to clip scripts
        clip_scripts = generate_clip_scripts(
            llm_output=llm_output,
            clip_boundaries=audio_data.clip_boundaries,
            lyrics=audio_data.lyrics
        )
        logger.debug(f"Generated {len(clip_scripts)} clip scripts")
        
        # Step 4: Plan transitions
        transitions = plan_transitions(
            clip_scripts=clip_scripts,
            beat_timestamps=audio_data.beat_timestamps,
            song_structure=audio_data.song_structure
        )
        logger.debug(f"Planned {len(transitions)} transitions")
        
        # Step 5: Extract other components from LLM output
        characters = []
        scenes = []
        style = None
        video_summary = ""
        
        if "characters" in llm_output:
            from shared.models.scene import Character
            characters = [
                Character(**char_data)
                for char_data in llm_output["characters"]
            ]
        
        if "scenes" in llm_output:
            from shared.models.scene import Scene
            scenes = [
                Scene(**scene_data)
                for scene_data in llm_output["scenes"]
            ]
        
        if "style" in llm_output:
            from shared.models.scene import Style
            style = Style(**llm_output["style"])
        
        if "video_summary" in llm_output:
            video_summary = llm_output["video_summary"]
        
        # Ensure job_id matches (if LLM provided one)
        if "job_id" in llm_output:
            try:
                # Validate job_id matches (LLM might return invalid UUID format)
                llm_job_id = UUID(str(llm_output["job_id"]))
                if llm_job_id != job_id:
                    logger.warning(
                        f"LLM job_id mismatch: {llm_job_id} vs {job_id}, using provided job_id"
                    )
            except (ValueError, TypeError) as e:
                # LLM returned invalid UUID format - ignore and use provided job_id
                logger.debug(
                    f"LLM returned invalid job_id format: {llm_output['job_id']}, using provided job_id",
                    extra={"error": str(e)}
                )
        
        # Step 6: Assemble ScenePlan
        scene_plan = ScenePlan(
            job_id=job_id,
            video_summary=video_summary or "Music video scene plan",
            characters=characters,
            scenes=scenes,
            style=style or _create_default_style(audio_data),
            clip_scripts=clip_scripts,
            transitions=transitions
        )
        
        # Step 7: Validate consistency
        is_consistent = analyze_style_consistency(scene_plan)
        if not is_consistent:
            logger.warning("Style inconsistencies found, refining...")
            scene_plan = refine_style(scene_plan)
        
        # Step 8: Validate against audio data
        scene_plan = validate_scene_plan(scene_plan, audio_data)
        
        logger.info(
            f"Scene planning complete",
            extra={
                "job_id": str(job_id),
                "characters": len(scene_plan.characters),
                "scenes": len(scene_plan.scenes),
                "clips": len(scene_plan.clip_scripts),
                "transitions": len(scene_plan.transitions)
            }
        )
        
        return scene_plan
        
    except Exception as e:
        logger.error(
            f"Scene planning failed: {str(e)}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        raise GenerationError(
            f"Failed to plan scenes: {str(e)}",
            job_id=job_id
        ) from e


def _create_default_style(audio_data: AudioAnalysis) -> "Style":
    """Create default style if LLM didn't provide one."""
    from shared.models.scene import Style
    
    mood = audio_data.mood.primary.lower()
    
    # Default color palettes by mood
    if mood == "energetic":
        color_palette = ["#00FFFF", "#FF00FF", "#FFFF00", "#FF1493"]
        visual_style = "Vibrant, high-energy with saturated colors"
        lighting = "Dynamic lighting with color shifts, high contrast"
    elif mood == "calm":
        color_palette = ["#87CEEB", "#E6E6FA", "#B0E0E6", "#FFDAB9"]
        visual_style = "Soft, muted colors with peaceful atmosphere"
        lighting = "Soft, natural, diffused light, low contrast"
    elif mood == "dark":
        color_palette = ["#000000", "#2F2F2F", "#00008B", "#8B0000"]
        visual_style = "Dark, moody with high contrast"
        lighting = "Low-key lighting, single source, deep shadows"
    else:  # bright or default
        color_palette = ["#FFFF00", "#FFFFFF", "#87CEEB", "#FFC0CB"]
        visual_style = "Bright, uplifting with high brightness"
        lighting = "High-key lighting, multiple sources, even illumination"
    
    return Style(
        color_palette=color_palette,
        visual_style=visual_style,
        mood=audio_data.mood.primary,
        lighting=lighting,
        cinematography="Balanced framing with smooth camera movements"
    )

