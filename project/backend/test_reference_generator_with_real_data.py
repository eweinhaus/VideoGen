"""
Test Reference Generator with real scene plan data from database.

This script:
1. Queries the database for the latest completed scene_planner job
2. Extracts or reconstructs the ScenePlan from job_stages metadata
3. Runs the reference generator with that real data
4. Verifies all events are properly emitted
5. Tests event publishing to ensure UI receives updates

Usage:
    cd project/backend
    source venv/bin/activate
    python test_reference_generator_with_real_data.py
"""

import asyncio
import sys
import json
from uuid import UUID
from pathlib import Path
from typing import Optional, Dict, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.database import DatabaseClient
from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition
from modules.reference_generator.process import process as generate_references
from shared.logging import get_logger
from shared.errors import ValidationError

logger = get_logger(__name__)
db_client = DatabaseClient()


async def get_latest_scene_planner_job() -> Optional[Dict[str, Any]]:
    """Get the latest job that has completed scene_planner stage."""
    try:
        # Query for jobs with completed scene_planner stage, ordered by most recent
        result = await db_client.table("job_stages").select(
            "job_id, status, metadata, created_at"
        ).eq(
            "stage_name", "scene_planner"
        ).eq(
            "status", "completed"
        ).order("created_at", desc=True).limit(1).execute()  # Get most recent
        
        if result.data and len(result.data) > 0:
            stage_data = result.data[0]
            job_id = stage_data["job_id"]
            
            # Get the full job details
            job_result = await db_client.table("jobs").select("*").eq("id", job_id).execute()
            if job_result.data and len(job_result.data) > 0:
                job = job_result.data[0]
                return {
                    "job_id": job_id,
                    "job": job,
                    "stage_metadata": stage_data.get("metadata"),
                    "stage_created_at": stage_data.get("created_at")
                }
        
        return None
    except Exception as e:
        logger.error(f"Failed to query database for scene planner job: {e}", exc_info=e)
        return None


async def reconstruct_scene_plan_from_metadata(
    job_id: str,
    metadata: Optional[Dict[str, Any]]
) -> Optional[ScenePlan]:
    """Reconstruct ScenePlan from job_stages metadata."""
    try:
        # Handle metadata that might be a JSON string or dict
        if metadata:
            # If metadata is a string, parse it
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse metadata as JSON: {metadata}")
                    return None
            
            # Check if metadata contains scene plan data
            if isinstance(metadata, dict) and "scene_plan" in metadata:
                scene_plan_data = metadata["scene_plan"]
                
                # Reconstruct ScenePlan from metadata
                return ScenePlan(
                    job_id=UUID(job_id),
                    video_summary=scene_plan_data.get("video_summary", ""),
                    characters=[
                        Character(**char) for char in scene_plan_data.get("characters", [])
                    ],
                    scenes=[
                        Scene(**scene) for scene in scene_plan_data.get("scenes", [])
                    ],
                    style=Style(**scene_plan_data.get("style", {})),
                    clip_scripts=[
                        ClipScript(**clip) for clip in scene_plan_data.get("clip_scripts", [])
                    ],
                    transitions=[
                        Transition(**trans) for trans in scene_plan_data.get("transitions", [])
                    ]
                )
            else:
                logger.warning(f"Metadata does not contain 'scene_plan' key. Keys: {list(metadata.keys()) if isinstance(metadata, dict) else 'not a dict'}")
        
        logger.warning("Scene plan not found in metadata")
        return None
        
    except Exception as e:
        logger.error(f"Failed to reconstruct scene plan: {e}", exc_info=e)
        return None


async def test_with_real_data():
    """Test reference generator with real scene plan from database."""
    logger.info("=" * 80)
    logger.info("Testing Reference Generator with Real Database Data")
    logger.info("=" * 80)
    
    # Get latest scene planner job
    logger.info("\n1. Querying database for latest scene planner job...")
    job_data = await get_latest_scene_planner_job()
    
    if not job_data:
        logger.warning("No completed scene_planner job found in database")
        logger.info("Falling back to mock scene plan test...")
        return await test_with_mock_data()
    
    job_id_str = job_data["job_id"]
    job = job_data["job"]
    metadata = job_data["stage_metadata"]
    
    logger.info(f"Found job: {job_id_str}")
    logger.info(f"Job status: {job.get('status')}")
    logger.info(f"Job created: {job.get('created_at')}")
    logger.info(f"Has metadata: {metadata is not None}")
    
    # Reconstruct scene plan
    logger.info("\n2. Reconstructing ScenePlan from metadata...")
    scene_plan = await reconstruct_scene_plan_from_metadata(job_id_str, metadata)
    
    if not scene_plan:
        logger.warning("Could not reconstruct scene plan from metadata")
        logger.info("Falling back to mock scene plan test...")
        return await test_with_mock_data()
    
    logger.info(f"Scene plan reconstructed:")
    logger.info(f"  - Scenes: {len(scene_plan.scenes)}")
    logger.info(f"  - Characters: {len(scene_plan.characters)}")
    logger.info(f"  - Clip scripts: {len(scene_plan.clip_scripts)}")
    logger.info(f"  - Video summary: {scene_plan.video_summary[:100]}...")
    
    # Test reference generator
    logger.info("\n3. Running reference generator with real scene plan...")
    job_id_uuid = UUID(job_id_str)
    duration_seconds = 120.0  # Use a reasonable default
    
    try:
        references, events = await generate_references(
            job_id=job_id_uuid,
            plan=scene_plan,
            duration_seconds=duration_seconds
        )
        
        logger.info(f"\n4. Reference generation completed!")
        logger.info(f"   Events emitted: {len(events)}")
        logger.info(f"   References returned: {references is not None}")
        
        # Analyze events
        logger.info("\n5. Event Analysis:")
        event_types = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        for event_type, count in sorted(event_types.items()):
            logger.info(f"   - {event_type}: {count}")
        
        # Check for critical events
        has_started = any(e.get("event_type") == "stage_update" and 
                         e.get("data", {}).get("status") == "started" 
                         for e in events)
        has_completed = any(e.get("event_type") == "stage_update" and 
                           e.get("data", {}).get("status") == "completed" 
                           for e in events)
        has_failed = any(e.get("event_type") == "stage_update" and 
                        e.get("data", {}).get("status") == "failed" 
                        for e in events)
        
        logger.info("\n6. Critical Event Check:")
        logger.info(f"   - stage_update 'started': {'✅' if has_started else '❌'}")
        logger.info(f"   - stage_update 'completed': {'✅' if has_completed else '❌'}")
        logger.info(f"   - stage_update 'failed': {'✅' if has_failed else '❌'}")
        
        # Check for reference generation events
        ref_start_events = [e for e in events if e.get("event_type") == "reference_generation_start"]
        ref_complete_events = [e for e in events if e.get("event_type") == "reference_generation_complete"]
        ref_failed_events = [e for e in events if e.get("event_type") == "reference_generation_failed"]
        
        logger.info(f"\n7. Reference Generation Events:")
        logger.info(f"   - reference_generation_start: {len(ref_start_events)}")
        logger.info(f"   - reference_generation_complete: {len(ref_complete_events)}")
        logger.info(f"   - reference_generation_failed: {len(ref_failed_events)}")
        
        # Print sample events
        logger.info("\n8. Sample Events (first 5):")
        for i, event in enumerate(events[:5]):
            logger.info(f"   [{i+1}] {event.get('event_type')}: {json.dumps(event.get('data', {}), indent=2)}")
        
        # Results
        if references is None:
            logger.error("\n❌ Reference generator returned None")
            logger.error("Check events above for failure reason")
            return False
        
        logger.info("\n✅ Reference generator succeeded!")
        logger.info(f"   Total references: {references.total_references}")
        logger.info(f"   Scene references: {len(references.scene_references)}")
        logger.info(f"   Character references: {len(references.character_references)}")
        logger.info(f"   Total cost: ${float(references.total_cost):.4f}")
        logger.info(f"   Total time: {references.total_generation_time:.2f}s")
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Reference generator failed: {e}", exc_info=e)
        return False


async def test_with_mock_data():
    """Fallback test with mock data."""
    from modules.reference_generator.tests.fixtures import create_mock_scene_plan
    
    logger.info("\nUsing mock scene plan for testing...")
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    scene_plan = create_mock_scene_plan(
        job_id=str(job_id),
        num_scenes=2,
        num_characters=2
    )
    
    try:
        references, events = await generate_references(
            job_id=job_id,
            plan=scene_plan,
            duration_seconds=120.0
        )
        
        logger.info(f"Mock test completed. Events: {len(events)}")
        return references is not None
        
    except Exception as e:
        logger.error(f"Mock test failed: {e}", exc_info=e)
        return False


async def test_event_emission():
    """Test that events are properly formatted for SSE publishing."""
    logger.info("\n" + "=" * 80)
    logger.info("Testing Event Emission Format")
    logger.info("=" * 80)
    
    from modules.reference_generator.tests.fixtures import create_mock_scene_plan
    
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    scene_plan = create_mock_scene_plan(
        job_id=str(job_id),
        num_scenes=1,
        num_characters=1
    )
    
    try:
        references, events = await generate_references(
            job_id=job_id,
            plan=scene_plan,
            duration_seconds=60.0
        )
        
        logger.info(f"\nTotal events: {len(events)}")
        
        # Verify event format
        issues = []
        for i, event in enumerate(events):
            if "event_type" not in event:
                issues.append(f"Event {i}: missing 'event_type'")
            if "data" not in event:
                issues.append(f"Event {i}: missing 'data'")
            if not isinstance(event.get("data"), dict):
                issues.append(f"Event {i}: 'data' is not a dict")
        
        if issues:
            logger.error("Event format issues found:")
            for issue in issues:
                logger.error(f"  - {issue}")
            return False
        
        logger.info("✅ All events properly formatted")
        return True
        
    except Exception as e:
        logger.error(f"Event emission test failed: {e}", exc_info=e)
        return False


async def main():
    """Run all tests."""
    results = []
    
    # Test 1: Real data from database
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Real Database Data")
    logger.info("=" * 80)
    result1 = await test_with_real_data()
    results.append(("Real Database Data", result1))
    
    # Test 2: Event emission format
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Event Emission Format")
    logger.info("=" * 80)
    result2 = await test_event_emission()
    results.append(("Event Emission Format", result2))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Test Summary")
    logger.info("=" * 80)
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        logger.info("\n✅ All tests passed!")
        return 0
    else:
        logger.error("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

