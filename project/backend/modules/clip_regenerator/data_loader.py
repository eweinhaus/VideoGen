"""
Data loading from job_stages table.

Loads clip data, prompts, scene plans, and reference images from job_stages.metadata.
All data is stored as JSON in the metadata column, not in separate tables.
"""
import json
from typing import Optional, List
from uuid import UUID

from shared.database import DatabaseClient
from shared.models.video import Clips, ClipPrompts
from shared.models.scene import ScenePlan, ReferenceImages, Transition
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
                extra={"job_id": str(job_id)},
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
        
        # Reconstruct Pydantic model
        try:
            clip_prompts = ClipPrompts(**metadata)
            logger.debug(
                f"Successfully loaded clip prompts from job_stages",
                extra={"job_id": str(job_id), "total_clips": clip_prompts.total_clips}
            )
            return clip_prompts
        except Exception as e:
            logger.error(
                f"Failed to reconstruct ClipPrompts model: {e}",
                extra={"job_id": str(job_id)},
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
        
        # Reconstruct Pydantic model
        try:
            scene_plan = ScenePlan(**metadata)
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
        result = await db.table("jobs").select("audio_url").eq("id", str(job_id)).single().execute()
        
        if not result.data:
            raise ValidationError(f"Job {job_id} not found")
        
        audio_url = result.data.get("audio_url")
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

