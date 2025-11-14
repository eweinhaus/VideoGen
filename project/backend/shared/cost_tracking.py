"""
Cost tracking utilities.

Track API costs per job and enforce budget limits.
"""

import asyncio
from decimal import Decimal
from typing import Optional
from uuid import UUID

from shared.database import db
from shared.errors import BudgetExceededError, RetryableError
from shared.logging import get_logger

logger = get_logger("cost_tracking")


class CostTracker:
    """Cost tracker for API calls with budget enforcement."""
    
    def __init__(self):
        """Initialize cost tracker."""
        # Locks per job_id for concurrent-safe operations
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._lock_manager = asyncio.Lock()  # Lock for managing the locks dict
    
    async def _get_lock(self, job_id: UUID) -> asyncio.Lock:
        """Get or create lock for a job_id."""
        async with self._lock_manager:
            if job_id not in self._locks:
                self._locks[job_id] = asyncio.Lock()
            return self._locks[job_id]
    
    async def track_cost(
        self,
        job_id: UUID,
        stage_name: str,
        api_name: str,
        cost: Decimal
    ) -> None:
        """
        Track a cost for a job.
        
        Args:
            job_id: Job ID
            stage_name: Pipeline stage name
            api_name: API name (e.g., "whisper", "gpt-4o", "sdxl", "svd")
            cost: Cost in USD
            
        Raises:
            RetryableError: If database operation fails
            ValidationError: If cost is negative
        """
        from shared.errors import ValidationError
        
        # Validate cost
        if cost < 0:
            raise ValidationError(f"Cost cannot be negative: {cost}", job_id=job_id)
        
        lock = await self._get_lock(job_id)
        
        async with lock:
            try:
                # Insert into job_costs table
                cost_record = {
                    "job_id": str(job_id),
                    "stage_name": stage_name,
                    "api_name": api_name,
                    "cost": float(cost),  # Supabase stores as numeric/float
                    "timestamp": "now()"
                }
                
                await db.table("job_costs").insert(cost_record).execute()
                
                # Update jobs.total_cost atomically using database increment
                # Use RPC function or raw SQL for atomic increment
                # For now, use a safer approach: get current, calculate new, update with condition
                job_result = await db.table("jobs").select("total_cost").eq("id", str(job_id)).execute()
                
                if job_result.data:
                    current_total = Decimal(str(job_result.data[0].get("total_cost", 0)))
                    new_total = current_total + cost
                    
                    # Update total_cost - this is still not fully atomic but better with lock
                    # TODO: Use Supabase RPC function for true atomic increment
                    await db.table("jobs").update({
                        "total_cost": float(new_total)
                    }).eq("id", str(job_id)).execute()
                else:
                    logger.warning(f"Job {job_id} not found when tracking cost")
                
                logger.info(
                    f"Tracked cost for job {job_id}",
                    extra={
                        "job_id": str(job_id),
                        "stage_name": stage_name,
                        "api_name": api_name,
                        "cost": float(cost)
                    }
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to track cost for job {job_id}: {str(e)}",
                    extra={"job_id": str(job_id), "error": str(e)}
                )
                raise RetryableError(f"Failed to track cost: {str(e)}") from e
    
    async def get_total_cost(self, job_id: UUID) -> Decimal:
        """
        Get total cost for a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Total cost in USD
            
        Raises:
            RetryableError: If database operation fails
        """
        try:
            job_result = await db.table("jobs").select("total_cost").eq("id", str(job_id)).execute()
            
            if job_result.data:
                return Decimal(str(job_result.data[0].get("total_cost", 0)))
            
            return Decimal("0.00")
            
        except Exception as e:
            logger.error(
                f"Failed to get total cost for job {job_id}: {str(e)}",
                extra={"job_id": str(job_id), "error": str(e)}
            )
            raise RetryableError(f"Failed to get total cost: {str(e)}") from e
    
    async def check_budget(
        self,
        job_id: UUID,
        new_cost: Decimal,
        limit: Decimal = Decimal("2000.00")
    ) -> bool:
        """
        Check if adding new_cost would exceed budget limit.
        
        Args:
            job_id: Job ID
            new_cost: Cost to add
            limit: Budget limit (default: $2000.00)
            
        Returns:
            True if within budget, False if would exceed
            
        Raises:
            RetryableError: If database operation fails
        """
        try:
            current_total = await self.get_total_cost(job_id)
            projected_total = current_total + new_cost
            
            return projected_total <= limit
            
        except Exception as e:
            logger.error(
                f"Failed to check budget for job {job_id}: {str(e)}",
                extra={"job_id": str(job_id), "error": str(e)}
            )
            raise RetryableError(f"Failed to check budget: {str(e)}") from e
    
    async def enforce_budget_limit(
        self,
        job_id: UUID,
        limit: Decimal = Decimal("2000.00")
    ) -> None:
        """
        Enforce budget limit, raising BudgetExceededError if exceeded.
        
        Args:
            job_id: Job ID
            limit: Budget limit (default: $2000.00)
            
        Raises:
            BudgetExceededError: If budget limit is exceeded
            RetryableError: If database operation fails
        """
        try:
            current_total = await self.get_total_cost(job_id)
            
            if current_total > limit:
                error_msg = (
                    f"Budget limit of ${limit} exceeded for job {job_id}. "
                    f"Current total: ${current_total}"
                )
                logger.error(
                    error_msg,
                    extra={
                        "job_id": str(job_id),
                        "current_total": float(current_total),
                        "limit": float(limit)
                    }
                )
                raise BudgetExceededError(error_msg, job_id=job_id, code="BUDGET_EXCEEDED")
            
        except BudgetExceededError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to enforce budget limit for job {job_id}: {str(e)}",
                extra={"job_id": str(job_id), "error": str(e)}
            )
            raise RetryableError(f"Failed to enforce budget limit: {str(e)}") from e


# Singleton instance
cost_tracker = CostTracker()
