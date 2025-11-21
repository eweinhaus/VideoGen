"""
BullMQ worker process.

Processes jobs from the queue and executes the video generation pipeline.
"""

import asyncio
import json
from uuid import UUID
from decimal import Decimal
from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.errors import RetryableError, PipelineError, BudgetExceededError
from shared.logging import get_logger
from api_gateway.orchestrator import execute_pipeline
from api_gateway.services.queue_service import QUEUE_NAME

logger = get_logger(__name__)

redis_client = RedisClient()
db_client = DatabaseClient()

# Max concurrent jobs per worker (PRD: 5 per worker, 2 workers = 10 total)
MAX_CONCURRENT_JOBS = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


async def process_job(job_data: dict) -> None:
    """
    Process a single job from the queue.
    
    Handles both generation and regeneration jobs based on job_type.
    
    Args:
        job_data: Job data dictionary with job_id, user_id, and job_type
    """
    job_type = job_data.get("job_type", "generation")  # Default to generation for backward compatibility
    job_id = job_data.get("job_id")
    user_id = job_data.get("user_id")
    
    if not all([job_id, user_id]):
        logger.error("Invalid job data", extra={"job_data": job_data})
        return
    
    logger.info(
        "Processing job",
        extra={
            "job_id": job_id,
            "user_id": user_id,
            "job_type": job_type
        }
    )
    
    try:
        if job_type == "regeneration":
            await process_regeneration_job(job_data)
        else:
            await process_generation_job(job_data)
        
        logger.info("Job processed successfully", extra={"job_id": job_id, "job_type": job_type})
        
    except (BudgetExceededError, PipelineError) as e:
        logger.error("Job failed", exc_info=e, extra={"job_id": job_id, "job_type": job_type})
        # Error handling is done in respective handlers
    except RetryableError as e:
        logger.warning("Retryable error occurred", exc_info=e, extra={"job_id": job_id, "job_type": job_type})
        # Re-raise for queue retry mechanism
        raise
    except Exception as e:
        logger.error("Unexpected error processing job", exc_info=e, extra={"job_id": job_id, "job_type": job_type})
        # Mark as failed
        await db_client.table("jobs").update({
            "status": "failed",
            "error_message": f"Unexpected error: {str(e)}"
        }).eq("id", job_id).execute()


async def process_generation_job(job_data: dict) -> None:
    """
    Process a video generation job from the queue.
    
    Args:
        job_data: Job data dictionary with job_id, user_id, audio_url, user_prompt, stop_at_stage
    """
    job_id = job_data.get("job_id")
    user_id = job_data.get("user_id")
    audio_url = job_data.get("audio_url")
    user_prompt = job_data.get("user_prompt")
    stop_at_stage = job_data.get("stop_at_stage")  # Optional: for testing
    video_model = job_data.get("video_model", "kling_v21")  # Default to kling_v21 if not provided
    aspect_ratio = job_data.get("aspect_ratio", "16:9")  # Default to 16:9 if not provided
    template = job_data.get("template", "standard")  # Default to standard if not provided
    
    if not all([audio_url, user_prompt]):
        logger.error("Invalid generation job data", extra={"job_data": job_data})
        return
    
    logger.info(
        "Processing generation job",
        extra={
            "job_id": job_id,
            "user_id": user_id,
            "stop_at_stage": stop_at_stage,
            "video_model": video_model,
            "aspect_ratio": aspect_ratio,
            "template": template
        }
    )
    
    # Publish message that processing is starting
    from api_gateway.services.event_publisher import publish_event
    await publish_event(job_id, "message", {
        "text": "Starting pipeline execution...",
        "stage": "queue"
    })
    
    # Check cancellation flag before starting
    cancel_key = f"job_cancel:{job_id}"
    if await redis_client.get(cancel_key):
        logger.info("Job cancelled before processing", extra={"job_id": job_id})
        await db_client.table("jobs").update({
            "status": "failed",
            "error_message": "Job cancelled by user"
        }).eq("id", job_id).execute()
        return
    
    # Execute pipeline (pass stop_at_stage, video_model, aspect_ratio, and template)
    await execute_pipeline(job_id, audio_url, user_prompt, stop_at_stage, video_model, aspect_ratio, template)


async def process_regeneration_job(job_data: dict) -> None:
    """
    Process a clip regeneration job from the queue.
    
    Regenerates multiple clips in parallel based on user instruction.
    
    Args:
        job_data: Job data dictionary with job_id, clip_indices, user_instruction, conversation_history
    """
    from modules.clip_regenerator.process import regenerate_clip_with_recomposition
    from modules.clip_regenerator.status_manager import update_job_status
    from api_gateway.services.event_publisher import publish_event
    
    job_id = job_data.get("job_id")
    user_id = job_data.get("user_id")
    clip_indices = job_data.get("clip_indices", [])
    user_instruction = job_data.get("user_instruction")
    conversation_history = job_data.get("conversation_history", [])
    regeneration_id = job_data.get("regeneration_id")
    
    if not all([job_id, user_id, clip_indices, user_instruction]):
        logger.error("Invalid regeneration job data", extra={"job_data": job_data})
        await update_job_status(UUID(job_id), "completed")
        return
    
    logger.info(
        "Processing regeneration job",
        extra={
            "job_id": job_id,
            "user_id": user_id,
            "clip_indices": clip_indices,
            "regeneration_id": regeneration_id
        }
    )
    
    # Create event publisher wrapper
    async def event_pub(event_type: str, data: dict):
        """Wrapper for event publishing."""
        await publish_event(job_id, event_type, data)
    
    # Publish start event
    await event_pub("regeneration_started", {
        "regeneration_id": regeneration_id,
        "clip_indices": clip_indices
    })
    
    try:
        # Process all clips in parallel (like video_generator does)
        tasks = []
        for clip_index in clip_indices:
            task = regenerate_single_clip(
                job_id=UUID(job_id),
                clip_index=clip_index,
                user_instruction=user_instruction,
                user_id=UUID(user_id),
                conversation_history=conversation_history,
                event_pub=event_pub,
                regeneration_id=regeneration_id
            )
            tasks.append(task)
        
        # Wait for all clips to regenerate in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful_count = 0
        failed_count = 0
        total_cost = Decimal("0")
        
        for i, result in enumerate(results):
            clip_index = clip_indices[i]
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to regenerate clip {clip_index}",
                    exc_info=result,
                    extra={"job_id": job_id, "clip_index": clip_index}
                )
                failed_count += 1
                await event_pub("clip_regeneration_failed", {
                    "clip_index": clip_index,
                    "error": str(result)
                })
            else:
                successful_count += 1
                # Result is now a dict with cost as Decimal
                cost = result.get("cost", Decimal("0"))
                if cost:
                    total_cost += Decimal(str(cost))
        
        # Release job lock on completion
        await update_job_status(UUID(job_id), "completed")
        
        # Publish completion event
        await event_pub("regeneration_complete", {
            "regeneration_id": regeneration_id,
            "clip_indices": clip_indices,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "total_cost": float(total_cost)
        })
        
        logger.info(
            "Regeneration job completed",
            extra={
                "job_id": job_id,
                "regeneration_id": regeneration_id,
                "successful_count": successful_count,
                "failed_count": failed_count,
                "total_cost": float(total_cost)
            }
        )
        
    except Exception as e:
        logger.error(
            "Unexpected error during regeneration job",
            exc_info=e,
            extra={"job_id": job_id, "regeneration_id": regeneration_id}
        )
        # Release job lock on error
        await update_job_status(UUID(job_id), "completed")
        await event_pub("regeneration_failed", {
            "regeneration_id": regeneration_id,
            "error": str(e),
            "error_type": "unexpected"
        })


async def regenerate_single_clip(
    job_id: UUID,
    clip_index: int,
    user_instruction: str,
    user_id: UUID,
    conversation_history: list,
    event_pub: callable,
    regeneration_id: str
) -> dict:
    """
    Regenerate a single clip (used for parallel processing).
    
    Args:
        job_id: Job ID
        clip_index: Clip index to regenerate
        user_instruction: User's regeneration instruction
        user_id: User ID
        conversation_history: Conversation history for context
        event_pub: Event publisher function
        regeneration_id: Regeneration ID
    
    Returns:
        Result dictionary with cost and video_url
    """
    from modules.clip_regenerator.process import regenerate_clip_with_recomposition
    
    logger.info(
        f"Starting regeneration for clip {clip_index}",
        extra={"job_id": str(job_id), "clip_index": clip_index}
    )
    
    result = await regenerate_clip_with_recomposition(
        job_id=job_id,
        clip_index=clip_index,
        user_instruction=user_instruction,
        user_id=user_id,
        conversation_history=conversation_history,
        event_publisher=event_pub
    )
    
    # Extract cost from result (it's a RegenerationResult dataclass)
    cost = float(result.cost) if result.cost else 0.0
    video_url = result.video_output.video_url if result.video_output else None
    
    logger.info(
        f"Completed regeneration for clip {clip_index}",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "cost": cost
        }
    )
    
    # Publish individual clip completion
    await event_pub("clip_regeneration_complete", {
        "clip_index": clip_index,
        "new_clip_url": video_url,
        "cost": cost
    })
    
    # Return a dict for easier aggregation
    return {
        "cost": result.cost,
        "video_url": video_url,
        "clip_index": clip_index
    }


async def process_job_with_limit(job_data: dict) -> None:
    """
    Process job with concurrency limit.
    
    Wraps process_job() with semaphore to limit concurrent execution.
    
    Args:
        job_data: Job data dictionary
    """
    job_id = job_data.get("job_id")
    
    # Log when acquiring semaphore
    available_slots = semaphore._value
    logger.info(
        "Acquiring semaphore for job",
        extra={"job_id": job_id, "available_slots": available_slots}
    )
    
    async with semaphore:
        try:
            logger.info(
                "Processing job (semaphore acquired)",
                extra={"job_id": job_id}
            )
            await process_job(job_data)
            logger.info(
                "Job completed (semaphore released)",
                extra={"job_id": job_id}
            )
        except Exception as e:
            logger.error(
                "Job failed (semaphore released)",
                exc_info=e,
                extra={"job_id": job_id}
            )
            raise


async def worker_loop():
    """
    Main worker loop that processes jobs from the queue.
    
    This is a simplified implementation using Redis list as queue.
    In production, this would use BullMQ or a similar queue system.
    """
    logger.info("Worker started", extra={"queue_name": QUEUE_NAME})
    
    queue_key = f"{QUEUE_NAME}:queue"
    processing_key = f"{QUEUE_NAME}:processing"
    
    while True:
        try:
            # Pop job from queue (blocking with timeout)
            logger.info(f"Waiting for job from queue: {queue_key} (timeout=5s)")
            try:
                job_json = await redis_client.client.brpop(queue_key, timeout=5)
            except Exception as e:
                logger.error(f"Error during brpop: {e}", exc_info=e)
                await asyncio.sleep(5)
                continue
            
            if job_json:
                logger.info(f"Job popped from queue: {queue_key}")
                # job_json is a tuple: (queue_key, job_data)
                job_data_str = job_json[1]
                try:
                    job_data = json.loads(job_data_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse job data JSON: {e}", extra={"job_data_str": job_data_str[:200]})
                    continue
                
                job_id = job_data.get("job_id")
                logger.info(
                    f"Parsed job data for job {job_id}",
                    extra={
                        "job_id": job_id,
                        "has_audio_url": bool(job_data.get("audio_url")),
                        "has_user_prompt": bool(job_data.get("user_prompt")),
                        "stop_at_stage": job_data.get("stop_at_stage")
                    }
                )
                
                # Publish message that worker picked up the job
                from api_gateway.services.event_publisher import publish_event
                await publish_event(job_id, "message", {
                    "text": "Worker picked up job, starting pipeline...",
                    "stage": "queue"
                })
                
                # Move to processing set
                await redis_client.client.sadd(processing_key, job_id)
                
                try:
                    # Process job with concurrency limit
                    await process_job_with_limit(job_data)
                finally:
                    # Remove from processing set
                    await redis_client.client.srem(processing_key, job_id)
                    
                    # Remove job data
                    job_data_key = f"{QUEUE_NAME}:job:{job_id}"
                    await redis_client.client.delete(job_data_key)
            
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled")
            break
        except Exception as e:
            logger.error("Error in worker loop", exc_info=e, extra={"queue_key": queue_key})
            await asyncio.sleep(5)  # Wait before retrying


async def main():
    """Main entry point for worker."""
    try:
        await worker_loop()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error("Worker crashed", exc_info=e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
