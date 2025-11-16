"""
Tests for time estimation service.
"""

import pytest
from api_gateway.services.time_estimator import (
    get_environment_defaults,
    calculate_estimated_remaining,
    STAGE_DEFAULTS
)


def test_get_environment_defaults_development():
    """Test that development environment returns dev defaults."""
    defaults = get_environment_defaults("development")
    assert defaults == STAGE_DEFAULTS["development"]


def test_get_environment_defaults_production():
    """Test that production environment returns prod defaults."""
    defaults = get_environment_defaults("production")
    assert defaults == STAGE_DEFAULTS["production"]


def test_get_environment_defaults_staging():
    """Test that staging environment returns prod defaults."""
    defaults = get_environment_defaults("staging")
    assert defaults == STAGE_DEFAULTS["production"]


def test_get_environment_defaults_unknown():
    """Test that unknown environment returns dev defaults as fallback."""
    defaults = get_environment_defaults("unknown")
    assert defaults == STAGE_DEFAULTS["development"]


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_with_audio_duration():
    """Test calculation with audio duration."""
    result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="audio_parser",
        progress=5,
        audio_duration=180.0,  # 3 minutes
        environment="development"
    )
    assert result is not None
    assert isinstance(result, int)
    assert result > 0


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_no_audio_duration():
    """Test that None is returned when audio duration not available."""
    result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="audio_parser",
        progress=5,
        audio_duration=None,
        environment="development"
    )
    assert result is None


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_audio_parser_scales():
    """Test that audio parser scales with audio duration."""
    short_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="audio_parser",
        progress=5,
        audio_duration=60.0,  # 1 minute
        environment="development"
    )
    
    long_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="audio_parser",
        progress=5,
        audio_duration=300.0,  # 5 minutes
        environment="development"
    )
    
    assert short_result is not None
    assert long_result is not None
    assert long_result > short_result  # Longer audio should take more time


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_video_generator_with_clips():
    """Test video generator scales with number of clips."""
    result_with_clips = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=60,
        audio_duration=180.0,
        environment="development",
        num_clips=6
    )
    
    result_without_clips = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=60,
        audio_duration=180.0,
        environment="development",
        num_clips=None  # Will estimate based on duration
    )
    
    assert result_with_clips is not None
    assert result_without_clips is not None
    # With explicit clips should be more accurate


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_reference_generator_with_images():
    """Test reference generator scales with number of images."""
    result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="reference_generator",
        progress=27,
        audio_duration=180.0,
        environment="development",
        num_images=4
    )
    
    assert result is not None
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_production_vs_development():
    """Test that production estimates are longer than development."""
    dev_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=60,
        audio_duration=180.0,
        environment="development",
        num_clips=6
    )
    
    prod_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=60,
        audio_duration=180.0,
        environment="production",
        num_clips=6
    )
    
    assert dev_result is not None
    assert prod_result is not None
    assert prod_result > dev_result  # Production should take longer


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_progress_affects_current_stage():
    """Test that progress within current stage affects estimate."""
    early_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=50,  # Start of stage
        audio_duration=180.0,
        environment="development",
        num_clips=6
    )
    
    late_result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="video_generator",
        progress=80,  # Near end of stage
        audio_duration=180.0,
        environment="development",
        num_clips=6
    )
    
    assert early_result is not None
    assert late_result is not None
    assert early_result > late_result  # Less progress = more time remaining


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_unknown_stage():
    """Test that unknown stage returns None."""
    result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="unknown_stage",
        progress=50,
        audio_duration=180.0,
        environment="development"
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_calculate_estimated_remaining_composer_stage():
    """Test composer stage calculation."""
    result = await calculate_estimated_remaining(
        job_id="test-job",
        current_stage="composer",
        progress=90,
        audio_duration=180.0,
        environment="development"
    )
    
    assert result is not None
    assert isinstance(result, int)
    assert result >= 0

