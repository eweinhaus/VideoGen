"""
Upload endpoint.

Handles audio file upload and job creation.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from mutagen import File as MutagenFile
from shared.storage import StorageClient
from shared.database import DatabaseClient
from shared.validation import validate_audio_file, validate_prompt
from shared.errors import ValidationError, BudgetExceededError
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
    current_user: dict = Depends(get_current_user)
):
    """
    Upload audio file and create video generation job.
    
    Args:
        audio_file: Audio file (MP3/WAV/FLAC, ≤10MB)
        user_prompt: Creative prompt (50-500 characters)
        current_user: Current authenticated user
        
    Returns:
        Job creation response with job_id, status, estimated_cost
    """
    user_id = current_user["user_id"]
    job_id = str(uuid.uuid4())
    
    try:
        # Validate file
        validate_audio_file(audio_file.file, max_size_mb=10)
        
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
        storage_path = f"{user_id}/{job_id}/{audio_file.filename}"
        audio_url = await storage_client.upload_file(
            bucket="audio-uploads",
            path=storage_path,
            file_obj=audio_file.file,
            content_type=audio_file.content_type
        )
        
        # Create job record in database
        # Note: Using 'id' as job_id (primary key) since schema uses 'id' as PK
        job_data = {
            "id": job_id,  # Use generated UUID as primary key
            "user_id": user_id,
            "status": "queued",
            "audio_url": audio_url,
            "user_prompt": user_prompt,
            "estimated_cost": estimated_cost,
            "progress": 0,
            "created_at": datetime.utcnow().isoformat()
        }
        
        await db_client.table("jobs").insert(job_data).execute()
        
        # Enqueue job to queue
        await enqueue_job(job_id, user_id, audio_url, user_prompt)
        
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

