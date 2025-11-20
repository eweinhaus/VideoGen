"""
Data loading from job_stages table.

Loads clip data, prompts, scene plans, and reference images from job_stages.metadata.
All data is stored as JSON in the metadata column, not in separate tables.
"""
import json
from typing import Optional, List, Dict
from uuid import UUID

from shared.database import DatabaseClient
from shared.models.video import Clips, ClipPrompts
from shared.models.scene import ScenePlan, ReferenceImages, Transition
from shared.models.audio import AudioAnalysis
from shared.logging import get_logger

logger = get_logger("clip_regenerator.data_loader")


async def load_clips_from_job_stages(job_id: UUID) -> Optional[Clips]:
    """
    Load Clips object from job_stages.metadata.
    
    Metadata structure: {"clips": {"clips": [...], "total_clips": 6, ...}}
    
    Args:
        job_id: Job ID to load clips for
        
    Returns:
        Clips object if found, None if stage not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "video_generator").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No video_generator stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            logger.warning(
                f"Empty metadata for video_generator stage, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # Access nested structure: metadata['clips']['clips']
        clips_data = metadata.get("clips")
        if not clips_data:
            logger.warning(
                f"No clips data in metadata, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Ensure clips_data is a dict (might be just a list in some cases)
        if isinstance(clips_data, list):
            clips_data = {"clips": clips_data}
        
        # Fill in missing required fields
        clips_list = clips_data.get("clips", [])
        if not isinstance(clips_list, list):
            logger.error(
                f"Invalid clips data structure: clips is not a list",
                extra={"job_id": str(job_id), "clips_type": type(clips_list).__name__}
            )
            return None
        
        # Filter and validate individual clip objects
        # Incomplete clips (missing required fields) will be skipped
        from decimal import Decimal
        validated_clips = []
        incomplete_count = 0
        
        for clip_data in clips_list:
            if not isinstance(clip_data, dict):
                incomplete_count += 1
                continue
            
            # Check for minimum required fields for a valid Clip
            required_fields = ["video_url", "actual_duration", "target_duration", 
                             "duration_diff", "status", "cost", "generation_time"]
            has_all_required = all(field in clip_data for field in required_fields)
            
            if not has_all_required:
                incomplete_count += 1
                logger.debug(
                    f"Skipping incomplete clip at index {clip_data.get('clip_index', 'unknown')}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": clip_data.get("clip_index"),
                        "missing_fields": [f for f in required_fields if f not in clip_data]
                    }
                )
                continue
            
            # Ensure cost is a valid Decimal
            try:
                cost_value = clip_data.get("cost", 0)
                if isinstance(cost_value, str):
                    clip_data["cost"] = Decimal(cost_value)
                elif isinstance(cost_value, (int, float)):
                    clip_data["cost"] = Decimal(str(cost_value))
                else:
                    clip_data["cost"] = Decimal(0)
            except Exception:
                clip_data["cost"] = Decimal(0)
            
            # Ensure numeric fields are the right type
            for field in ["actual_duration", "target_duration", "original_target_duration", "duration_diff", "generation_time"]:
                if field in clip_data and clip_data[field] is not None:
                    try:
                        clip_data[field] = float(clip_data[field])
                    except (ValueError, TypeError):
                        # For original_target_duration, default to target_duration if conversion fails
                        if field == "original_target_duration":
                            clip_data[field] = clip_data.get("target_duration", 0.0)
                        else:
                            clip_data[field] = 0.0
            
            # Ensure metadata is a dict (default to empty dict if missing or invalid)
            if "metadata" not in clip_data or not isinstance(clip_data.get("metadata"), dict):
                clip_data["metadata"] = {}
            
            validated_clips.append(clip_data)
        
        if incomplete_count > 0:
            logger.warning(
                f"Skipped {incomplete_count} incomplete clip(s) when loading from job_stages",
                extra={
                    "job_id": str(job_id),
                    "incomplete_count": incomplete_count,
                    "valid_clips": len(validated_clips)
                }
            )
        
        if len(validated_clips) == 0:
            logger.error(
                f"No valid clips found in job_stages metadata",
                extra={
                    "job_id": str(job_id),
                    "total_clips_in_db": len(clips_list),
                    "incomplete_count": incomplete_count
                }
            )
            return None
        
        # Update clips_data with validated clips
        clips_data["clips"] = validated_clips
        
        # Add job_id if missing
        if "job_id" not in clips_data:
            clips_data["job_id"] = str(job_id)
        
        # Calculate missing fields from validated clips list
        if "total_clips" not in clips_data:
            clips_data["total_clips"] = len(validated_clips)
        
        if "successful_clips" not in clips_data:
            clips_data["successful_clips"] = sum(1 for clip in validated_clips if clip.get("status") == "success")
        
        if "failed_clips" not in clips_data:
            clips_data["failed_clips"] = sum(1 for clip in validated_clips if clip.get("status") == "failed")
        
        # Calculate total_cost from validated clips if missing
        if "total_cost" not in clips_data:
            total_cost = Decimal(0)
            for clip in validated_clips:
                clip_cost = clip.get("cost", Decimal(0))
                if isinstance(clip_cost, Decimal):
                    total_cost += clip_cost
                else:
                    try:
                        total_cost += Decimal(str(clip_cost))
                    except Exception:
                        pass
            clips_data["total_cost"] = str(total_cost)
        
        # Calculate total_generation_time from validated clips if missing
        if "total_generation_time" not in clips_data:
            total_time = sum(clip.get("generation_time", 0) for clip in validated_clips)
            clips_data["total_generation_time"] = total_time
        
        # Reconstruct Pydantic model
        try:
            clips = Clips(**clips_data)
            logger.debug(
                f"Successfully loaded {len(clips.clips)} clips from job_stages",
                extra={"job_id": str(job_id), "total_clips": len(clips.clips)}
            )
            return clips
        except Exception as e:
            logger.error(
                f"Failed to reconstruct Clips model: {e}",
                extra={
                    "job_id": str(job_id),
                    "clips_data_keys": list(clips_data.keys()) if isinstance(clips_data, dict) else "not_a_dict",
                    "clips_count": len(clips_list) if isinstance(clips_list, list) else 0
                },
                exc_info=True
            )
            return None
        
    except Exception as e:
        logger.error(
            f"Failed to load clips from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def load_clip_prompts_from_job_stages(job_id: UUID) -> Optional[ClipPrompts]:
    """
    Load ClipPrompts object from job_stages.metadata.
    
    Args:
        job_id: Job ID to load prompts for
        
    Returns:
        ClipPrompts object if found, None if stage not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "prompt_generator").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No prompt_generator stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            logger.warning(
                f"Empty metadata for prompt_generator stage, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # The orchestrator saves metadata as {"clip_prompts": clip_prompts_dict}
        # Check if we have a nested structure and extract the actual clip_prompts dict
        if "clip_prompts" in metadata and isinstance(metadata.get("clip_prompts"), dict):
            # Nested structure: metadata = {"clip_prompts": {...}}
            clip_prompts_data = metadata["clip_prompts"]
        else:
            # Direct structure: metadata = {...} (for backward compatibility)
            clip_prompts_data = metadata
        
        # Fill in missing required fields
        if "job_id" not in clip_prompts_data:
            clip_prompts_data["job_id"] = str(job_id)
        
        # Calculate total_clips from clip_prompts list if missing
        clip_prompts_list = clip_prompts_data.get("clip_prompts", [])
        if not isinstance(clip_prompts_list, list):
            logger.error(
                f"Invalid clip_prompts data structure: clip_prompts is not a list",
                extra={"job_id": str(job_id), "clip_prompts_type": type(clip_prompts_list).__name__}
            )
            return None
        
        if "total_clips" not in clip_prompts_data:
            clip_prompts_data["total_clips"] = len(clip_prompts_list)
        
        # Set default generation_time if missing
        if "generation_time" not in clip_prompts_data:
            clip_prompts_data["generation_time"] = 0.0
        
        # Reconstruct Pydantic model
        try:
            clip_prompts = ClipPrompts(**clip_prompts_data)
            logger.debug(
                f"Successfully loaded clip prompts from job_stages",
                extra={"job_id": str(job_id), "total_clips": clip_prompts.total_clips}
            )
            return clip_prompts
        except Exception as e:
            logger.error(
                f"Failed to reconstruct ClipPrompts model: {e}",
                extra={
                    "job_id": str(job_id),
                    "metadata_keys": list(metadata.keys()) if isinstance(metadata, dict) else "not_a_dict",
                    "clip_prompts_data_keys": list(clip_prompts_data.keys()) if isinstance(clip_prompts_data, dict) else "not_a_dict",
                    "clip_prompts_count": len(clip_prompts_list) if isinstance(clip_prompts_list, list) else 0
                },
                exc_info=True
            )
            return None
        
    except Exception as e:
        logger.error(
            f"Failed to load clip prompts from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def load_scene_plan_from_job_stages(job_id: UUID) -> Optional[ScenePlan]:
    """
    Load ScenePlan object from job_stages.metadata.
    
    Metadata structure: {"scene_plan": {"job_id": ..., "video_summary": ..., ...}}
    
    Args:
        job_id: Job ID to load scene plan for
        
    Returns:
        ScenePlan object if found, None if stage not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "scene_planner").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No scene_planner stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            logger.warning(
                f"Empty metadata for scene_planner stage, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # The orchestrator saves metadata as {"scene_plan": scene_plan_dict}
        # Check if we have a nested structure and extract the actual scene_plan dict
        if "scene_plan" in metadata and isinstance(metadata.get("scene_plan"), dict):
            # Nested structure: metadata = {"scene_plan": {...}}
            scene_plan_data = metadata["scene_plan"]
        else:
            # Direct structure: metadata = {...} (for backward compatibility)
            scene_plan_data = metadata
        
        # Fill in missing required fields
        if "job_id" not in scene_plan_data:
            scene_plan_data["job_id"] = str(job_id)
        
        # Reconstruct Pydantic model
        try:
            scene_plan = ScenePlan(**scene_plan_data)
            logger.debug(
                f"Successfully loaded scene plan from job_stages",
                extra={"job_id": str(job_id)}
            )
            return scene_plan
        except Exception as e:
            logger.error(
                f"Failed to reconstruct ScenePlan model: {e}",
                extra={"job_id": str(job_id)},
                exc_info=True
            )
            return None
        
    except Exception as e:
        logger.error(
            f"Failed to load scene plan from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def load_reference_images_from_job_stages(job_id: UUID) -> Optional[ReferenceImages]:
    """
    Load ReferenceImages object from job_stages.metadata.
    
    Args:
        job_id: Job ID to load reference images for
        
    Returns:
        ReferenceImages object if found, None if stage not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "reference_generator").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No reference_generator stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            logger.warning(
                f"Empty metadata for reference_generator stage, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # Reconstruct Pydantic model
        try:
            reference_images = ReferenceImages(**metadata)
            logger.debug(
                f"Successfully loaded reference images from job_stages",
                extra={"job_id": str(job_id)}
            )
            return reference_images
        except Exception as e:
            logger.error(
                f"Failed to reconstruct ReferenceImages model: {e}",
                extra={"job_id": str(job_id)},
                exc_info=True
            )
            return None
        
    except Exception as e:
        logger.error(
            f"Failed to load reference images from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def load_transitions_from_job_stages(job_id: UUID) -> List[Transition]:
    """
    Load transitions from job_stages.metadata (scene_planner stage).
    
    Transitions are stored in scene_plan.transitions within the metadata.
    Metadata structure: {"scene_plan": {"transitions": [...], ...}}
    
    Args:
        job_id: Job ID to load transitions for
        
    Returns:
        List of Transition objects if found, empty list if not found or invalid
    """
    try:
        scene_plan = await load_scene_plan_from_job_stages(job_id)
        if scene_plan:
            return scene_plan.transitions
        
        # Fallback: Try to load directly from metadata
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "scene_planner").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No scene_planner stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return []
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            return []
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                return []
        
        # Check if transitions are nested under scene_plan
        scene_plan_data = metadata.get("scene_plan")
        if scene_plan_data and "transitions" in scene_plan_data:
            transitions_data = scene_plan_data["transitions"]
            try:
                transitions = [Transition(**t) for t in transitions_data]
                logger.debug(
                    f"Successfully loaded {len(transitions)} transitions from job_stages",
                    extra={"job_id": str(job_id), "transition_count": len(transitions)}
                )
                return transitions
            except Exception as e:
                logger.warning(
                    f"Failed to reconstruct transitions: {e}",
                    extra={"job_id": str(job_id)}
                )
                return []
        
        return []
        
    except Exception as e:
        logger.error(
            f"Failed to load transitions from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return []


async def load_beat_timestamps_from_job_stages(job_id: UUID) -> Optional[List[float]]:
    """
    Load beat timestamps from job_stages.metadata (audio_parser stage).
    
    Beat timestamps are stored in audio_analysis.beat_timestamps within the metadata.
    Metadata structure: {"audio_analysis": {"beat_timestamps": [...], ...}}
    
    Args:
        job_id: Job ID to load beat timestamps for
        
    Returns:
        List of beat timestamps (floats) if found, None if not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "audio_parser").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No audio_parser stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # Check if beat_timestamps are nested under audio_analysis
        audio_analysis = metadata.get("audio_analysis")
        if audio_analysis and "beat_timestamps" in audio_analysis:
            beat_timestamps = audio_analysis["beat_timestamps"]
            if isinstance(beat_timestamps, list) and all(isinstance(ts, (int, float)) for ts in beat_timestamps):
                logger.debug(
                    f"Successfully loaded {len(beat_timestamps)} beat timestamps from job_stages",
                    extra={"job_id": str(job_id), "beat_count": len(beat_timestamps)}
                )
                return [float(ts) for ts in beat_timestamps]
        
        # Fallback: Check if beat_timestamps are at top level
        if "beat_timestamps" in metadata:
            beat_timestamps = metadata["beat_timestamps"]
            if isinstance(beat_timestamps, list) and all(isinstance(ts, (int, float)) for ts in beat_timestamps):
                return [float(ts) for ts in beat_timestamps]
        
        return None
        
    except Exception as e:
        logger.error(
            f"Failed to load beat timestamps from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def get_audio_url(job_id: UUID) -> str:
    """
    Get audio URL from jobs table.
    
    Args:
        job_id: Job ID to get audio URL for
        
    Returns:
        Audio URL string
        
    Raises:
        ValidationError: If job not found or audio_url is missing
    """
    from shared.errors import ValidationError
    
    try:
        db = DatabaseClient()
        # Use fallback pattern for .single() method
        eq_builder = db.table("jobs").select("audio_url").eq("id", str(job_id))
        if hasattr(eq_builder, 'single'):
            try:
                result = await eq_builder.single().execute()
            except AttributeError:
                result = await eq_builder.limit(1).execute()
        else:
            result = await eq_builder.limit(1).execute()
        
        if not result.data:
            raise ValidationError(f"Job {job_id} not found")
        
        # Handle both dict (from .single()) and list (from .limit(1)) results
        job_data = result.data if isinstance(result.data, dict) else (result.data[0] if result.data else {})
        audio_url = job_data.get("audio_url")
        if not audio_url:
            raise ValidationError(f"Audio URL not found for job {job_id}")
        
        logger.debug(
            f"Successfully loaded audio URL from jobs table",
            extra={"job_id": str(job_id)}
        )
        return audio_url
        
    except Exception as e:
        logger.error(
            f"Failed to load audio URL: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        raise


async def load_audio_data_from_job_stages(job_id: UUID) -> Optional[AudioAnalysis]:
    """
    Load AudioAnalysis object from job_stages.metadata (audio_parser stage).
    
    Args:
        job_id: Job ID to load audio data for
        
    Returns:
        AudioAnalysis object if found, None if stage not found or invalid
    """
    try:
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "audio_parser").execute()
        
        if not result.data or len(result.data) == 0:
            logger.debug(
                f"No audio_parser stage found for job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        metadata = result.data[0].get("metadata")
        if not metadata:
            logger.warning(
                f"Empty metadata for audio_parser stage, job {job_id}",
                extra={"job_id": str(job_id)}
            )
            return None
        
        # Handle JSON string or dict
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse metadata JSON: {e}",
                    extra={"job_id": str(job_id)}
                )
                return None
        
        # Check if audio_analysis is nested or at top level
        audio_data = metadata.get("audio_analysis")
        if not audio_data:
            # Try top level
            audio_data = metadata
        
        # Fill in missing required fields
        if "job_id" not in audio_data:
            audio_data["job_id"] = str(job_id)
        
        # Reconstruct Pydantic model
        try:
            audio_analysis = AudioAnalysis(**audio_data)
            logger.debug(
                f"Successfully loaded audio analysis from job_stages",
                extra={"job_id": str(job_id), "bpm": audio_analysis.bpm}
            )
            return audio_analysis
        except Exception as e:
            logger.error(
                f"Failed to reconstruct AudioAnalysis model: {e}",
                extra={
                    "job_id": str(job_id),
                    "audio_data_keys": list(audio_data.keys()) if isinstance(audio_data, dict) else "not_a_dict"
                },
                exc_info=True
            )
            return None
        
    except Exception as e:
        logger.error(
            f"Failed to load audio data from job_stages: {e}",
            extra={"job_id": str(job_id)},
            exc_info=True
        )
        return None


async def get_aspect_ratio(job_id: UUID) -> str:
    """
    Get aspect ratio from job data.
    
    Checks job_stages metadata first, then falls back to default "16:9".
    
    Args:
        job_id: Job ID to get aspect ratio for
        
    Returns:
        Aspect ratio string (default: "16:9")
    """
    try:
        # Try to get from job_stages metadata (video_generator stage)
        db = DatabaseClient()
        result = await db.table("job_stages").select("metadata").eq(
            "job_id", str(job_id)
        ).eq("stage_name", "video_generator").execute()
        
        if result.data and len(result.data) > 0:
            metadata = result.data[0].get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    pass
            
            if isinstance(metadata, dict):
                aspect_ratio = metadata.get("aspect_ratio")
                if aspect_ratio:
                    logger.debug(
                        f"Successfully loaded aspect ratio from job_stages",
                        extra={"job_id": str(job_id), "aspect_ratio": aspect_ratio}
                    )
                    return aspect_ratio
        
        # Fallback to default
        logger.debug(
            f"Aspect ratio not found, using default 16:9",
            extra={"job_id": str(job_id)}
        )
        return "16:9"
        
    except Exception as e:
        logger.warning(
            f"Failed to load aspect ratio: {e}, using default 16:9",
            extra={"job_id": str(job_id)}
        )
        return "16:9"


async def load_clip_version(
    job_id: UUID,
    clip_index: int,
    version_number: Optional[int] = None
) -> Optional[Dict]:
    """
    Load clip version data for comparison.
    
    Loads from clip_versions table if version_number is specified,
    otherwise loads current version (is_current=True) or original from clips table.
    
    Args:
        job_id: Job ID
        clip_index: Index of clip
        version_number: Optional version number (1 = original, 2+ = regenerated)
                       If None, loads current version or original
        
    Returns:
        Dict with video_url, thumbnail_url, prompt, version_number, duration, user_instruction
        None if version not found
    """
    try:
        db = DatabaseClient()
        
        # If version_number is specified, try to load from clip_versions table
        if version_number is not None:
            # Check if clip_versions table exists (Part 4 dependency)
            try:
                result = await db.table("clip_versions").select("*").eq(
                    "job_id", str(job_id)
                ).eq("clip_index", clip_index).eq("version_number", version_number).execute()
                
                if result.data and len(result.data) > 0:
                    version_data = result.data[0]
                    return {
                        "video_url": version_data.get("video_url"),
                        "thumbnail_url": version_data.get("thumbnail_url"),
                        "prompt": version_data.get("prompt"),
                        "version_number": version_data.get("version_number"),
                        "duration": None,  # Duration not stored in clip_versions, extract from video if needed
                        "user_instruction": version_data.get("user_instruction"),
                        "cost": float(version_data.get("cost", 0)) if version_data.get("cost") else None,
                        "created_at": version_data.get("created_at")
                    }
            except Exception as e:
                # Table may not exist (Part 4 not implemented yet)
                logger.debug(
                    f"clip_versions table not available: {e}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
        
        # Fallback: Load from clips table (original version)
        clips = await load_clips_from_job_stages(job_id)
        if clips:
            for clip in clips.clips:
                if clip.clip_index == clip_index:
                    # Get thumbnail URL if available
                    thumbnail_url = None
                    try:
                        thumb_result = await db.table("clip_thumbnails").select("thumbnail_url").eq(
                            "job_id", str(job_id)
                        ).eq("clip_index", clip_index).limit(1).execute()
                        if thumb_result.data and len(thumb_result.data) > 0:
                            thumbnail_url = thumb_result.data[0].get("thumbnail_url")
                    except Exception:
                        pass  # Table may not exist
                    
                    # Get prompt
                    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
                    prompt = ""
                    if clip_prompts and clip_index < len(clip_prompts.clip_prompts):
                        prompt = clip_prompts.clip_prompts[clip_index].prompt
                    
                    return {
                        "video_url": clip.video_url,
                        "thumbnail_url": thumbnail_url,
                        "prompt": prompt,
                        "version_number": 1,  # Original version
                        "duration": clip.actual_duration or clip.target_duration,
                        "user_instruction": None,  # Original has no instruction
                        "cost": float(clip.cost) if clip.cost else None,
                        "created_at": None
                    }
        
        return None
        
    except Exception as e:
        logger.error(
            f"Failed to load clip version: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index, "version_number": version_number},
            exc_info=True
        )
        return None

