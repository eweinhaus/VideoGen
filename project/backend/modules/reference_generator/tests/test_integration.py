"""
Integration tests for Reference Generator module.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID
from decimal import Decimal
from modules.reference_generator.process import process
from shared.storage import storage
from shared.cost_tracking import cost_tracker


@pytest.mark.asyncio
@patch('modules.reference_generator.generator.generate_all_references', new_callable=AsyncMock)
@patch('shared.storage.storage.upload_file', new_callable=AsyncMock)
async def test_process_success(mock_upload, mock_generate, sample_scene_plan):
    """Test successful reference generation."""
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    
    # Mock generation results (all 4 images successful)
    mock_generate.return_value = [
        {
            "success": True,
            "image_type": "scene",
            "image_id": "city_street",
            "scene_id": "city_street",
            "character_id": None,
            "image_bytes": b"fake_image_bytes",
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
            "image_bytes": b"fake_image_bytes",
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
            "image_bytes": b"fake_image_bytes",
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
            "image_bytes": b"fake_image_bytes",
            "generation_time": 8.0,
            "cost": Decimal("0.005"),
            "prompt": "Test prompt",
            "retry_count": 0
        }
    ]
    
    # Mock storage
    mock_upload.return_value = "https://storage.supabase.co/test.png"
    
    with patch.object(storage, 'get_signed_url', new_callable=AsyncMock) as mock_get_url, \
         patch.object(cost_tracker, 'track_cost', new_callable=AsyncMock) as mock_track_cost:
        mock_get_url.return_value = "https://storage.supabase.co/test.png?token=..."
        mock_track_cost.return_value = None
        
        # Process
        references, events = await process(job_id, sample_scene_plan)
        
        # Verify results
        assert references is not None
        assert references.status == "success"
        assert len(references.scene_references) == 2
        assert len(references.character_references) == 2
        assert len(events) > 0
        
        # Verify events
        stage_events = [e for e in events if e.get("event_type") == "stage_update"]
        assert len(stage_events) >= 2  # Start and complete
