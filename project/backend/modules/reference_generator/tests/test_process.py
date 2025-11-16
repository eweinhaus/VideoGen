"""Tests for process function."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from decimal import Decimal

from modules.reference_generator.process import process
from shared.models.scene import ScenePlan, Character, Scene, Style, ReferenceImages
from shared.storage import storage
from shared.cost_tracking import cost_tracker


@pytest.mark.asyncio
async def test_process_validation_no_scenes(sample_style):
    """Test that process raises ValidationError when no scenes."""
    plan = ScenePlan(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        video_summary="Test",
        characters=[Character(id="char1", description="Character", role="main")],
        scenes=[],
        style=sample_style,
        clip_scripts=[],
        transitions=[]
    )
    
    with pytest.raises(Exception):  # ValidationError
        await process(UUID("550e8400-e29b-41d4-a716-446655440000"), plan)


@pytest.mark.asyncio
async def test_process_validation_no_characters(sample_style):
    """Test that process raises ValidationError when no characters."""
    plan = ScenePlan(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        video_summary="Test",
        characters=[],
        scenes=[Scene(id="scene1", description="Scene")],
        style=sample_style,
        clip_scripts=[],
        transitions=[]
    )
    
    with pytest.raises(Exception):  # ValidationError
        await process(UUID("550e8400-e29b-41d4-a716-446655440000"), plan)


@pytest.mark.asyncio
async def test_process_validation_duplicate_scene_ids(sample_style):
    """Test that process raises ValidationError for duplicate scene IDs."""
    plan = ScenePlan(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        video_summary="Test",
        characters=[Character(id="char1", description="Character", role="main")],
        scenes=[
            Scene(id="scene1", description="Scene 1"),
            Scene(id="scene1", description="Scene 2")  # Duplicate ID
        ],
        style=sample_style,
        clip_scripts=[],
        transitions=[]
    )
    
    with pytest.raises(Exception):  # ValidationError
        await process(UUID("550e8400-e29b-41d4-a716-446655440000"), plan)


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.generate_all_references', new_callable=AsyncMock)
@patch('shared.storage.storage.upload_file', new_callable=AsyncMock)
async def test_process_success(mock_upload, mock_generate, sample_scene_plan):
    """Test successful process execution."""
    # Mock successful image generation (matches generate_all_references return structure)
    # Need all 4 images (2 scenes + 2 characters) for "success" status
    mock_generate.return_value = [
        {
            "success": True,
            "image_type": "scene",
            "image_id": "city_street",
            "scene_id": "city_street",
            "character_id": None,
            "image_bytes": b"fake_image_data",
            "generation_time": 8.5,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": True,
            "image_type": "scene",
            "image_id": "interior",
            "scene_id": "interior",
            "character_id": None,
            "image_bytes": b"fake_image_data",
            "generation_time": 8.2,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": True,
            "image_type": "character",
            "image_id": "protagonist",
            "scene_id": None,
            "character_id": "protagonist",
            "image_bytes": b"fake_image_data",
            "generation_time": 8.1,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": True,
            "image_type": "character",
            "image_id": "antagonist",
            "scene_id": None,
            "character_id": "antagonist",
            "image_bytes": b"fake_image_data",
            "generation_time": 8.0,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        }
    ]
    
    # Mock upload_file (returns public URL, but we'll use get_signed_url)
    mock_upload.return_value = "https://storage.supabase.co/public-url"
    
    # Mock storage.get_signed_url and cost tracker
    with patch.object(storage, 'get_signed_url', new_callable=AsyncMock) as mock_get_url, \
         patch.object(cost_tracker, 'track_cost', new_callable=AsyncMock) as mock_track_cost:
        mock_get_url.return_value = "https://storage.supabase.co/signed-url"
        mock_track_cost.return_value = None
        
        result, events = await process(
            UUID("550e8400-e29b-41d4-a716-446655440000"),
            sample_scene_plan
        )
        
        assert result is not None
        assert isinstance(result, ReferenceImages)
        assert result.status == "success"  # All 4 images successful
        assert len(result.scene_references) == 2  # Both scenes
        assert len(result.character_references) == 2  # Both characters
        assert len(events) >= 2  # At least start and complete events


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.generate_all_references', new_callable=AsyncMock)
@patch('shared.storage.storage.upload_file', new_callable=AsyncMock)
async def test_process_partial_success_below_threshold(mock_upload, mock_generate, sample_scene_plan):
    """Test process returns None when partial success threshold not met."""
    # Mock generation with only 1 successful image (below 50% threshold for 4 images)
    mock_generate.return_value = [
        {
            "success": True,
            "image_type": "scene",
            "image_id": "city_street",
            "scene_id": "city_street",
            "character_id": None,
            "image_bytes": b"fake_image_data",
            "generation_time": 8.5,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": False,
            "image_type": "scene",
            "image_id": "interior",
            "error": "Failed",
            "retry_count": 0
        },
        {
            "success": False,
            "image_type": "character",
            "image_id": "protagonist",
            "error": "Failed",
            "retry_count": 0
        },
        {
            "success": False,
            "image_type": "character",
            "image_id": "antagonist",
            "error": "Failed",
            "retry_count": 0
        }
    ]
    
    mock_upload.return_value = "https://storage.supabase.co/public-url"
    
    with patch.object(storage, 'get_signed_url', new_callable=AsyncMock) as mock_get_url, \
         patch.object(cost_tracker, 'track_cost', new_callable=AsyncMock) as mock_track_cost:
        mock_get_url.return_value = "https://storage.supabase.co/signed-url"
        mock_track_cost.return_value = None
        
        result, events = await process(
            UUID("550e8400-e29b-41d4-a716-446655440000"),
            sample_scene_plan
        )
        
        # Should return None because threshold not met (1/4 = 25% < 50%)
        assert result is None
        assert len(events) >= 2


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.generate_all_references', new_callable=AsyncMock)
@patch('shared.storage.storage.upload_file', new_callable=AsyncMock)
async def test_process_partial_success_no_characters(mock_upload, mock_generate, sample_scene_plan):
    """Test process returns None when no character references generated."""
    # Mock generation with only scene references (no characters)
    mock_generate.return_value = [
        {
            "success": True,
            "image_type": "scene",
            "image_id": "city_street",
            "scene_id": "city_street",
            "character_id": None,
            "image_bytes": b"fake_image_data",
            "generation_time": 8.5,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": True,
            "image_type": "scene",
            "image_id": "interior",
            "scene_id": "interior",
            "character_id": None,
            "image_bytes": b"fake_image_data",
            "generation_time": 8.2,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        },
        {
            "success": False,
            "image_type": "character",
            "image_id": "protagonist",
            "error": "Failed",
            "retry_count": 0
        },
        {
            "success": False,
            "image_type": "character",
            "image_id": "antagonist",
            "error": "Failed",
            "retry_count": 0
        }
    ]
    
    mock_upload.return_value = "https://storage.supabase.co/public-url"
    
    with patch.object(storage, 'get_signed_url', new_callable=AsyncMock) as mock_get_url, \
         patch.object(cost_tracker, 'track_cost', new_callable=AsyncMock) as mock_track_cost:
        mock_get_url.return_value = "https://storage.supabase.co/signed-url"
        mock_track_cost.return_value = None
        
        result, events = await process(
            UUID("550e8400-e29b-41d4-a716-446655440000"),
            sample_scene_plan
        )
        
        # Should return None because no character references (threshold requires ≥1 character)
        assert result is None

