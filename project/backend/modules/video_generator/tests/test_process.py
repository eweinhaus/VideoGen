"""
Unit tests for video generator process module.

Tests parallel generation, retry logic, budget enforcement, and partial success handling.
"""
import pytest
import asyncio
import sys
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
from uuid import UUID, uuid4
import os

from shared.models.video import ClipPrompts, ClipPrompt, Clip
from shared.errors import BudgetExceededError, PipelineError, RetryableError

# Import process module
import modules.video_generator.process
from modules.video_generator.process import process


# Test fixtures
@pytest.fixture
def sample_job_id():
    """Create a sample job ID."""
    return uuid4()


@pytest.fixture
def sample_clip_prompt():
    """Create a sample ClipPrompt for testing."""
    return ClipPrompt(
        clip_index=0,
        prompt="A beautiful sunset over the ocean",
        negative_prompt="blurry, low quality",
        duration=5.0,
        scene_reference_url="https://example.com/image.jpg",
        character_reference_urls=[],
        metadata={}
    )


@pytest.fixture
def sample_clip_prompts(sample_job_id, sample_clip_prompt):
    """Create sample ClipPrompts with multiple clips."""
    clip_prompts = [
        ClipPrompt(
            clip_index=i,
            prompt=f"Clip {i} prompt",
            negative_prompt="blurry, low quality",
            duration=5.0 + i,
            scene_reference_url=f"https://example.com/image_{i}.jpg" if i % 2 == 0 else None,
            character_reference_urls=[],
            metadata={}
        )
        for i in range(6)
    ]
    return ClipPrompts(
        job_id=sample_job_id,
        clip_prompts=clip_prompts,
        total_clips=6,
        generation_time=0.0
    )


@pytest.fixture
def sample_successful_clip():
    """Create a sample successful Clip."""
    return Clip(
        clip_index=0,
        video_url="https://example.com/video.mp4",
        actual_duration=5.0,
        target_duration=5.0,
        duration_diff=0.0,
        status="success",
        cost=Decimal("0.10"),
        retry_count=0,
        generation_time=10.0
    )


@pytest.mark.asyncio
async def test_process_budget_not_exceeded(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test process when budget is not exceeded."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.50"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make generate_video_clip return different clips for each call
        clips = [
            Clip(
                clip_index=i,
                video_url=f"https://example.com/video_{i}.mp4",
                actual_duration=5.0,
                target_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                retry_count=0,
                generation_time=10.0
            )
            for i in range(3)
        ]
        
        async def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            return clips[clip_prompt.clip_index]
        
        mock_generate.side_effect = generate_side_effect
        
        # Patch the function in the process module's namespace
        setattr(modules.video_generator.process, 'generate_video_clip', mock_generate)
        
        # Create ClipPrompts with 3 clips
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=sample_clip_prompts.clip_prompts[:3],
            total_clips=3,
            generation_time=0.0
        )
        
        # Call process
        result = await process(sample_job_id, clip_prompts)
        
        # Verify results
        assert result.job_id == sample_job_id
        assert len(result.clips) == 3
        assert result.successful_clips == 3
        assert result.failed_clips == 0
        assert result.total_clips == 3
        assert result.total_cost == Decimal("0.30")  # 3 * 0.10
        
        # Verify budget check was called
        mock_estimate.assert_called_once()
        mock_tracker.get_total_cost.assert_called_once_with(sample_job_id)
        mock_budget.assert_called()


@pytest.mark.asyncio
async def test_process_budget_exceeded(sample_job_id, sample_clip_prompts):
    """Test process raises BudgetExceededError when budget would be exceeded."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("modules.video_generator.process.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks - budget exceeded
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("2000.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("1.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_settings_obj.environment = "development"
        
        # Call process - should raise BudgetExceededError
        with pytest.raises(BudgetExceededError) as exc_info:
            await process(sample_job_id, sample_clip_prompts)
        
        # Verify error message
        assert "would exceed budget" in str(exc_info.value).lower()
        
        # Verify budget check was called
        mock_estimate.assert_called_once()
        mock_tracker.get_total_cost.assert_called_once_with(sample_job_id)


@pytest.mark.asyncio
async def test_process_parallel_generation(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test parallel generation of multiple clips."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        
        # Create multiple successful clips
        clips = [
            Clip(
                clip_index=i,
                video_url=f"https://example.com/video_{i}.mp4",
                actual_duration=5.0,
                target_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                retry_count=0,
                generation_time=10.0
            )
            for i in range(6)
        ]
        
        # Make generate_video_clip return different clips based on clip_index
        async def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            return clips[clip_prompt.clip_index]
        
        mock_generate.side_effect = generate_side_effect
        mock_settings_obj.environment = "development"
        
        # Call process
        result = await process(sample_job_id, sample_clip_prompts)
        
        # Verify all clips generated
        assert len(result.clips) == 6
        assert result.successful_clips == 6
        assert result.failed_clips == 0
        assert result.total_clips == 6
        
        # Verify generate_video_clip was called for each clip
        assert mock_generate.call_count == 6


@pytest.mark.asyncio
async def test_process_retry_logic(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test retry logic with exponential backoff."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("modules.video_generator.process.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image") as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip") as mock_generate, \
         patch("asyncio.sleep") as mock_sleep, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make generate_video_clip fail twice with RetryableError, then succeed
        call_count = 0
        async def generate_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RetryableError("Rate limit error")
            return sample_successful_clip
        
        mock_generate.side_effect = generate_side_effect
        
        # Create ClipPrompts with 1 clip
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=[sample_clip_prompts.clip_prompts[0]],
            total_clips=1,
            generation_time=0.0
        )
        
        # Call process
        result = await process(sample_job_id, clip_prompts)
        
        # Verify clip succeeded after retries
        assert len(result.clips) == 1
        assert result.successful_clips == 1
        
        # Verify retry delays (2s, 4s)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)  # First retry: 2s
        mock_sleep.assert_any_call(4.0)  # Second retry: 4s
        
        # Verify generate_video_clip was called 3 times (initial + 2 retries)
        assert mock_generate.call_count == 3


@pytest.mark.asyncio
async def test_process_retry_exhausted(sample_job_id, sample_clip_prompts):
    """Test retry logic when all retries are exhausted."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("modules.video_generator.process.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image") as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip") as mock_generate, \
         patch("asyncio.sleep") as mock_sleep, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make generate_video_clip always fail with RetryableError
        mock_generate.side_effect = RetryableError("Rate limit error")
        
        # Create ClipPrompts with 1 clip (will fail, but we need 3 minimum)
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=[sample_clip_prompts.clip_prompts[0]],
            total_clips=1,
            generation_time=0.0
        )
        
        # Call process - should raise PipelineError (insufficient clips)
        with pytest.raises(PipelineError) as exc_info:
            await process(sample_job_id, clip_prompts)
        
        # Verify error message
        assert "Insufficient clips" in str(exc_info.value)
        
        # Verify all retries attempted (3 attempts)
        assert mock_generate.call_count == 3
        assert mock_sleep.call_count == 2  # 2 retries (attempts 1 and 2)


@pytest.mark.asyncio
async def test_process_partial_success(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test partial success handling (some clips fail, but ≥3 succeed)."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make some clips succeed, some fail
        def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            if clip_prompt.clip_index < 3:
                # First 3 clips succeed
                return Clip(
                    clip_index=clip_prompt.clip_index,
                    video_url=f"https://example.com/video_{clip_prompt.clip_index}.mp4",
                    actual_duration=5.0,
                    target_duration=5.0,
                    duration_diff=0.0,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=10.0
                )
            else:
                # Remaining clips fail
                raise GenerationError("Generation failed")
        
        mock_generate.side_effect = generate_side_effect
        
        # Call process
        result = await process(sample_job_id, sample_clip_prompts)
        
        # Verify partial success (3 successful, 3 failed)
        assert len(result.clips) == 3
        assert result.successful_clips == 3
        assert result.failed_clips == 3
        assert result.total_clips == 6  # Input count


@pytest.mark.asyncio
async def test_process_insufficient_clips(sample_job_id, sample_clip_prompts):
    """Test PipelineError when <3 clips generated successfully."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make only 2 clips succeed
        def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            if clip_prompt.clip_index < 2:
                return Clip(
                    clip_index=clip_prompt.clip_index,
                    video_url=f"https://example.com/video_{clip_prompt.clip_index}.mp4",
                    actual_duration=5.0,
                    target_duration=5.0,
                    duration_diff=0.0,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=10.0
                )
            else:
                raise GenerationError("Generation failed")
        
        mock_generate.side_effect = generate_side_effect
        
        # Call process - should raise PipelineError
        with pytest.raises(PipelineError) as exc_info:
            await process(sample_job_id, sample_clip_prompts)
        
        # Verify error message
        assert "Insufficient clips" in str(exc_info.value)
        assert "minimum required" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_process_image_download_failure(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test handling when image download fails (proceeds with text-only)."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = None  # Image download fails
        mock_generate.return_value = sample_successful_clip
        mock_settings_obj.environment = "development"
        
        # Create ClipPrompts with 3 clips (all have scene_reference_url)
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=sample_clip_prompts.clip_prompts[:3],
            total_clips=3,
            generation_time=0.0
        )
        
        # Call process
        result = await process(sample_job_id, clip_prompts)
        
        # Verify clips generated successfully (text-only)
        assert len(result.clips) == 3
        assert result.successful_clips == 3
        
        # Verify generate_video_clip was called with None for image_url
        assert mock_generate.call_count == 3
        for call in mock_generate.call_args_list:
            assert call.kwargs["image_url"] is None


@pytest.mark.asyncio
async def test_process_concurrency_control(sample_job_id, sample_clip_prompts, sample_successful_clip):
    """Test concurrency control with semaphore."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("modules.video_generator.process.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image") as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip") as mock_generate, \
         patch("os.getenv") as mock_getenv, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_getenv.return_value = "2"  # Set concurrency to 2
        mock_settings_obj.environment = "development"
        
        # Track concurrent calls
        concurrent_calls = []
        call_lock = asyncio.Lock()
        
        async def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            async with call_lock:
                concurrent_calls.append(len(concurrent_calls))
            # Simulate some work
            await asyncio.sleep(0.1)
            return Clip(
                clip_index=clip_prompt.clip_index,
                video_url=f"https://example.com/video_{clip_prompt.clip_index}.mp4",
                actual_duration=5.0,
                target_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                retry_count=0,
                generation_time=10.0
            )
        
        mock_generate.side_effect = generate_side_effect
        
        # Create ClipPrompts with 6 clips
        # Call process
        result = await process(sample_job_id, sample_clip_prompts)
        
        # Verify all clips generated
        assert len(result.clips) == 6
        assert result.successful_clips == 6
        
        # Verify concurrency was controlled (semaphore limits to 2)
        # Note: This is a simplified test - actual concurrency verification
        # would require more sophisticated timing tests


@pytest.mark.asyncio
async def test_process_cost_calculation(sample_job_id, sample_clip_prompts):
    """Test cost calculation and mid-generation budget check."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(side_effect=[
            Decimal("0.00"),  # Initial check
            Decimal("2001.00")  # After generation (exceeded budget)
        ])
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Create clips with different costs
        clips = [
            Clip(
                clip_index=i,
                video_url=f"https://example.com/video_{i}.mp4",
                actual_duration=5.0,
                target_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal(f"0.{i+1}0"),  # 0.10, 0.20, 0.30
                retry_count=0,
                generation_time=10.0
            )
            for i in range(3)
        ]
        
        def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            return clips[clip_prompt.clip_index]
        
        mock_generate.side_effect = generate_side_effect
        
        # Create ClipPrompts with 3 clips
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=sample_clip_prompts.clip_prompts[:3],
            total_clips=3,
            generation_time=0.0
        )
        
        # Call process
        result = await process(sample_job_id, clip_prompts)
        
        # Verify cost calculation
        expected_total = Decimal("0.10") + Decimal("0.20") + Decimal("0.30")
        assert result.total_cost == expected_total
        
        # Verify budget check was called twice (pre-flight and mid-generation)
        assert mock_tracker.get_total_cost.call_count == 2


@pytest.mark.asyncio
async def test_process_min_clips_configurable(sample_job_id, sample_clip_prompts):
    """Test configurable minimum clips via environment variable."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("modules.video_generator.process.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image") as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip") as mock_generate, \
         patch("os.getenv") as mock_getenv, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Set minimum clips to 5
        def getenv_side_effect(key, default=None):
            if key == "VIDEO_GENERATOR_MIN_CLIPS":
                return "5"
            return default
        
        mock_getenv.side_effect = getenv_side_effect
        
        # Make only 4 clips succeed
        def generate_side_effect(clip_prompt, image_url, settings, job_id, environment):
            if clip_prompt.clip_index < 4:
                return Clip(
                    clip_index=clip_prompt.clip_index,
                    video_url=f"https://example.com/video_{clip_prompt.clip_index}.mp4",
                    actual_duration=5.0,
                    target_duration=5.0,
                    duration_diff=0.0,
                    status="success",
                    cost=Decimal("0.10"),
                    retry_count=0,
                    generation_time=10.0
                )
            else:
                raise GenerationError("Generation failed")
        
        mock_generate.side_effect = generate_side_effect
        
        # Call process - should raise PipelineError (4 < 5)
        with pytest.raises(PipelineError) as exc_info:
            await process(sample_job_id, sample_clip_prompts)
        
        # Verify error message includes minimum (5)
        assert "Insufficient clips" in str(exc_info.value)
        assert "5" in str(exc_info.value)  # Minimum clips


@pytest.mark.asyncio
async def test_process_non_retryable_error(sample_job_id, sample_clip_prompts):
    """Test handling of non-retryable errors (returns None immediately)."""
    with patch("modules.video_generator.config.get_generation_settings") as mock_settings, \
         patch("modules.video_generator.cost_estimator.estimate_total_cost") as mock_estimate, \
         patch("shared.cost_tracking.cost_tracker") as mock_tracker, \
         patch("api_gateway.services.budget_helpers.get_budget_limit") as mock_budget, \
         patch("modules.video_generator.image_handler.download_and_upload_image", new_callable=AsyncMock) as mock_image, \
         patch("modules.video_generator.generator.generate_video_clip", new_callable=AsyncMock) as mock_generate, \
         patch("shared.config.settings") as mock_settings_obj:
        
        # Setup mocks
        mock_settings.return_value = {"resolution": "1024x576", "fps": 30}
        mock_estimate.return_value = Decimal("1.00")
        mock_tracker.get_total_cost = AsyncMock(return_value=Decimal("0.00"))
        mock_budget.return_value = Decimal("2000.00")
        mock_image.return_value = "https://example.com/image.jpg"
        mock_settings_obj.environment = "development"
        
        # Make generate_video_clip raise non-retryable error
        from shared.errors import GenerationError
        mock_generate.side_effect = GenerationError("Invalid input")
        
        # Create ClipPrompts with 1 clip (will fail, but we need 3 minimum)
        clip_prompts = ClipPrompts(
            job_id=sample_job_id,
            clip_prompts=[sample_clip_prompts.clip_prompts[0]],
            total_clips=1,
            generation_time=0.0
        )
        
        # Call process - should raise PipelineError (insufficient clips)
        with pytest.raises(PipelineError):
            await process(sample_job_id, clip_prompts)
        
        # Verify generate_video_clip was called only once (no retries for non-retryable)
        assert mock_generate.call_count == 1

