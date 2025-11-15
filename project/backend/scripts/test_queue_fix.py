#!/usr/bin/env python3
"""
Test script to verify queue enqueue/dequeue operations work correctly.

This script tests:
1. Job can be enqueued with proper encoding
2. Job can be dequeued with proper decoding
3. Queue key matches between enqueue and dequeue
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.redis_client import RedisClient
from api_gateway.services.queue_service import QUEUE_NAME, enqueue_job, get_queue_size
from shared.logging import get_logger

logger = get_logger(__name__)


async def test_queue_operations():
    """Test queue enqueue and dequeue operations."""
    redis_client = RedisClient()
    queue_key = f"{QUEUE_NAME}:queue"
    
    print("=" * 80)
    print("Testing Queue Operations")
    print("=" * 80)
    print()
    
    # Clear queue first
    print(f"1. Clearing queue: {queue_key}")
    await redis_client.client.delete(queue_key)
    initial_size = await redis_client.client.llen(queue_key)
    print(f"   Queue cleared. Initial size: {initial_size}")
    print()
    
    # Test 1: Enqueue a test job
    print("2. Testing job enqueue...")
    test_job_id = "test-job-12345"
    test_user_id = "test-user-12345"
    test_audio_url = "https://example.com/test.mp3"
    test_prompt = "Test prompt"
    
    try:
        await enqueue_job(
            job_id=test_job_id,
            user_id=test_user_id,
            audio_url=test_audio_url,
            user_prompt=test_prompt
        )
        print(f"   ✓ Job enqueued successfully")
        
        # Check queue size
        queue_size = await get_queue_size()
        print(f"   Queue size after enqueue: {queue_size}")
        
        if queue_size == 0:
            print("   ⚠ WARNING: Queue size is 0 after enqueue!")
            return False
        
    except Exception as e:
        print(f"   ✗ Failed to enqueue job: {e}")
        return False
    
    print()
    
    # Test 2: Dequeue the job
    print("3. Testing job dequeue...")
    try:
        # Use brpop with short timeout
        result = await redis_client.client.brpop(queue_key, timeout=2)
        
        if result is None:
            print("   ✗ Failed to dequeue job (timeout)")
            return False
        
        # Decode the job data
        job_data_bytes = result[1]
        if isinstance(job_data_bytes, bytes):
            job_data_str = job_data_bytes.decode('utf-8')
        else:
            job_data_str = job_data_bytes
        
        job_data = json.loads(job_data_str)
        
        print(f"   ✓ Job dequeued successfully")
        print(f"   Job ID: {job_data.get('job_id')}")
        print(f"   User ID: {job_data.get('user_id')}")
        print(f"   Audio URL: {job_data.get('audio_url')}")
        
        # Verify job data matches
        if job_data.get('job_id') != test_job_id:
            print(f"   ✗ Job ID mismatch: expected {test_job_id}, got {job_data.get('job_id')}")
            return False
        
        if job_data.get('user_id') != test_user_id:
            print(f"   ✗ User ID mismatch: expected {test_user_id}, got {job_data.get('user_id')}")
            return False
        
        print("   ✓ Job data matches expected values")
        
    except Exception as e:
        print(f"   ✗ Failed to dequeue job: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Test 3: Verify queue is empty
    print("4. Verifying queue is empty after dequeue...")
    final_size = await get_queue_size()
    print(f"   Final queue size: {final_size}")
    
    if final_size != 0:
        print(f"   ⚠ WARNING: Queue is not empty after dequeue!")
        return False
    
    print("   ✓ Queue is empty")
    print()
    
    print("=" * 80)
    print("✓ All tests passed!")
    print("=" * 80)
    return True


async def main():
    """Main entry point."""
    try:
        success = await test_queue_operations()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

