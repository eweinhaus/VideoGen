"""
End-to-end test for time remaining estimation feature.

Tests the full flow from backend estimation to SSE events.
This test verifies that:
1. Backend calculates estimate correctly
2. Database is updated with estimate
3. SSE events include estimate
4. Frontend would receive and display estimate correctly
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from api_gateway.orchestrator import update_progress
from api_gateway.services.time_estimator import calculate_estimated_remaining


async def test_time_remaining_e2e():
    """Test end-to-end flow of time remaining estimation."""
    print("=" * 80)
    print("Time Remaining Estimation End-to-End Test")
    print("=" * 80)
    
    job_id = str(uuid4())
    print(f"✅ Job ID: {job_id}")
    
    # Test scenario: 3-minute audio, 6 clips, 4 images
    audio_duration = 180.0  # 3 minutes
    num_clips = 6
    num_images = 4
    
    print(f"\n📊 Test Scenario:")
    print(f"  - Audio duration: {audio_duration}s ({audio_duration/60:.1f} minutes)")
    print(f"  - Number of clips: {num_clips}")
    print(f"  - Number of images: {num_images}")
    
    # Step 1: Test estimation calculation
    print("\n" + "-" * 80)
    print("Step 1: Testing estimation calculation...")
    print("-" * 80)
    
    try:
        # Test at different stages
        stages_to_test = [
            ("audio_parser", 5),
            ("audio_parser", 5),
            ("scene_planner", 15),
            ("reference_generator", 27),
            ("prompt_generator", 40),
            ("video_generator", 60),
            ("composer", 90),
        ]
        
        estimates = {}
        for stage_name, progress in stages_to_test:
            estimate = await calculate_estimated_remaining(
                job_id=job_id,
                current_stage=stage_name,
                progress=progress,
                audio_duration=audio_duration,
                environment="development",
                num_clips=num_clips if stage_name in ["video_generator", "composer"] else None,
                num_images=num_images if stage_name == "reference_generator" else None
            )
            estimates[f"{stage_name}_{progress}"] = estimate
            print(f"  ✅ {stage_name} ({progress}%): {estimate}s ({estimate/60:.1f} min)")
        
        # Verify estimates are reasonable
        assert all(e is not None for e in estimates.values()), "All estimates should be non-null"
        assert all(e > 0 for e in estimates.values()), "All estimates should be positive"
        
        # Verify estimates decrease as progress increases
        audio_parser_early = estimates["audio_parser_5"]
        composer_late = estimates["composer_90"]
        assert composer_late < audio_parser_early, "Estimate should decrease as job progresses"
        
        print("  ✅ All estimates calculated successfully")
        
    except Exception as e:
        print(f"  ❌ Estimation calculation failed: {e}")
        return False
    
    # Step 2: Test update_progress integration
    print("\n" + "-" * 80)
    print("Step 2: Testing update_progress integration...")
    print("-" * 80)
    
    try:
        # Mock database
        mock_db_result = MagicMock()
        mock_db_result.data = [{"id": job_id}]
        mock_db_query = MagicMock()
        mock_db_query.execute = AsyncMock(return_value=mock_db_result)
        mock_db_query.eq = MagicMock(return_value=mock_db_query)
        mock_db_query.update = MagicMock(return_value=mock_db_query)
        mock_db_table = MagicMock()
        mock_db_table.update = MagicMock(return_value=mock_db_query)
        mock_db = MagicMock()
        mock_db.table = MagicMock(return_value=mock_db_table)
        
        # Mock Redis
        mock_redis_client = MagicMock()
        mock_redis_client.delete = AsyncMock(return_value=1)
        mock_redis_wrapper = MagicMock()
        mock_redis_wrapper.client = mock_redis_client
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Mock event publishing
        published_events = []
        async def mock_publish(job_id, event_type, data):
            published_events.append((job_id, event_type, data))
        
        broadcasted_events = []
        async def mock_broadcast(job_id, event_type, data):
            broadcasted_events.append((job_id, event_type, data))
        
        with patch("api_gateway.orchestrator.db_client", mock_db), \
             patch("api_gateway.orchestrator.redis_client", mock_redis_wrapper), \
             patch("api_gateway.orchestrator.publish_event", mock_publish), \
             patch("api_gateway.orchestrator.broadcast_event", mock_broadcast):
            
            # Test update_progress at video_generator stage
            await update_progress(
                job_id=job_id,
                progress=60,
                stage_name="video_generator",
                audio_duration=audio_duration,
                num_clips=num_clips
            )
            
            # Verify database update
            assert mock_db_table.update.called, "Database update should be called"
            update_data = mock_db_table.update.call_args[0][0]
            assert "estimated_remaining" in update_data, "Database should include estimated_remaining"
            assert update_data["estimated_remaining"] is not None, "estimated_remaining should not be None"
            assert update_data["progress"] == 60, "Progress should be 60"
            print(f"  ✅ Database updated with estimated_remaining: {update_data['estimated_remaining']}s")
            
            # Verify events published
            assert len(published_events) > 0, "Progress event should be published"
            progress_event = published_events[-1]
            assert progress_event[0] == job_id, "Event should be for correct job"
            assert progress_event[1] == "progress", "Event type should be 'progress'"
            assert "estimated_remaining" in progress_event[2], "Event should include estimated_remaining"
            print(f"  ✅ Progress event published with estimated_remaining: {progress_event[2]['estimated_remaining']}s")
            
            # Verify SSE broadcast
            assert len(broadcasted_events) > 0, "SSE event should be broadcast"
            sse_event = broadcasted_events[-1]
            assert sse_event[0] == job_id, "SSE event should be for correct job"
            assert sse_event[1] == "progress", "SSE event type should be 'progress'"
            assert "estimated_remaining" in sse_event[2], "SSE event should include estimated_remaining"
            print(f"  ✅ SSE event broadcast with estimated_remaining: {sse_event[2]['estimated_remaining']}s")
            
            # Verify estimate matches
            assert progress_event[2]["estimated_remaining"] == sse_event[2]["estimated_remaining"], \
                "Published and broadcast estimates should match"
            assert progress_event[2]["estimated_remaining"] == update_data["estimated_remaining"], \
                "Database and event estimates should match"
            
            print("  ✅ All integration checks passed")
            
    except Exception as e:
        print(f"  ❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 3: Test edge cases
    print("\n" + "-" * 80)
    print("Step 3: Testing edge cases...")
    print("-" * 80)
    
    try:
        # Test with no audio_duration
        with patch("api_gateway.orchestrator.db_client", mock_db), \
             patch("api_gateway.orchestrator.redis_client", mock_redis_wrapper), \
             patch("api_gateway.orchestrator.publish_event", mock_publish), \
             patch("api_gateway.orchestrator.broadcast_event", mock_broadcast):
            
            # Reset mocks
            mock_db_table.update.reset_mock()
            published_events.clear()
            broadcasted_events.clear()
            mock_redis_wrapper.get.return_value = None
            
            await update_progress(
                job_id=job_id,
                progress=25,
                stage_name="scene_planner"
                # No audio_duration provided
            )
            
            # Verify it handles None gracefully
            update_data = mock_db_table.update.call_args[0][0]
            assert "estimated_remaining" not in update_data or update_data.get("estimated_remaining") is None, \
                "Should handle missing audio_duration gracefully"
            
            # Verify events still sent (with None)
            assert len(published_events) > 0, "Should still publish event"
            assert published_events[-1][2]["estimated_remaining"] is None, \
                "Event should include None for estimated_remaining"
            
            print("  ✅ Edge case: Missing audio_duration handled gracefully")
        
        # Test with Redis audio_duration retrieval
        mock_redis_wrapper.get.return_value = "150.0"
        with patch("api_gateway.orchestrator.db_client", mock_db), \
             patch("api_gateway.orchestrator.redis_client", mock_redis_wrapper), \
             patch("api_gateway.orchestrator.publish_event", mock_publish), \
             patch("api_gateway.orchestrator.broadcast_event", mock_broadcast):
            
            mock_db_table.update.reset_mock()
            published_events.clear()
            broadcasted_events.clear()
            
            await update_progress(
                job_id=job_id,
                progress=40,
                stage_name="prompt_generator"
                # No audio_duration, should retrieve from Redis
            )
            
            # Verify Redis was queried
            assert mock_redis_wrapper.get.called, "Should query Redis for audio_duration"
            
            # Verify estimate was calculated
            update_data = mock_db_table.update.call_args[0][0]
            assert "estimated_remaining" in update_data, "Should calculate estimate from Redis value"
            assert update_data["estimated_remaining"] is not None, "Estimate should not be None"
            
            print("  ✅ Edge case: Audio duration retrieved from Redis")
        
        print("  ✅ All edge cases handled correctly")
        
    except Exception as e:
        print(f"  ❌ Edge case test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 4: Summary
    print("\n" + "=" * 80)
    print("✅ END-TO-END TEST PASSED")
    print("=" * 80)
    print("\n📋 Summary:")
    print("  ✅ Estimation calculation works correctly")
    print("  ✅ Database updates include estimated_remaining")
    print("  ✅ Progress events include estimated_remaining")
    print("  ✅ SSE broadcasts include estimated_remaining")
    print("  ✅ Edge cases handled gracefully")
    print("\n💡 Frontend Integration:")
    print("  - Frontend should receive estimated_remaining in SSE progress events")
    print("  - Frontend should display countdown timer using estimated_remaining")
    print("  - Frontend should handle null/undefined gracefully (show 'Calculating...')")
    print("  - Frontend should decrement timer every second")
    print("  - Frontend should show 'Almost done...' when <30 seconds")
    
    return True


async def main():
    """Run the E2E test."""
    success = await test_time_remaining_e2e()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

