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
from .character_description_validator import (
    extract_character_features,
    validate_and_reformat_character_description,
    validate_character_specificity
)
from .character_analyzer import (
    analyze_clips_for_implicit_characters,
    update_clip_scripts_with_characters
)
from .object_analyzer import (
    extract_objects_from_user_input,
    analyze_clips_for_objects,
    update_clip_scripts_with_objects as update_clips_with_object_ids
)

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
        user_prompt: User's creative prompt (50-3000 characters)
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
        
        # Step 1a: Extract objects from user input before LLM generation
        # This allows us to pass explicit object hints to the LLM
        user_input_objects = extract_objects_from_user_input(user_prompt)
        if user_input_objects:
            logger.info(
                f"Extracted {len(user_input_objects)} objects from user input",
                extra={
                    "job_id": str(job_id),
                    "object_ids": [obj.id for obj in user_input_objects]
                }
            )
        
        # Step 2: Generate scene plan using LLM
        llm_output = await generate_scene_plan(
            job_id=job_id,
            user_prompt=user_prompt,
            audio_data=audio_data,
            director_knowledge=director_knowledge,
            user_input_objects=user_input_objects  # Pass extracted objects as hints
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

        # PHASE 2: Analyze clips for implicit/background characters
        # This happens BEFORE character extraction to ensure we catch all mentioned characters
        
        # Step 5: Extract other components from LLM output
        characters = []
        scenes = []
        style = None
        video_summary = ""
        
        if "characters" in llm_output:
            from shared.models.scene import Character
            # Create characters and extract structured features
            characters = []
            for char_data in llm_output["characters"]:
                # Extract character name from description if format is "Name - FIXED CHARACTER IDENTITY:"
                # Otherwise use the character ID as fallback
                description = char_data.get("description", "")
                char_id = char_data.get("id", "unknown")
                char_role = char_data.get("role", "character")

                # Try to extract character name from description
                character_name = char_id
                if " - FIXED CHARACTER IDENTITY:" in description:
                    character_name = description.split(" - FIXED CHARACTER IDENTITY:")[0].strip()
                elif description:
                    # Use first word of description as name fallback (but not feature keys)
                    first_word = description.split()[0] if description.split() else char_id
                    # Don't use feature keys like "Hair:", "Face:", etc. as names
                    feature_keys = ["Hair:", "Face:", "Eyes:", "Clothing:", "Accessories:", "Build:", "Age:"]
                    if (len(first_word) <= 20 and
                        first_word[0].isupper() and
                        first_word not in feature_keys and
                        not first_word.startswith("-")):
                        character_name = first_word

                # EXTRACT structured features (does NOT format into text)
                features, extracted_name = extract_character_features(
                    character_id=char_id,
                    character_name=character_name,
                    description=description
                )

                # Use extracted name if available
                if extracted_name:
                    character_name = extracted_name

                # Validate specificity if features were extracted
                if features:
                    # Build a temporary formatted description for specificity check
                    # Format face_features into a string
                    face_desc = f"{features.face_features.shape} face, {features.face_features.skin_tone} skin, {features.face_features.nose}, {features.face_features.mouth}, {features.face_features.cheeks}, {features.face_features.jawline}"
                    if features.face_features.distinctive_marks != "none":
                        face_desc += f", {features.face_features.distinctive_marks}"

                    temp_description = f"{character_name} - Hair: {features.hair}, Face: {face_desc}, Eyes: {features.eyes}, Clothing: {features.clothing}, Accessories: {features.accessories}, Build: {features.build}, Age: {features.age}"
                    specificity_check = validate_character_specificity(temp_description)
                    if not specificity_check["is_specific"]:
                        logger.warning(
                            f"Character {char_id} description lacks specificity",
                            extra={
                                "character_id": char_id,
                                "warnings": specificity_check["warnings"]
                            }
                        )

                # Create character with structured features
                # Keep description for backward compatibility (will be populated from features when needed)
                character = Character(
                    id=char_id,
                    role=char_role,
                    features=features,
                    name=character_name,
                    description=description  # Keep original for backward compatibility
                )
                characters.append(character)

        # PHASE 2: Analyze clip scripts for implicit/background characters
        # Scan clip descriptions for mentions of characters not in the character list
        implicit_characters = analyze_clips_for_implicit_characters(
            clip_scripts=clip_scripts,
            existing_characters=characters
        )

        if implicit_characters:
            logger.info(
                f"Found {len(implicit_characters)} implicit/background characters in clip scripts",
                extra={
                    "job_id": str(job_id),
                    "implicit_character_ids": [char.id for char in implicit_characters]
                }
            )
            # Add implicit characters to the character list
            characters.extend(implicit_characters)

            # Update clip scripts to include implicit character IDs
            clip_scripts = update_clip_scripts_with_characters(
                clip_scripts=clip_scripts,
                all_characters=characters
            )
            logger.debug("Updated clip scripts with implicit character IDs")

        # PHASE 3: Extract objects from LLM output and analyze clips for additional objects
        # Start with objects extracted from user input (they're already marked as primary)
        from shared.models.scene import Object, ObjectFeatures
        from .object_analyzer import _normalize_object_type
        
        objects = list(user_input_objects)  # Start with user input objects
        
        # Build object_type to Object mapping for consolidation
        # This prevents duplicate objects of the same type (e.g., "truck", "truck_1", "pickup truck")
        object_type_map = {}
        for obj in objects:
            normalized_type = _normalize_object_type(obj.features.object_type)
            if normalized_type not in object_type_map:
                object_type_map[normalized_type] = obj
            # Prefer primary importance
            elif obj.importance == "primary" and object_type_map[normalized_type].importance != "primary":
                object_type_map[normalized_type] = obj
        
        # Get objects from LLM (if provided)
        if "objects" in llm_output and llm_output["objects"]:
            existing_object_ids = {obj.id for obj in objects}
            for obj_data in llm_output["objects"]:
                # Parse object with nested features
                if "features" in obj_data:
                    obj_features = ObjectFeatures(**obj_data["features"])
                    obj = Object(
                        id=obj_data["id"],
                        name=obj_data["name"],
                        features=obj_features,
                        importance=obj_data.get("importance", "secondary")
                    )
                    
                    # Check for duplicate ID
                    if obj.id in existing_object_ids:
                        logger.debug(
                            f"Skipping duplicate object ID '{obj.id}' from LLM",
                            extra={"object_id": obj.id, "object_type": obj.features.object_type}
                        )
                        continue
                    
                    # Check for duplicate object_type (consolidation)
                    normalized_type = _normalize_object_type(obj.features.object_type)
                    if normalized_type in object_type_map:
                        existing_obj = object_type_map[normalized_type]
                        logger.info(
                            f"Consolidating duplicate object type '{obj.features.object_type}' (normalized: '{normalized_type}') - "
                            f"keeping existing '{existing_obj.id}' (importance: {existing_obj.importance}), "
                            f"skipping LLM object '{obj.id}' (importance: {obj.importance})",
                            extra={
                                "job_id": str(job_id),
                                "normalized_type": normalized_type,
                                "existing_object_id": existing_obj.id,
                                "skipped_object_id": obj.id,
                                "existing_importance": existing_obj.importance,
                                "skipped_importance": obj.importance
                            }
                        )
                        # If the new object is primary and existing is not, upgrade existing
                        if obj.importance == "primary" and existing_obj.importance != "primary":
                            existing_obj.importance = "primary"
                            logger.info(
                                f"Upgraded existing object '{existing_obj.id}' to primary importance",
                                extra={"object_id": existing_obj.id}
                            )
                        continue
                    
                    # Add new object
                    objects.append(obj)
                    existing_object_ids.add(obj.id)
                    object_type_map[normalized_type] = obj

            logger.info(
                f"LLM generated {len([o for o in objects if o not in user_input_objects])} additional object profiles",
                extra={
                    "job_id": str(job_id),
                    "object_ids": [obj.id for obj in objects],
                    "user_input_objects": len(user_input_objects)
                }
            )

        # Analyze clip scripts for additional objects not caught by LLM or user input
        detected_objects, clip_scripts = analyze_clips_for_objects(
            clip_scripts=clip_scripts,
            existing_objects=objects
        )

        if detected_objects:
            logger.info(
                f"Detected {len(detected_objects)} additional objects in clip scripts",
                extra={
                    "job_id": str(job_id),
                    "detected_object_ids": [obj.id for obj in detected_objects]
                }
            )
            # Add detected objects to the object list
            objects.extend(detected_objects)

        # If LLM provided objects but didn't assign them to clips, update clip scripts
        if objects and "objects" in llm_output and llm_output["objects"]:
            clip_scripts = update_clips_with_object_ids(
                clip_scripts=clip_scripts,
                objects=objects
            )
            logger.debug("Updated clip scripts with object IDs")

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
            objects=objects,
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

