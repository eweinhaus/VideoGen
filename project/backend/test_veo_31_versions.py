#!/usr/bin/env python3
"""
Test script to find the best working Veo 3.1 model version.

Tests different version hashes for google/veo-3.1 to identify:
1. Which versions are accessible
2. Which versions accept valid duration parameters (4, 6, 8)
3. Which versions generate videos successfully

Usage:
    python test_veo_31_versions.py [--hash HASH] [--test-all]
"""

import asyncio
import os
import sys
from typing import Dict, Any, Optional, List
from decimal import Decimal
import replicate
from replicate.exceptions import ModelError, ReplicateError

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("test_veo_31")

# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    sys.exit(1)

# Known version hash from error logs
KNOWN_HASH = "20ebd92c5919f20e8fa2e983bdb60016a99794c9accfab496ea25a68e0dbbaad"

# Valid durations for Veo 3.1
VALID_DURATIONS = [4, 6, 8]


async def get_latest_version_hash() -> Optional[str]:
    """Get the latest version hash for google/veo-3.1."""
    try:
        model = client.models.get(owner="google", name="veo-3.1")
        if model and model.latest_version:
            return model.latest_version.id
    except Exception as e:
        logger.error(f"Failed to get latest version: {e}")
    return None


async def list_all_versions() -> List[str]:
    """List all available versions for google/veo-3.1."""
    try:
        model = client.models.get(owner="google", name="veo-3.1")
        if model and hasattr(model, 'versions'):
            versions = []
            # Get versions (may need pagination)
            try:
                for version in model.versions.list():
                    versions.append(version.id)
            except Exception:
                # If versions.list() doesn't work, just return latest
                if model.latest_version:
                    versions.append(model.latest_version.id)
            return versions
    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
    return []


async def test_version_hash(version_hash: str, duration: int = 4, aspect_ratio: str = "16:9") -> Dict[str, Any]:
    """
    Test a specific version hash with a duration parameter.
    
    Args:
        version_hash: Version hash to test
        duration: Duration in seconds (must be 4, 6, or 8)
        aspect_ratio: Aspect ratio to test (default: "16:9")
        
    Returns:
        Dict with test results
    """
    result = {
        "version_hash": version_hash,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "accessible": False,
        "validates_duration": False,
        "generates_video": False,
        "error": None,
        "prediction_id": None,
    }
    
    # Test: Try to create a prediction with valid duration (this will validate the version)
    try:
        test_input = {
            "prompt": "A beautiful sunset over the ocean",
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        
        prediction = client.predictions.create(
            version=version_hash,
            input=test_input
        )
        result["prediction_id"] = prediction.id
        result["accessible"] = True  # If we got here, version is accessible
        result["validates_duration"] = True
        logger.info(f"✅ Version {version_hash[:20]}... accepts duration={duration}")
        
        # Test 3: Wait for prediction to complete (with timeout)
        max_wait = 180  # 3 minutes max
        wait_time = 0
        poll_interval = 5
        
        while prediction.status in ["starting", "processing"] and wait_time < max_wait:
            await asyncio.sleep(poll_interval)
            wait_time += poll_interval
            prediction = client.predictions.get(prediction.id)
            
            if prediction.status == "succeeded":
                result["generates_video"] = True
                if prediction.output:
                    result["video_url"] = prediction.output
                logger.info(f"✅ Version {version_hash[:20]}... generated video successfully")
                break
            elif prediction.status == "failed":
                result["error"] = f"Prediction failed: {prediction.error}"
                logger.error(f"❌ Version {version_hash[:20]}... prediction failed: {prediction.error}")
                break
        
        if prediction.status in ["starting", "processing"]:
            result["error"] = "Prediction timed out"
            logger.warning(f"⏱️  Version {version_hash[:20]}... prediction timed out")
        
    except ReplicateError as e:
        error_str = str(e)
        if "duration must be one of" in error_str:
            result["error"] = f"Duration validation error: {error_str}"
            logger.error(f"❌ Version {version_hash[:20]}... duration validation failed: {error_str}")
        else:
            result["error"] = f"Replicate error: {error_str}"
            logger.error(f"❌ Version {version_hash[:20]}... Replicate error: {error_str}")
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        logger.error(f"❌ Version {version_hash[:20]}... unexpected error: {e}")
    
    return result


async def test_all_durations(version_hash: str) -> Dict[str, Any]:
    """Test a version hash with all valid durations."""
    results = {
        "version_hash": version_hash,
        "durations": {}
    }
    
    for duration in VALID_DURATIONS:
        logger.info(f"Testing duration={duration}s for version {version_hash[:20]}...")
        test_result = await test_version_hash(version_hash, duration)
        results["durations"][duration] = test_result
    
    return results


async def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Veo 3.1 model versions")
    parser.add_argument("--hash", type=str, help="Specific version hash to test")
    parser.add_argument("--test-all", action="store_true", help="Test all durations for the hash")
    parser.add_argument("--list-versions", action="store_true", help="List all available versions")
    args = parser.parse_args()
    
    print("=" * 80)
    print("Veo 3.1 Version Testing Script")
    print("=" * 80)
    print()
    
    # Get latest version hash
    print("📡 Retrieving latest version hash...")
    latest_hash = await get_latest_version_hash()
    if latest_hash:
        print(f"✅ Latest version: {latest_hash}")
        print()
    else:
        print("❌ Could not retrieve latest version")
        print()
    
    # List versions if requested
    if args.list_versions:
        print("📋 Listing all available versions...")
        versions = await list_all_versions()
        if versions:
            print(f"Found {len(versions)} versions:")
            for v in versions[:10]:  # Show first 10
                print(f"  - {v}")
            if len(versions) > 10:
                print(f"  ... and {len(versions) - 10} more")
        else:
            print("❌ Could not list versions")
        print()
    
    # Test specific hash or known hash
    hash_to_test = args.hash or KNOWN_HASH
    
    if args.test_all:
        print(f"🧪 Testing all durations for version {hash_to_test[:20]}...")
        print()
        results = await test_all_durations(hash_to_test)
        
        print("=" * 80)
        print("Test Results Summary")
        print("=" * 80)
        print(f"Version Hash: {results['version_hash']}")
        print()
        
        for duration, result in results["durations"].items():
            print(f"Duration: {duration}s")
            print(f"  Accessible: {'✅' if result['accessible'] else '❌'}")
            print(f"  Validates Duration: {'✅' if result['validates_duration'] else '❌'}")
            print(f"  Generates Video: {'✅' if result['generates_video'] else '❌'}")
            if result.get("error"):
                print(f"  Error: {result['error']}")
            if result.get("video_url"):
                print(f"  Video URL: {result['video_url']}")
            print()
    else:
        print(f"🧪 Testing version {hash_to_test[:20]}... with duration=4")
        print()
        result = await test_version_hash(hash_to_test, duration=4)
        
        print("=" * 80)
        print("Test Results")
        print("=" * 80)
        print(f"Version Hash: {result['version_hash']}")
        print(f"Duration: {result['duration']}s")
        print(f"Accessible: {'✅' if result['accessible'] else '❌'}")
        print(f"Validates Duration: {'✅' if result['validates_duration'] else '❌'}")
        print(f"Generates Video: {'✅' if result['generates_video'] else '❌'}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("video_url"):
            print(f"Video URL: {result['video_url']}")
        print()
    
    print("=" * 80)
    print("Testing complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

