"""
Error handling.

Custom exception classes for consistent error handling across the pipeline.
"""

from typing import Optional
from uuid import UUID


class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    
    def __init__(
        self,
        message: str,
        job_id: Optional[UUID] = None,
        code: Optional[str] = None
    ):
        """
        Initialize pipeline error.
        
        Args:
            message: Error message
            job_id: Optional job ID associated with the error
            code: Optional error code for categorization
        """
        self.message = message
        self.job_id = job_id
        self.code = code
        super().__init__(self.message)


class ConfigError(PipelineError):
    """Configuration errors (missing env vars, invalid settings)."""
    pass


class AudioAnalysisError(PipelineError):
    """Audio analysis failures."""
    pass


class GenerationError(PipelineError):
    """AI generation failures (images, video)."""
    pass


class CompositionError(PipelineError):
    """Video composition failures."""
    pass


class BudgetExceededError(PipelineError):
    """Cost exceeds budget limit."""
    pass


class RetryableError(PipelineError):
    """Error that can be retried."""
    pass


class ValidationError(PipelineError):
    """Input validation errors."""
    pass


class RateLimitError(PipelineError):
    """Rate limit exceeded errors."""
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        job_id: Optional[UUID] = None,
        code: Optional[str] = None
    ):
        """
        Initialize rate limit error.
        
        Args:
            message: Error message
            retry_after: Seconds until retry is allowed
            job_id: Optional job ID associated with the error
            code: Optional error code for categorization
        """
        self.retry_after = retry_after
        super().__init__(message, job_id, code)


__all__ = [
    "PipelineError",
    "ConfigError",
    "AudioAnalysisError",
    "GenerationError",
    "CompositionError",
    "BudgetExceededError",
    "RetryableError",
    "ValidationError",
    "RateLimitError",
]
