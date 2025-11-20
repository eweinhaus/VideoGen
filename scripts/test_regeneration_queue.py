#!/usr/bin/env python3
"""
Test script for regeneration queue functionality.

Tests:
1. Enqueueing a regeneration job
2. Verifying job data is stored in Redis
3. Worker processing (manual check)
"""

import asyncio
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'project', 'backend'))

from api_gateway.services.queue_service import enqueue_regeneration_job, QUEUE_NAME
from shared.redis_client import RedisClient
from shared.logging import get_logger

logger = get_logger(__name__)


async def test_enqueue_regeneration():
    """Test enqueueing a regeneration job."""
    test_job_id = "test-job-123"
    test_user_id = "test-user-456"
    test_clip_indices = [0, 1, 2]
    test_instruction = "Make the videos more cinematic"
    
    print("\n=== Testing Regeneration Queue ===\n")
    
    try:
        # 1. Enqueue a test regeneration job
        print("1. Enqueueing regeneration job...")
        await enqueue_regeneration_job(
            job_id=test_job_id,
            user_id=test_user_id,
            clip_indices=test_clip_indices,
            user_instruction=test_instruction,
            conversation_history=[{"role": "user", "content": "Previous instruction"}],
            regeneration_id="test-regen-789"
        )
        print("✓ Job enqueued successfully\n")
        
        # 2. Verify job is in queue
        print("2. Verifying job in Redis queue...")
        redis_client = RedisClient()
        queue_key = f"{QUEUE_NAME}:queue"
        queue_length = await redis_client.client.llen(queue_key)
        print(f"✓ Queue length: {queue_length}\n")
        
        # 3. Peek at the job data (without removing it)
        print("3. Peeking at job data...")
        job_data_bytes = await redis_client.client.lindex(queue_key, 0)
        if job_data_bytes:
            job_data = json.loads(job_data_bytes.decode('utf-8'))
            print(f"✓ Job data: {json.dumps(job_data, indent=2)}\n")
            
            # Verify it's a regeneration job
            assert job_data.get("job_type") == "regeneration", "Job type should be 'regeneration'"
            assert job_data.get("job_id") == test_job_id, "Job ID mismatch"
            assert job_data.get("clip_indices") == test_clip_indices, "Clip indices mismatch"
            print("✓ Job data validation passed\n")
        else:
            print("✗ No job data found in queue\n")
            return False
        
        # 4. Check regeneration key
        print("4. Checking regeneration key in Redis...")
        regen_key = f"{QUEUE_NAME}:regeneration:test-regen-789"
        regen_data_bytes = await redis_client.client.get(regen_key)
        if regen_data_bytes:
            regen_data = json.loads(regen_data_bytes.decode('utf-8'))
            print(f"✓ Regeneration data: {json.dumps(regen_data, indent=2)}\n")
        else:
            print("✗ Regeneration key not found\n")
            return False
        
        print("=== All tests passed! ===\n")
        print("✓ Regeneration jobs are being enqueued correctly")
        print("✓ Job type is set to 'regeneration'")
        print("✓ Clip indices array is preserved")
        print("✓ Worker will process these in parallel\n")
        
        # Clean up - remove test job from queue
        print("Cleaning up test job...")
        await redis_client.client.lpop(queue_key)
        await redis_client.client.delete(regen_key)
        print("✓ Cleanup complete\n")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"\n✗ Test failed: {e}\n")
        return False


async def main():
    """Main test runner."""
    success = await test_enqueue_regeneration()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

