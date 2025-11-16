#!/usr/bin/env python3
"""
Test if the configured Stable Video Diffusion version works.

This script attempts to create a minimal prediction to verify the version is valid.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

try:
    import replicate
except ImportError:
    print("ERROR: replicate package not installed. Install with: pip install replicate")
    sys.exit(1)

# Check API token
api_token = os.getenv("REPLICATE_API_TOKEN")
if not api_token:
    print("ERROR: REPLICATE_API_TOKEN not found in environment.")
    sys.exit(1)

# Get current version from config
try:
    from modules.video_generator.config import SVD_MODEL_VERSION
    print(f"Testing version: {SVD_MODEL_VERSION}")
    print(f"Full model string: stability-ai/stable-video-diffusion:{SVD_MODEL_VERSION}\n")
except Exception as e:
    print(f"Warning: Could not load config: {e}")
    SVD_MODEL_VERSION = "3f0457f4613a"  # Default fallback
    print(f"Using default version: {SVD_MODEL_VERSION}\n")

# Test the version
print("=" * 70)
print("Testing Version Accessibility")
print("=" * 70)

try:
    # Try to create a minimal prediction (this will fail but tells us if version exists)
    print(f"\nAttempting to create prediction with version: {SVD_MODEL_VERSION}")
    print("(This will fail with input validation, but confirms version exists)\n")
    
    prediction = replicate.predictions.create(
        version=SVD_MODEL_VERSION,  # Just the version hash
        input={
            "prompt": "test",  # Minimal input
            "num_frames": 14
        }
    )
    
    print(f"✓ Version is accessible!")
    print(f"  Prediction ID: {prediction.id}")
    print(f"  Status: {prediction.status}")
    print(f"\n✅ SUCCESS: Version {SVD_MODEL_VERSION} is valid and accessible!")
    
except replicate.exceptions.ModelError as e:
    # ModelError usually means the version doesn't exist
    print(f"❌ ModelError: {e}")
    print(f"\n⚠️  Version {SVD_MODEL_VERSION} may not exist or is not accessible.")
    print("   Check https://replicate.com/stability-ai/stable-video-diffusion for available versions.")
    
except Exception as e:
    error_str = str(e).lower()
    # If it's an input validation error, the version exists!
    if "input" in error_str or "validation" in error_str or "required" in error_str:
        print(f"✓ Version exists! (Got expected input validation error)")
        print(f"  Error: {e}")
        print(f"\n✅ SUCCESS: Version {SVD_MODEL_VERSION} is valid!")
    else:
        print(f"❌ Unexpected error: {e}")
        print(f"\n⚠️  Could not verify version. Error: {e}")

print("\n" + "=" * 70)
print("Next Steps")
print("=" * 70)
print("""
If the version test failed:
1. Visit: https://replicate.com/stability-ai/stable-video-diffusion
2. Check the Versions tab to see available versions
3. Update your .env file with the correct version

To update your .env file:
1. Open: project/backend/.env (or root .env)
2. Add or update: SVD_MODEL_VERSION=<new_version_id>
3. Restart your application
""")

