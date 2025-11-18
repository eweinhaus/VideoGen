"""
Unit tests for data loader module.

Tests loading clips, prompts, scene plans, and reference images from job_stages.metadata.
"""
import pytest
import json
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clip_prompts_from_job_stages,
    load_scene_plan_from_job_stages,
    load_reference_images_from_job_stages
)
from shared.models.video import Clips, Clip, ClipPrompts, ClipPrompt
from shared.models.scene import ScenePlan, ReferenceImages


@pytest.fixture
def sample_job_id():
    """Sample job ID for testing."""
    return uuid4()


@pytest.fixture
def mock_database_client():
    """Mock database client for testing."""
    mock_client = AsyncMock()
    
    # Mock table query builder
    mock_table = MagicMock()
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.eq = MagicMock(return_value=mock_table)
    
    mock_client.table = MagicMock(return_value=mock_table)
    
    return mock_client


@pytest.fixture
def sample_clips_metadata():
    """Sample clips metadata structure."""
    return {
        "clips": {
            "job_id": str(uuid4()),
            "clips": [
                {
                    "clip_index": 0,
                    "video_url": "https://storage.supabase.co/video-clips/job/clip_0.mp4",
                    "actual_duration": 12.5,
                    "target_duration": 12.0,
                    "original_target_duration": 12.0,
                    "duration_diff": 0.5,
                    "status": "success",
                    "cost": "0.10",
                    "retry_count": 0,
                    "generation_time": 45.2
                },
                {
                    "clip_index": 1,
                    "video_url": "https://storage.supabase.co/video-clips/job/clip_1.mp4",
                    "actual_duration": 11.8,
                    "target_duration": 12.0,
                    "original_target_duration": 12.0,
                    "duration_diff": -0.2,
                    "status": "success",
                    "cost": "0.10",
                    "retry_count": 0,
                    "generation_time": 43.1
                }
            ],
            "total_clips": 2,
            "successful_clips": 2,
            "failed_clips": 0,
            "total_cost": "0.20",
            "total_generation_time": 88.3
        }
    }


@pytest.fixture
def sample_clip_prompts_metadata():
    """Sample clip prompts metadata structure."""
    return {
        "job_id": str(uuid4()),
        "clip_prompts": [
            {
                "clip_index": 0,
                "prompt": "A cyberpunk street scene with neon lights",
                "negative_prompt": "blurry, low quality",
                "duration": 12.0,
                "scene_reference_url": "https://storage.supabase.co/reference-images/scene.jpg",
                "character_reference_urls": [],
                "metadata": {}
            }
        ],
        "total_clips": 1,
        "generation_time": 2.5
    }


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_success(sample_job_id, sample_clips_metadata, mock_database_client):
    """Test loading clips with valid metadata."""
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [{"metadata": sample_clips_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is not None
    assert isinstance(clips, Clips)
    assert len(clips.clips) == 2
    assert clips.total_clips == 2
    assert clips.successful_clips == 2
    assert clips.clips[0].clip_index == 0
    assert clips.clips[1].clip_index == 1


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_missing_stage(sample_job_id, mock_database_client):
    """Test loading clips when stage not found."""
    # Mock empty database response
    mock_result = MagicMock()
    mock_result.data = []
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is None


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_invalid_json(sample_job_id, mock_database_client):
    """Test loading clips with invalid JSON metadata."""
    # Mock database response with invalid JSON string
    mock_result = MagicMock()
    mock_result.data = [{"metadata": "invalid json {["}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is None


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_missing_clips_key(sample_job_id, mock_database_client):
    """Test loading clips when metadata doesn't have clips key."""
    # Mock database response with metadata missing clips
    mock_result = MagicMock()
    mock_result.data = [{"metadata": {"other_data": "value"}}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is None


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_pydantic_validation_error(sample_job_id, mock_database_client):
    """Test loading clips with invalid Pydantic model data."""
    # Mock database response with invalid clip data (missing required fields)
    invalid_metadata = {
        "clips": {
            "clips": [{"clip_index": 0}]  # Missing required fields
        }
    }
    
    mock_result = MagicMock()
    mock_result.data = [{"metadata": invalid_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is None


@pytest.mark.asyncio
async def test_load_clips_from_job_stages_json_string(sample_job_id, sample_clips_metadata, mock_database_client):
    """Test loading clips when metadata is JSON string."""
    # Mock database response with JSON string metadata
    mock_result = MagicMock()
    mock_result.data = [{"metadata": json.dumps(sample_clips_metadata)}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is not None
    assert isinstance(clips, Clips)
    assert len(clips.clips) == 2


@pytest.mark.asyncio
async def test_load_clip_prompts_from_job_stages_success(sample_job_id, sample_clip_prompts_metadata, mock_database_client):
    """Test loading clip prompts with valid metadata."""
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [{"metadata": sample_clip_prompts_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clip_prompts = await load_clip_prompts_from_job_stages(sample_job_id)
    
    assert clip_prompts is not None
    assert isinstance(clip_prompts, ClipPrompts)
    assert len(clip_prompts.clip_prompts) == 1
    assert clip_prompts.clip_prompts[0].clip_index == 0


@pytest.mark.asyncio
async def test_load_clip_prompts_from_job_stages_missing_stage(sample_job_id, mock_database_client):
    """Test loading clip prompts when stage not found."""
    # Mock empty database response
    mock_result = MagicMock()
    mock_result.data = []
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clip_prompts = await load_clip_prompts_from_job_stages(sample_job_id)
    
    assert clip_prompts is None


@pytest.mark.asyncio
async def test_load_scene_plan_from_job_stages_success(sample_job_id, mock_database_client):
    """Test loading scene plan with valid metadata."""
    # Sample scene plan metadata
    scene_plan_metadata = {
        "characters": [],
        "scenes": [],
        "clip_scripts": [],
        "transitions": [],
        "style": {
            "visual_style": "cyberpunk",
            "color_palette": "neon",
            "lighting": "dark",
            "cinematography": "dynamic"
        }
    }
    
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [{"metadata": scene_plan_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        scene_plan = await load_scene_plan_from_job_stages(sample_job_id)
    
    assert scene_plan is not None
    assert isinstance(scene_plan, ScenePlan)


@pytest.mark.asyncio
async def test_load_reference_images_from_job_stages_success(sample_job_id, mock_database_client):
    """Test loading reference images with valid metadata."""
    # Sample reference images metadata
    reference_images_metadata = {
        "scene_references": [],
        "character_references": [],
        "total_images": 0,
        "successful_images": 0,
        "failed_images": 0,
        "total_cost": "0.00",
        "total_generation_time": 0.0
    }
    
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [{"metadata": reference_images_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        reference_images = await load_reference_images_from_job_stages(sample_job_id)
    
    assert reference_images is not None
    assert isinstance(reference_images, ReferenceImages)


@pytest.mark.asyncio
async def test_load_clips_nested_structure(sample_job_id, sample_clips_metadata, mock_database_client):
    """Test that nested structure metadata['clips']['clips'] is correctly accessed."""
    # Mock database response
    mock_result = MagicMock()
    mock_result.data = [{"metadata": sample_clips_metadata}]
    
    mock_table = mock_database_client.table.return_value
    mock_table.execute = AsyncMock(return_value=mock_result)
    
    with patch("modules.clip_regenerator.data_loader.DatabaseClient", return_value=mock_database_client):
        clips = await load_clips_from_job_stages(sample_job_id)
    
    assert clips is not None
    # Verify nested structure was correctly accessed
    assert len(clips.clips) == 2
    assert clips.clips[0].clip_index == 0
    assert clips.clips[1].clip_index == 1

