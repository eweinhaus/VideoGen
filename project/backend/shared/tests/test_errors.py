"""
Tests for error handling.
"""

import pytest
from uuid import UUID
from shared.errors import (
    PipelineError,
    ConfigError,
    AudioAnalysisError,
    GenerationError,
    CompositionError,
    BudgetExceededError,
    RetryableError,
    ValidationError
)


def test_pipeline_error_inheritance():
    """Test that all exceptions inherit from PipelineError."""
    assert issubclass(ConfigError, PipelineError)
    assert issubclass(AudioAnalysisError, PipelineError)
    assert issubclass(GenerationError, PipelineError)
    assert issubclass(CompositionError, PipelineError)
    assert issubclass(BudgetExceededError, PipelineError)
    assert issubclass(RetryableError, PipelineError)
    assert issubclass(ValidationError, PipelineError)


def test_pipeline_error_with_job_id():
    """Test that exceptions can include job_id."""
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    error = ConfigError("Test error", job_id=job_id, code="TEST_ERROR")
    
    assert error.message == "Test error"
    assert error.job_id == job_id
    assert error.code == "TEST_ERROR"
    assert str(error) == "Test error"


def test_exception_messages():
    """Test that exception messages are clear."""
    error = ValidationError("Invalid input provided")
    assert "Invalid input" in str(error)
    
    error = BudgetExceededError("Budget exceeded", code="BUDGET_EXCEEDED")
    assert "Budget exceeded" in str(error)
    assert error.code == "BUDGET_EXCEEDED"


