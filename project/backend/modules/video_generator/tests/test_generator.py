"""
Unit tests for video generator module.

Tests Replicate API integration, error handling, and video processing.
"""
import pytest
import asyncio
import subprocess
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
from uuid import UUID, uuid4
import time

from shared.models.video import ClipPrompt, Clip
from shared.errors import RetryableError, GenerationError
from replicate.exceptions import ModelError
from modules.video_generator.generator import (
    generate_video_clip,
    calculate_num_frames,
    get_video_duration,
    download_video_from_url,
    parse_retry_after_header,
    get_prediction_cost
)


# Test fixtures
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
def sample_job_id():
    """Create a sample job ID."""
    return uuid4()


@pytest.fixture
def sample_settings():
    """Create sample generation settings."""
    return {
        "resolution": "1024x576",
        "fps": 30,
        "motion_bucket_id": 127,
        "steps": 25,
        "max_duration": 8.0
    }


@pytest.fixture
def mock_video_bytes():
    """Create mock video bytes."""
    return b"fake video content" * 1000


# Helper function tests
class TestHelperFunctions:
    """Test helper functions."""
    
    def test_calculate_num_frames(self):
        """Test num_frames calculation."""
        assert calculate_num_frames(5.0, 30) == 150
        assert calculate_num_frames(1.0, 24) == 24
        assert calculate_num_frames(10.0, 60) == 600
    
    def test_parse_retry_after_header_seconds_int(self):
        """Test parsing Retry-After header with integer seconds."""
        headers = {"Retry-After": "30"}
        result = parse_retry_after_header(headers)
        assert result == 30.0
    
    def test_parse_retry_after_header_seconds_float(self):
        """Test parsing Retry-After header with float seconds."""
        headers = {"Retry-After": "30.5"}
        result = parse_retry_after_header(headers)
        assert result == 30.5
    
    def test_parse_retry_after_header_missing(self):
        """Test parsing when Retry-After header is missing."""
        headers = {}
        result = parse_retry_after_header(headers)
        assert result is None
    
    def test_parse_retry_after_header_case_insensitive(self):
        """Test parsing with lowercase header name."""
        headers = {"retry-after": "45"}
        result = parse_retry_after_header(headers)
        assert result == 45.0
    
    def test_get_prediction_cost_from_metrics(self):
        """Test getting cost from prediction.metrics."""
        prediction = Mock()
        prediction.metrics = {"cost": 0.15}
        result = get_prediction_cost(prediction)
        assert result == Decimal("0.15")
    
    def test_get_prediction_cost_from_attribute(self):
        """Test getting cost from prediction.cost attribute."""
        prediction = Mock()
        prediction.cost = 0.20
        result = get_prediction_cost(prediction)
        assert result == Decimal("0.20")
    
    def test_get_prediction_cost_from_response(self):
        """Test getting cost from prediction.response.json()."""
        prediction = Mock(spec=[])  # Empty spec to prevent auto-attributes
        prediction.metrics = {}
        # Remove cost attribute if it exists
        if hasattr(prediction, 'cost'):
            delattr(prediction, 'cost')
        mock_response = Mock()
        mock_response.json = Mock(return_value={"cost": 0.25})
        prediction.response = mock_response
        result = get_prediction_cost(prediction)
        assert result == Decimal("0.25")
    
    def test_get_prediction_cost_nested_metrics(self):
        """Test getting cost from nested metrics in response."""
        prediction = Mock(spec=[])  # Empty spec to prevent auto-attributes
        prediction.metrics = {}
        # Remove cost attribute if it exists
        if hasattr(prediction, 'cost'):
            delattr(prediction, 'cost')
        mock_response = Mock()
        mock_response.json = Mock(return_value={"metrics": {"cost": 0.30}})
        prediction.response = mock_response
        result = get_prediction_cost(prediction)
        assert result == Decimal("0.30")
    
    def test_get_prediction_cost_not_available(self):
        """Test when cost is not available."""
        prediction = Mock()
        prediction.metrics = {}
        # Ensure no cost attribute
        if hasattr(prediction, 'cost'):
            delattr(prediction, 'cost')
        result = get_prediction_cost(prediction)
        assert result is None
    
    def test_get_prediction_cost_invalid_value(self):
        """Test handling invalid cost value."""
        prediction = Mock()
        prediction.metrics = {"cost": "invalid"}
        with patch('modules.video_generator.generator.logger') as mock_logger:
            result = get_prediction_cost(prediction)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_download_video_from_url_success(self):
        """Test successful video download."""
        mock_response = Mock()
        mock_response.content = b"video content"
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await download_video_from_url("https://example.com/video.mp4")
            assert result == b"video content"
    
    @pytest.mark.asyncio
    async def test_download_video_from_url_failure(self):
        """Test video download failure raises RetryableError."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Network error"))
            with pytest.raises(RetryableError, match="Video download failed"):
                await download_video_from_url("https://example.com/video.mp4")
    
    @patch('os.unlink')
    @patch('os.path.exists')
    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    def test_get_video_duration_success(self, mock_tempfile, mock_subprocess, mock_exists, mock_unlink):
        """Test successful duration extraction."""
        # Mock temp file
        mock_file = Mock()
        mock_file.name = "/tmp/test.mp4"
        mock_file.write = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_tempfile.return_value = mock_file
        
        # Mock os.path.exists
        mock_exists.return_value = True
        
        # Mock ffprobe output
        mock_result = Mock()
        mock_result.stdout = "5.5\n"
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        result = get_video_duration(b"fake video bytes")
        assert result == 5.5
        mock_unlink.assert_called_once_with("/tmp/test.mp4")
    
    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_get_video_duration_ffprobe_not_found(self, mock_unlink, mock_tempfile, mock_subprocess):
        """Test duration extraction when ffprobe is not found."""
        # Mock temp file
        mock_file = Mock()
        mock_file.name = "/tmp/test.mp4"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_tempfile.return_value = mock_file
        
        # Mock FileNotFoundError
        mock_subprocess.side_effect = FileNotFoundError("ffprobe not found")
        
        with patch('modules.video_generator.generator.logger') as mock_logger:
            result = get_video_duration(b"fake video bytes")
            assert result == 5.0  # Default fallback
            mock_logger.warning.assert_called()
    
    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_get_video_duration_subprocess_error(self, mock_unlink, mock_tempfile, mock_subprocess):
        """Test duration extraction when subprocess fails."""
        # Mock temp file
        mock_file = Mock()
        mock_file.name = "/tmp/test.mp4"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_tempfile.return_value = mock_file
        
        # Mock subprocess error
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "ffprobe")
        
        with patch('modules.video_generator.generator.logger') as mock_logger:
            result = get_video_duration(b"fake video bytes")
            assert result == 5.0  # Default fallback
            mock_logger.warning.assert_called()


# Main function tests
class TestGenerateVideoClip:
    """Test main generate_video_clip function."""
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.cost_tracker')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_success_with_url(
        self,
        mock_replicate,
        mock_download,
        mock_get_duration,
        mock_cost_tracker,
        mock_storage,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test successful clip generation with URL output."""
        # Mock prediction
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.metrics = {}
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        # Mock video download
        mock_download.return_value = b"video bytes"
        
        # Mock duration extraction
        mock_get_duration.return_value = 5.2
        
        # Mock storage
        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        mock_storage_instance.upload_file = AsyncMock(return_value="https://supabase.com/video.mp4")
        
        # Mock cost tracking
        mock_cost_tracker.track_cost = AsyncMock()
        
        # Mock cost extraction
        with patch('modules.video_generator.generator.get_prediction_cost', return_value=None):
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("0.15")):
                result = await generate_video_clip(
                    clip_prompt=sample_clip_prompt,
                    image_url="https://example.com/image.jpg",
                    settings=sample_settings,
                    job_id=sample_job_id,
                    environment="development"
                )
        
        assert isinstance(result, Clip)
        assert result.clip_index == 0
        assert result.video_url == "https://supabase.com/video.mp4"
        assert result.actual_duration == 5.2
        assert result.target_duration == 5.0
        assert result.status == "success"
        assert result.cost == Decimal("0.15")
        assert result.retry_count == 0
        assert result.generation_time > 0
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.cost_tracker')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_success_with_fileoutput(
        self,
        mock_replicate,
        mock_get_duration,
        mock_cost_tracker,
        mock_storage,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test successful clip generation with FileOutput object."""
        # Mock FileOutput object
        mock_file_output = Mock()
        mock_file_output.read.return_value = b"video bytes"
        
        # Mock prediction
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = mock_file_output
        mock_prediction.reload = Mock()
        mock_prediction.metrics = {"cost": 0.20}
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        # Mock duration extraction
        mock_get_duration.return_value = 5.0
        
        # Mock storage
        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        mock_storage_instance.upload_file = AsyncMock(return_value="https://supabase.com/video.mp4")
        
        # Mock cost tracking
        mock_cost_tracker.track_cost = AsyncMock()
        
        result = await generate_video_clip(
            clip_prompt=sample_clip_prompt,
            image_url=None,
            settings=sample_settings,
            job_id=sample_job_id,
            environment="development"
        )
        
        assert isinstance(result, Clip)
        assert result.video_url == "https://supabase.com/video.mp4"
        mock_file_output.read.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.time')
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_timeout(
        self,
        mock_replicate,
        mock_time,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test timeout handling."""
        # Mock prediction that never completes
        mock_prediction = Mock()
        mock_prediction.status = "processing"
        mock_prediction.reload = Mock()
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        # Mock time to simulate timeout quickly
        start_time = 1000.0
        mock_time.time.side_effect = [start_time, start_time + 1, start_time + 122]  # Exceeds 120s timeout
        
        with pytest.raises(TimeoutError, match="timeout"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_rate_limit_error(
        self,
        mock_replicate,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test rate limit error handling."""
        # Mock ModelError with rate limit
        mock_prediction = Mock()
        mock_prediction.status = "failed"
        mock_prediction.error = "Rate limit exceeded"
        mock_prediction.logs = "429 Too Many Requests"
        
        # Create ModelError with prediction object
        error = ModelError(mock_prediction)
        
        mock_replicate.predictions.create.side_effect = error
        
        with pytest.raises(RetryableError, match="Rate limit"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_model_unavailable(
        self,
        mock_replicate,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test model unavailable error handling."""
        # Mock prediction failure with unavailable model
        mock_prediction = Mock()
        mock_prediction.status = "failed"
        mock_prediction.error = "Model unavailable"
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        with pytest.raises(RetryableError, match="Model unavailable"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_invalid_input(
        self,
        mock_replicate,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test invalid input error handling."""
        # Mock ModelError with invalid input
        mock_prediction = Mock()
        mock_prediction.error = "Invalid input parameters"
        error = ModelError(mock_prediction)
        
        mock_replicate.predictions.create.side_effect = error
        
        with pytest.raises(GenerationError, match="Model error"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_network_error(
        self,
        mock_replicate,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test network error handling."""
        # Mock network error
        mock_replicate.predictions.create.side_effect = Exception("Network connection error")
        
        with pytest.raises(RetryableError, match="Network error"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.cost_tracker')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_with_actual_cost(
        self,
        mock_replicate,
        mock_download,
        mock_get_duration,
        mock_cost_tracker,
        mock_storage,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test cost tracking with actual cost from prediction."""
        # Mock prediction with cost
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.metrics = {"cost": 0.25}
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        # Mock video download
        mock_download.return_value = b"video bytes"
        
        # Mock duration extraction
        mock_get_duration.return_value = 5.0
        
        # Mock storage
        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        mock_storage_instance.upload_file = AsyncMock(return_value="https://supabase.com/video.mp4")
        
        # Mock cost tracking
        mock_cost_tracker.track_cost = AsyncMock()
        
        result = await generate_video_clip(
            clip_prompt=sample_clip_prompt,
            image_url=None,
            settings=sample_settings,
            job_id=sample_job_id,
            environment="development"
        )
        
        assert result.cost == Decimal("0.25")
        mock_cost_tracker.track_cost.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.cost_tracker')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_list_output(
        self,
        mock_replicate,
        mock_download,
        mock_get_duration,
        mock_cost_tracker,
        mock_storage,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test handling list output format."""
        # Mock prediction with list output
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = ["https://replicate.com/video1.mp4", "https://replicate.com/video2.mp4"]
        mock_prediction.reload = Mock()
        mock_prediction.metrics = {}
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        # Mock video download
        mock_download.return_value = b"video bytes"
        
        # Mock duration extraction
        mock_get_duration.return_value = 5.0
        
        # Mock storage
        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        mock_storage_instance.upload_file = AsyncMock(return_value="https://supabase.com/video.mp4")
        
        # Mock cost tracking
        mock_cost_tracker.track_cost = AsyncMock()
        
        with patch('modules.video_generator.generator.get_prediction_cost', return_value=None):
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("0.15")):
                result = await generate_video_clip(
                    clip_prompt=sample_clip_prompt,
                    image_url=None,
                    settings=sample_settings,
                    job_id=sample_job_id,
                    environment="development"
                )
        
        assert isinstance(result, Clip)
        # Should use first element from list
        mock_download.assert_called_once_with("https://replicate.com/video1.mp4")
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.replicate')
    async def test_generate_video_clip_unexpected_output_format(
        self,
        mock_replicate,
        sample_clip_prompt,
        sample_job_id,
        sample_settings
    ):
        """Test handling unexpected output format."""
        # Mock prediction with unexpected output type
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = 12345  # Unexpected type
        mock_prediction.reload = Mock()
        
        # Mock Replicate API
        mock_replicate.predictions.create.return_value = mock_prediction
        
        with pytest.raises(GenerationError, match="Unexpected output format"):
            await generate_video_clip(
                clip_prompt=sample_clip_prompt,
                image_url=None,
                settings=sample_settings,
                job_id=sample_job_id,
                environment="development"
            )


# Buffer calculation and original target duration tests
class TestBufferCalculation:
    """Test buffer duration calculation and original target preservation."""
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.get_latest_version_hash')
    @patch('modules.video_generator.generator.client')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.get_duration_buffer_multiplier')
    async def test_buffer_calculation_kling_discrete_maximum(
        self,
        mock_buffer_multiplier,
        mock_get_duration,
        mock_storage,
        mock_download,
        mock_client,
        mock_get_latest_hash,
        sample_job_id
    ):
        """Test buffer calculation for Kling models (discrete, maximum buffer strategy)."""
        # Set buffer multiplier (not used for discrete models, but needed)
        mock_buffer_multiplier.return_value = 1.25
        # Mock get_latest_version_hash (returns None to use model= parameter)
        mock_get_latest_hash.return_value = None
        
        # Test target > 5s should request 10s (maximum buffer)
        clip_prompt = ClipPrompt(
            clip_index=0,
            prompt="Test prompt",
            negative_prompt="",
            duration=8.0,  # Target > 5s
            scene_reference_url=None,
            character_reference_urls=[],
            metadata={}
        )
        
        # Mock Replicate API
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.created_at = None
        mock_client.predictions.create.return_value = mock_prediction
        
        # Mock other dependencies
        mock_download.return_value = b"fake video"
        mock_get_duration.return_value = 10.0
        mock_storage_instance = AsyncMock()
        mock_storage_instance.upload_file = AsyncMock(return_value="https://storage.com/video.mp4")
        mock_storage_instance.delete_file = AsyncMock()
        mock_storage.return_value = mock_storage_instance
        
        with patch('modules.video_generator.generator.cost_tracker') as mock_tracker:
            mock_tracker.track_cost = AsyncMock()
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("0.80")):
                result = await generate_video_clip(
                    clip_prompt=clip_prompt,
                    image_url=None,
                    settings={"resolution": "1080p", "fps": 24},
                    job_id=sample_job_id,
                    environment="production",
                    video_model="kling_v21"
                )
        
        # Verify original target duration is preserved
        assert result.original_target_duration == 8.0
        assert result.target_duration == 8.0
        # Verify duration requested was 10s (maximum buffer)
        call_args = mock_client.predictions.create.call_args
        # call_args is a tuple: (args, kwargs)
        assert call_args[1]["input"]["duration"] == 10
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.get_latest_version_hash')
    @patch('modules.video_generator.generator.client')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.get_duration_buffer_multiplier')
    async def test_buffer_calculation_kling_discrete_no_buffer(
        self,
        mock_buffer_multiplier,
        mock_get_duration,
        mock_storage,
        mock_download,
        mock_client,
        mock_get_latest_hash,
        sample_job_id
    ):
        """Test buffer calculation for Kling models when target ≤5s (no buffer possible)."""
        mock_buffer_multiplier.return_value = 1.25
        # Mock get_latest_version_hash (returns None to use model= parameter)
        mock_get_latest_hash.return_value = None
        
        # Test target ≤5s should request 5s (no buffer possible)
        clip_prompt = ClipPrompt(
            clip_index=0,
            prompt="Test prompt",
            negative_prompt="",
            duration=4.0,  # Target ≤5s
            scene_reference_url=None,
            character_reference_urls=[],
            metadata={}
        )
        
        # Mock Replicate API
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.created_at = None
        mock_client.predictions.create.return_value = mock_prediction
        
        # Mock other dependencies
        mock_download.return_value = b"fake video"
        mock_get_duration.return_value = 5.0
        mock_storage_instance = AsyncMock()
        mock_storage_instance.upload_file = AsyncMock(return_value="https://storage.com/video.mp4")
        mock_storage_instance.delete_file = AsyncMock()
        mock_storage.return_value = mock_storage_instance
        
        with patch('modules.video_generator.generator.cost_tracker') as mock_tracker:
            mock_tracker.track_cost = AsyncMock()
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("0.55")):
                result = await generate_video_clip(
                    clip_prompt=clip_prompt,
                    image_url=None,
                    settings={"resolution": "1080p", "fps": 24},
                    job_id=sample_job_id,
                    environment="production",
                    video_model="kling_v21"
                )
        
        # Verify original target duration is preserved
        assert result.original_target_duration == 4.0
        assert result.target_duration == 4.0
        # Verify duration requested was 5s (no buffer possible)
        call_args = mock_client.predictions.create.call_args
        # call_args is a tuple: (args, kwargs)
        assert call_args[1]["input"]["duration"] == 5
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.get_latest_version_hash')
    @patch('modules.video_generator.generator.client')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.get_duration_buffer_multiplier')
    async def test_buffer_calculation_veo_continuous_percentage(
        self,
        mock_buffer_multiplier,
        mock_get_duration,
        mock_storage,
        mock_download,
        mock_client,
        mock_get_latest_hash,
        sample_job_id
    ):
        """Test buffer calculation for Veo 3.1 (continuous, percentage buffer)."""
        # Set buffer multiplier to 1.25 (25% buffer)
        mock_buffer_multiplier.return_value = 1.25
        # Mock get_latest_version_hash (returns None to use model= parameter)
        mock_get_latest_hash.return_value = None
        
        # Test target 4.0s should request 5.0s (25% buffer = 5.0s)
        clip_prompt = ClipPrompt(
            clip_index=0,
            prompt="Test prompt",
            negative_prompt="",
            duration=4.0,  # Target 4.0s
            scene_reference_url=None,
            character_reference_urls=[],
            metadata={}
        )
        
        # Mock Replicate API
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.created_at = None
        mock_client.predictions.create.return_value = mock_prediction
        
        # Mock other dependencies
        mock_download.return_value = b"fake video"
        mock_get_duration.return_value = 5.0
        mock_storage_instance = AsyncMock()
        mock_storage_instance.upload_file = AsyncMock(return_value="https://storage.com/video.mp4")
        mock_storage_instance.delete_file = AsyncMock()
        mock_storage.return_value = mock_storage_instance
        
        with patch('modules.video_generator.generator.cost_tracker') as mock_tracker:
            mock_tracker.track_cost = AsyncMock()
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("1.00")):
                result = await generate_video_clip(
                    clip_prompt=clip_prompt,
                    image_url=None,
                    settings={"resolution": "1080p", "fps": 24},
                    job_id=sample_job_id,
                    environment="production",
                    video_model="veo_31"
                )
        
        # Verify original target duration is preserved
        assert result.original_target_duration == 4.0
        assert result.target_duration == 4.0
        # Verify duration requested was 5.0s (4.0 * 1.25 = 5.0)
        call_args = mock_client.predictions.create.call_args
        # call_args is a tuple: (args, kwargs)
        assert call_args[1]["input"]["duration"] == 5.0
    
    @pytest.mark.asyncio
    @patch('modules.video_generator.generator.get_latest_version_hash')
    @patch('modules.video_generator.generator.client')
    @patch('modules.video_generator.generator.download_video_from_url')
    @patch('modules.video_generator.generator.StorageClient')
    @patch('modules.video_generator.generator.get_video_duration')
    @patch('modules.video_generator.generator.get_duration_buffer_multiplier')
    async def test_buffer_calculation_veo_continuous_capped(
        self,
        mock_buffer_multiplier,
        mock_get_duration,
        mock_storage,
        mock_download,
        mock_client,
        mock_get_latest_hash,
        sample_job_id
    ):
        """Test buffer calculation for Veo 3.1 when buffer would exceed 10s (capped)."""
        mock_buffer_multiplier.return_value = 1.25
        # Mock get_latest_version_hash (returns None to use model= parameter)
        mock_get_latest_hash.return_value = None
        
        # Test target 8.0s should request 10.0s (capped at 10s, not 10.0s)
        clip_prompt = ClipPrompt(
            clip_index=0,
            prompt="Test prompt",
            negative_prompt="",
            duration=8.0,  # Target 8.0s, 25% buffer = 10.0s (capped)
            scene_reference_url=None,
            character_reference_urls=[],
            metadata={}
        )
        
        # Mock Replicate API
        mock_prediction = Mock()
        mock_prediction.status = "succeeded"
        mock_prediction.output = "https://replicate.com/video.mp4"
        mock_prediction.reload = Mock()
        mock_prediction.created_at = None
        mock_client.predictions.create.return_value = mock_prediction
        
        # Mock other dependencies
        mock_download.return_value = b"fake video"
        mock_get_duration.return_value = 10.0
        mock_storage_instance = AsyncMock()
        mock_storage_instance.upload_file = AsyncMock(return_value="https://storage.com/video.mp4")
        mock_storage_instance.delete_file = AsyncMock()
        mock_storage.return_value = mock_storage_instance
        
        with patch('modules.video_generator.generator.cost_tracker') as mock_tracker:
            mock_tracker.track_cost = AsyncMock()
            with patch('modules.video_generator.generator.estimate_clip_cost', return_value=Decimal("1.50")):
                result = await generate_video_clip(
                    clip_prompt=clip_prompt,
                    image_url=None,
                    settings={"resolution": "1080p", "fps": 24},
                    job_id=sample_job_id,
                    environment="production",
                    video_model="veo_31"
                )
        
        # Verify original target duration is preserved
        assert result.original_target_duration == 8.0
        assert result.target_duration == 8.0
        # Verify duration requested was 10.0s (capped at max)
        call_args = mock_client.predictions.create.call_args
        # call_args is a tuple: (args, kwargs)
        assert call_args[1]["input"]["duration"] == 10.0


class TestOriginalTargetDuration:
    """Test original target duration preservation in Clip model."""
    
    def test_clip_original_target_defaults_to_target(self):
        """Test that original_target_duration defaults to target_duration if not provided."""
        clip = Clip(
            clip_index=0,
            video_url="https://example.com/video.mp4",
            actual_duration=5.0,
            target_duration=5.0,
            duration_diff=0.0,
            status="success",
            cost=Decimal("0.50"),
            retry_count=0,
            generation_time=10.0
        )
        
        # Should default to target_duration
        assert clip.original_target_duration == 5.0
    
    def test_clip_original_target_explicit(self):
        """Test that original_target_duration can be set explicitly."""
        clip = Clip(
            clip_index=0,
            video_url="https://example.com/video.mp4",
            actual_duration=10.0,
            target_duration=8.0,  # After buffer calculation
            original_target_duration=6.0,  # Original before buffer
            duration_diff=2.0,
            status="success",
            cost=Decimal("0.80"),
            retry_count=0,
            generation_time=15.0
        )
        
        # Should use explicit value
        assert clip.original_target_duration == 6.0
        assert clip.target_duration == 8.0
    
    def test_clip_original_target_none_defaults(self):
        """Test that original_target_duration=None defaults to target_duration."""
        clip = Clip(
            clip_index=0,
            video_url="https://example.com/video.mp4",
            actual_duration=5.0,
            target_duration=5.0,
            original_target_duration=None,  # Explicitly None
            duration_diff=0.0,
            status="success",
            cost=Decimal("0.50"),
            retry_count=0,
            generation_time=10.0
        )
        
        # Should default to target_duration even if None provided
        assert clip.original_target_duration == 5.0

