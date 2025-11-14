"""
BullMQ worker process.

Processes jobs from the queue and executes the video generation pipeline.
"""

import asyncio
import json
from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.errors import RetryableError, PipelineError, BudgetExceededError
from shared.logging import get_logger
from api_gateway.orchestrator import execute_pipeline
from api_gateway.services.queue_service import QUEUE_NAME

logger = get_logger(__name__)

redis_client = RedisClient()
db_client = DatabaseClient()

# Max concurrent jobs per worker (PRD: 3 per worker, 2 workers = 6 total)
MAX_CONCURRENT_JOBS = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


async def process_job(job_data: dict) -> None:
    """
    Process a single job from the queue.
    
    Args:
        job_data: Job data dictionary with job_id, user_id, audio_url, user_prompt
    """
    job_id = job_data.get("job_id")
    user_id = job_data.get("user_id")
    audio_url = job_data.get("audio_url")
    user_prompt = job_data.get("user_prompt")
    
    if not all([job_id, user_id, audio_url, user_prompt]):
        logger.error("Invalid job data", extra={"job_data": job_data})
        return
    
    logger.info("Processing job", extra={"job_id": job_id, "user_id": user_id})
    
    try:
        # Check cancellation flag before starting
        cancel_key = f"job_cancel:{job_id}"
        if await redis_client.get(cancel_key):
            logger.info("Job cancelled before processing", extra={"job_id": job_id})
            await db_client.table("jobs").update({
                "status": "failed",
                "error_message": "Job cancelled by user"
            }).eq("id", job_id).execute()
            return
        
        # Execute pipeline
        await execute_pipeline(job_id, audio_url, user_prompt)
        
        logger.info("Job processed successfully", extra={"job_id": job_id})
        
    except (BudgetExceededError, PipelineError) as e:
        logger.error("Job failed", exc_info=e, extra={"job_id": job_id})
        # Error handling is done in orchestrator.handle_pipeline_error
    except RetryableError as e:
        logger.warning("Retryable error occurred", exc_info=e, extra={"job_id": job_id})
        # Re-raise for queue retry mechanism
        raise
    except Exception as e:
        logger.error("Unexpected error processing job", exc_info=e, extra={"job_id": job_id})
        # Mark as failed
        await db_client.table("jobs").update({
            "status": "failed",
            "error_message": f"Unexpected error: {str(e)}"
        }).eq("id", job_id).execute()


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
            job_json = await redis_client.client.brpop(queue_key, timeout=5)
            
            if job_json:
                # job_json is a tuple: (queue_key, job_data)
                job_data_str = job_json[1]
                job_data = json.loads(job_data_str)
                
                job_id = job_data.get("job_id")
                
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
            logger.error("Error in worker loop", exc_info=e)
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
