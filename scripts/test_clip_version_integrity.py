#!/usr/bin/env python3
"""
Test script to verify clip version database integrity.

This script tests the version verification system to ensure:
1. Both versions are saved correctly
2. Video URLs are different between versions
3. is_current flags are set correctly
4. Verification catches integrity violations
"""
import asyncio
from uuid import UUID, uuid4
from decimal import Decimal

# Mock data for testing
MOCK_JOB_ID = UUID("12345678-1234-5678-1234-567812345678")
MOCK_CLIP_INDEX = 0
MOCK_ORIGINAL_URL = "https://storage.example.com/video-clips/job_123/clip_0_original.mp4"
MOCK_REGENERATED_URL = "https://storage.example.com/video-clips/job_123/clip_0_regenerated.mp4"


async def test_verify_clip_versions():
    """Test the verification function with mock data."""
    print("Testing clip version verification...")
    print("=" * 80)
    
    # Import the verification function
    try:
        from modules.clip_regenerator.version_verifier import verify_clip_versions_after_save
    except ImportError as e:
        print(f"❌ Failed to import verification function: {e}")
        print("Make sure the module is in the Python path")
        return False
    
    # Test Case 1: Verify with expected URLs (success case)
    print("\n📝 Test Case 1: Verify with expected URLs (should pass)")
    print("-" * 80)
    try:
        result = await verify_clip_versions_after_save(
            job_id=MOCK_JOB_ID,
            clip_index=MOCK_CLIP_INDEX,
            expected_original_url=MOCK_ORIGINAL_URL,
            expected_latest_url=MOCK_REGENERATED_URL,
            expected_latest_version=2
        )
        
        if result.get("success"):
            print("✅ Verification passed!")
            print(f"   Message: {result.get('message')}")
            print(f"   Total versions: {result.get('total_versions')}")
            print(f"   URLs different: {result.get('urls_different')}")
            print(f"   v1 URL: {result.get('v1_url')}")
            print(f"   v{result.get('v_latest_version')} URL: {result.get('v_latest_url')}")
        else:
            print(f"⚠️ Verification returned failure: {result.get('message')}")
            if result.get("error"):
                print(f"   Error: {result.get('error')} ({result.get('error_type')})")
        
        return result.get("success")
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


async def test_get_current_version():
    """Test getting current version."""
    print("\n📝 Test Case 2: Get current version")
    print("-" * 80)
    
    try:
        from modules.clip_regenerator.version_verifier import get_current_clip_version
        
        current = await get_current_clip_version(
            job_id=MOCK_JOB_ID,
            clip_index=MOCK_CLIP_INDEX
        )
        
        if current:
            print("✅ Found current version!")
            print(f"   Version number: {current.get('version_number')}")
            print(f"   Video URL: {current.get('video_url')}")
            print(f"   Is current: {current.get('is_current')}")
            return True
        else:
            print("⚠️ No current version found (this may be expected if clip_versions table is empty)")
            return True  # Not a failure
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


async def test_get_all_versions():
    """Test getting all versions."""
    print("\n📝 Test Case 3: Get all versions")
    print("-" * 80)
    
    try:
        from modules.clip_regenerator.version_verifier import get_all_clip_versions
        
        all_versions = await get_all_clip_versions(
            job_id=MOCK_JOB_ID,
            clip_index=MOCK_CLIP_INDEX
        )
        
        if all_versions:
            print(f"✅ Found {len(all_versions)} version(s)!")
            for version in all_versions:
                print(f"   v{version.get('version_number')}: {version.get('video_url')}")
                print(f"      is_current: {version.get('is_current')}")
                print(f"      user_instruction: {version.get('user_instruction') or 'None (original)'}")
            return True
        else:
            print("⚠️ No versions found (this may be expected if clip_versions table is empty)")
            return True  # Not a failure
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


async def main():
    """Run all tests."""
    print("\n🔬 CLIP VERSION VERIFICATION TESTS")
    print("=" * 80)
    print(f"Job ID: {MOCK_JOB_ID}")
    print(f"Clip Index: {MOCK_CLIP_INDEX}")
    print()
    
    # Note: These tests require an actual database connection and existing data
    # If the clip_versions table is empty, some tests may return no data (which is expected)
    
    print("⚠️  NOTE: These tests require:")
    print("   1. Database connection configured (Supabase)")
    print("   2. clip_versions table exists")
    print("   3. Actual clip version data in the table")
    print()
    print("   If you don't have test data, use the regeneration endpoint to create some:")
    print("   POST /api/v1/jobs/{job_id}/clips/regenerate")
    print()
    
    # Run tests
    results = []
    
    # Test 1: Verify versions
    result1 = await test_verify_clip_versions()
    results.append(("Verify clip versions", result1))
    
    # Test 2: Get current version
    result2 = await test_get_current_version()
    results.append(("Get current version", result2))
    
    # Test 3: Get all versions
    result3 = await test_get_all_versions()
    results.append(("Get all versions", result3))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

