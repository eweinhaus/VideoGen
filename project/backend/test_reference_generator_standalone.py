"""
Standalone test script for Reference Generator module.

Tests the reference generator with a mock scene plan from fixtures.
This can be run independently to verify the reference generator works.

Usage:
    cd project/backend
    source venv/bin/activate
    python test_reference_generator_standalone.py
"""

import asyncio
import sys
from uuid import UUID
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.reference_generator.tests.fixtures import create_mock_scene_plan
from modules.reference_generator.process import process as generate_references
from shared.logging import get_logger
from shared.errors import ValidationError

logger = get_logger(__name__)


async def test_reference_generator():
    """Test reference generator with mock scene plan."""
    
    # Create a test job ID
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    
    # Create mock scene plan (2 scenes, 2 characters - typical case)
    logger.info("Creating mock scene plan...")
    scene_plan = create_mock_scene_plan(
        job_id=str(job_id),
        num_scenes=2,
        num_characters=2,
        style_variant="default"
    )
    
    logger.info(
        f"Scene plan created: {len(scene_plan.scenes)} scenes, {len(scene_plan.characters)} characters"
    )
    logger.info(f"Scenes: {[s.id for s in scene_plan.scenes]}")
    logger.info(f"Characters: {[c.id for c in scene_plan.characters]}")
    
    # Test with duration for budget checks
    duration_seconds = 120.0  # 2 minutes
    
    try:
        logger.info("Starting reference generation...")
        references, events = await generate_references(
            job_id=job_id,
            plan=scene_plan,
            duration_seconds=duration_seconds
        )
        
        logger.info(f"Reference generation completed. Events: {len(events)}")
        
        # Print event summary
        for event in events:
            event_type = event.get("event_type", "unknown")
            data = event.get("data", {})
            logger.info(f"Event: {event_type} - {data}")
        
        # Check results
        if references is None:
            logger.error("❌ Reference generator returned None (failed)")
            logger.error("Check events above for failure reason")
            return False
        
        logger.info("✅ Reference generator succeeded!")
        logger.info(f"Total references: {references.total_references}")
        logger.info(f"Scene references: {len(references.scene_references)}")
        logger.info(f"Character references: {len(references.character_references)}")
        logger.info(f"Total cost: ${float(references.total_cost):.4f}")
        logger.info(f"Total time: {references.total_generation_time:.2f}s")
        logger.info(f"Status: {references.status}")
        
        # Print image URLs
        for ref in references.scene_references:
            logger.info(f"Scene reference: {ref.scene_id} -> {ref.image_url}")
        
        for ref in references.character_references:
            logger.info(f"Character reference: {ref.character_id} -> {ref.image_url}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Reference generator failed with error: {e}", exc_info=e)
        return False


async def test_empty_scene_plan():
    """Test reference generator with empty scene plan (should raise ValidationError)."""
    
    job_id = UUID("550e8400-e29b-41d4-a716-446655440001")
    
    # Create scene plan with no scenes/characters
    scene_plan = create_mock_scene_plan(
        job_id=str(job_id),
        num_scenes=0,
        num_characters=0
    )
    
    logger.info("Testing with empty scene plan (should raise ValidationError)...")
    
    try:
        references, events = await generate_references(
            job_id=job_id,
            plan=scene_plan,
            duration_seconds=120.0
        )
        
        logger.error("❌ Should have raised ValidationError for empty scene plan")
        return False
            
    except ValidationError as e:
        logger.info(f"✅ Correctly raised ValidationError: {e}")
        return True
    except Exception as e:
        logger.error(f"❌ Unexpected error type: {type(e).__name__}: {e}", exc_info=e)
        return False


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Reference Generator Standalone Test")
    logger.info("=" * 60)
    
    # Test 1: Normal case
    logger.info("\n" + "=" * 60)
    logger.info("Test 1: Normal case (2 scenes, 2 characters)")
    logger.info("=" * 60)
    test1_result = await test_reference_generator()
    
    # Test 2: Empty scene plan
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Empty scene plan (should fail gracefully)")
    logger.info("=" * 60)
    test2_result = await test_empty_scene_plan()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    logger.info(f"Test 1 (Normal case): {'✅ PASSED' if test1_result else '❌ FAILED'}")
    logger.info(f"Test 2 (Empty plan): {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    if test1_result and test2_result:
        logger.info("\n✅ All tests passed!")
        return 0
    else:
        logger.error("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

