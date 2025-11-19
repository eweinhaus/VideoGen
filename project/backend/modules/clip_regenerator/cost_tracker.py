"""
Cost tracking for clip regenerations.

Tracks regeneration costs in clip_regenerations table and updates job total_cost.
"""
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID

from shared.database import DatabaseClient
from shared.logging import get_logger
from shared.errors import ValidationError

logger = get_logger("clip_regenerator.cost_tracker")

db_client = DatabaseClient()


async def track_regeneration_cost(
    job_id: UUID,
    clip_index: int,
    original_prompt: str,
    modified_prompt: str,
    user_instruction: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    cost: Decimal = Decimal("0.00"),
    status: str = "completed"
) -> None:
    """
    Track regeneration cost in clip_regenerations table.
    
    Also updates job.total_cost atomically.
    
    Args:
        job_id: Job ID
        clip_index: Index of regenerated clip
        original_prompt: Original prompt before modification
        modified_prompt: Modified prompt after LLM/template transformation
        user_instruction: User's modification instruction
        conversation_history: Optional conversation history
        cost: Regeneration cost (LLM + video generation)
        status: Regeneration status ("completed" or "failed")
        
    Raises:
        ValidationError: If job not found or invalid data
    """
    if status not in ["completed", "failed"]:
        raise ValidationError(f"Invalid status: {status}. Must be 'completed' or 'failed'")
    
    try:
        # Insert regeneration record
        regeneration_record = {
            "job_id": str(job_id),
            "clip_index": clip_index,
            "original_prompt": original_prompt,
            "modified_prompt": modified_prompt,
            "user_instruction": user_instruction,
            "conversation_history": conversation_history if conversation_history else None,
            "cost": float(cost),  # Supabase stores as numeric/float
            "status": status
        }
        
        await db_client.table("clip_regenerations").insert(regeneration_record).execute()
        
        logger.info(
            f"Tracked regeneration cost",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "cost": float(cost),
                "status": status
            }
        )
        
        # Update job.total_cost atomically
        # Get current total_cost
        # Use fallback pattern for .single() method
        eq_builder = db_client.table("jobs").select("total_cost").eq("id", str(job_id))
        if hasattr(eq_builder, 'single'):
            try:
                job_result = await eq_builder.single().execute()
            except AttributeError:
                job_result = await eq_builder.limit(1).execute()
        else:
            job_result = await eq_builder.limit(1).execute()
        
        if not job_result.data:
            raise ValidationError(f"Job {job_id} not found")
        
        # Handle both dict (from .single()) and list (from .limit(1)) results
        job_data = job_result.data if isinstance(job_result.data, dict) else (job_result.data[0] if job_result.data else {})
        current_total = Decimal(str(job_data.get("total_cost", 0)))
        new_total = current_total + cost
        
        # Update job total_cost
        await db_client.table("jobs").update({
            "total_cost": float(new_total)
        }).eq("id", str(job_id)).execute()
        
        logger.info(
            f"Updated job total_cost",
            extra={
                "job_id": str(job_id),
                "previous_total": float(current_total),
                "regeneration_cost": float(cost),
                "new_total": float(new_total)
            }
        )
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to track regeneration cost: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index},
            exc_info=True
        )
        # Don't raise error - cost tracking failure shouldn't block regeneration
        # Just log and continue
        pass


async def get_regeneration_history(
    job_id: UUID,
    clip_index: Optional[int] = None
) -> List[Dict]:
    """
    Get regeneration history for a job or specific clip.
    
    Args:
        job_id: Job ID
        clip_index: Optional clip index to filter by
        
    Returns:
        List of regeneration records
    """
    try:
        query = db_client.table("clip_regenerations").select("*").eq("job_id", str(job_id))
        
        if clip_index is not None:
            query = query.eq("clip_index", clip_index)
        
        query = query.order("created_at", desc=True)
        
        result = await query.execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(
            f"Failed to get regeneration history: {e}",
            extra={"job_id": str(job_id), "clip_index": clip_index},
            exc_info=True
        )
        return []

