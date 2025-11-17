"""
Upload endpoint.

Handles audio file upload and job creation.
"""

import uuid
import re
import asyncio
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from mutagen import File as MutagenFile
from shared.storage import StorageClient
from shared.database import DatabaseClient
from shared.validation import validate_audio_file, validate_prompt
from shared.errors import ValidationError, BudgetExceededError, RetryableError
from shared.logging import get_logger
from shared.config import settings
from api_gateway.dependencies import get_current_user
from api_gateway.services.rate_limiter import check_rate_limit
from api_gateway.services.queue_service import enqueue_job
from api_gateway.services.budget_helpers import get_cost_estimate, get_budget_limit

logger = get_logger(__name__)

router = APIRouter()
storage_client = StorageClient()
db_client = DatabaseClient()


@router.post("/upload-audio", status_code=status.HTTP_201_CREATED)
async def upload_audio(
    audio_file: UploadFile = File(...),
    user_prompt: str = Form(...),
    stop_at_stage: str = Form(None),
    video_model: str = Form("kling_v21"),
    aspect_ratio: str = Form("16:9"),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload audio file and create video generation job.
    
    Args:
        audio_file: Audio file (MP3/WAV/FLAC, ≤10MB)
        user_prompt: Creative prompt (50-500 characters)
        stop_at_stage: Optional stage to stop at (for testing: audio_parser, scene_planner, reference_generator, prompt_generator, video_generator, composer)
        video_model: Video generation model to use (kling_v21, kling_v25_turbo, hailuo_23, wan_25_i2v, veo_31)
        current_user: Current authenticated user
        
    Returns:
        Job creation response with job_id, status, estimated_cost
    """
    user_id = current_user["user_id"]
    job_id = str(uuid.uuid4())
    
    try:
        # Validate file (pass filename separately for MIME type detection)
        # Create a wrapper to add filename attribute if needed
        file_obj = audio_file.file
        if audio_file.filename and not hasattr(file_obj, "name"):
            # Add filename attribute for validation
            file_obj.name = audio_file.filename
        validate_audio_file(file_obj, max_size_mb=10)
        
        # Validate prompt
        validate_prompt(user_prompt, min_length=50, max_length=500)
        
        # Extract audio duration using mutagen (metadata only, no full decode)
        audio_file.file.seek(0)
        try:
            audio_obj = MutagenFile(audio_file.file)
            if audio_obj is None:
                raise ValidationError("Could not read audio file metadata")
            duration = audio_obj.info.length  # Duration in seconds
        except Exception as e:
            logger.error("Failed to extract audio duration", exc_info=e)
            raise ValidationError(f"Failed to extract audio duration: {str(e)}")
        finally:
            audio_file.file.seek(0)
        
        # Calculate pre-flight cost estimate (environment-aware)
        duration_minutes = duration / 60
        estimated_cost = get_cost_estimate(duration_minutes, settings.environment)
        budget_limit = float(get_budget_limit(settings.environment))
        
        # Reject if estimated cost exceeds budget limit
        if estimated_cost > budget_limit:
            raise BudgetExceededError(
                f"Estimated cost (${estimated_cost:.2f}) exceeds ${budget_limit:.2f} limit. "
                f"Audio duration: {duration_minutes:.2f} minutes"
            )
        
        # Check rate limit
        await check_rate_limit(user_id)
        
        # Upload audio to Supabase Storage
        # Read file content as bytes
        audio_file.file.seek(0)
        file_data = await audio_file.read()
        audio_file.file.seek(0)  # Reset for potential reuse
        
        # Sanitize filename for Supabase Storage (replaces problematic characters)
        # Supabase Storage doesn't allow spaces, brackets, and other special chars in paths
        # Replace spaces and special chars with underscores, keep only alphanumeric, hyphens, dots, underscores
        original_filename = audio_file.filename or "audio.mp3"
        # Split filename and extension
        if '.' in original_filename:
            name_part, ext = original_filename.rsplit('.', 1)
            # Sanitize name part: keep only word chars (alphanumeric + underscore), hyphens
            # Replace everything else (spaces, brackets, etc.) with underscores
            sanitized_name = re.sub(r'[^\w\-]', '_', name_part)  # Keep word chars and hyphens
            sanitized_name = re.sub(r'_+', '_', sanitized_name)  # Replace multiple underscores with single
            sanitized_name = sanitized_name.strip('_')  # Remove leading/trailing underscores
            sanitized_filename = f"{sanitized_name}.{ext}" if sanitized_name else f"audio.{ext}"
        else:
            # No extension, sanitize entire filename
            sanitized_filename = re.sub(r'[^\w\-]', '_', original_filename)
            sanitized_filename = re.sub(r'_+', '_', sanitized_filename).strip('_') or "audio"
        
        storage_path = f"{user_id}/{job_id}/{sanitized_filename}"
        
        # Determine correct MIME type from file extension (don't trust upload content_type)
        ext_lower = sanitized_filename.rsplit('.', 1)[-1].lower() if '.' in sanitized_filename else ''
        mime_type_map = {
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'flac': 'audio/flac',
            'ogg': 'audio/ogg',
            'm4a': 'audio/mp4'
        }
        content_type = mime_type_map.get(ext_lower, audio_file.content_type or 'audio/mpeg')
        
        logger.info(
            "Sanitized filename for storage",
            extra={
                "original_filename": original_filename,
                "sanitized_filename": sanitized_filename,
                "storage_path": storage_path,
                "detected_content_type": content_type,
                "original_content_type": audio_file.content_type
            }
        )
        
        # Upload audio file with timeout (150s total timeout for upload + URL generation)
        try:
            audio_url = await asyncio.wait_for(
                storage_client.upload_file(
                    bucket="audio-uploads",
                    path=storage_path,
                    file_data=file_data,
                    content_type=content_type
                ),
                timeout=150.0  # 150s total timeout (120s upload + 30s URL generation)
            )
        except asyncio.TimeoutError:
            logger.error(
                "Storage upload timed out",
                extra={"job_id": job_id, "storage_path": storage_path, "file_size": len(file_data)}
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="File upload timed out. Please try again."
            )
        except RetryableError as e:
            logger.error(
                "Storage upload failed after retries",
                exc_info=e,
                extra={"job_id": job_id, "storage_path": storage_path}
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service temporarily unavailable. Please try again."
            )
        
        # Validate stop_at_stage if provided
        valid_stages = ["audio_parser", "scene_planner", "reference_generator", "prompt_generator", "video_generator", "composer"]
        if stop_at_stage and stop_at_stage not in valid_stages:
            raise ValidationError(f"Invalid stop_at_stage: {stop_at_stage}. Must be one of: {', '.join(valid_stages)}")
        
        # Validate video_model
        valid_models = ["kling_v21", "kling_v25_turbo", "hailuo_23", "wan_25_i2v", "veo_31"]
        if video_model not in valid_models:
            raise ValidationError(f"Invalid video_model: {video_model}. Must be one of: {', '.join(valid_models)}")
        
        # Create job record in database
        # Note: Using 'id' as job_id (primary key) since schema uses 'id' as PK
        # Note: Schema has 'total_cost' not 'estimated_cost', so we don't store estimated_cost
        job_data = {
            "id": job_id,  # Use generated UUID as primary key
            "user_id": user_id,
            "status": "queued",
            "audio_url": audio_url,
            "user_prompt": user_prompt,
            "progress": 0,
            "current_stage": "audio_parser",  # Set initial stage so frontend knows what's next
            "stop_at_stage": stop_at_stage,  # Store stop_at_stage for orchestrator
            "created_at": datetime.utcnow().isoformat()
        }
        
        await db_client.table("jobs").insert(job_data).execute()
        
        # Publish initial stage update so frontend knows which stage is pending
        from api_gateway.services.event_publisher import publish_event
        await publish_event(job_id, "stage_update", {
            "stage": "audio_parser",
            "status": "pending"
        })
        
        # Enqueue job to queue (pass stop_at_stage and video_model to orchestrator)
        await enqueue_job(job_id, user_id, audio_url, user_prompt, stop_at_stage, video_model, aspect_ratio)
        
        logger.info(
            "Job created and enqueued",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "estimated_cost": estimated_cost,
                "duration_minutes": duration_minutes
            }
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "estimated_cost": round(estimated_cost, 2),
            "created_at": job_data["created_at"]
        }
        
    except (ValidationError, BudgetExceededError) as e:
        raise
    except Exception as e:
        logger.error("Failed to create job", exc_info=e, extra={"job_id": job_id, "user_id": user_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job"
        )

