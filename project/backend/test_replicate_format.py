#!/usr/bin/env python3
"""Test Replicate API format"""
import os
from dotenv import load_dotenv
load_dotenv()

import replicate

# Set API token
os.environ['REPLICATE_API_TOKEN'] = os.getenv('REPLICATE_API_TOKEN')

# Test different formats
formats_to_test = [
    "stability-ai/stable-video-diffusion:3f0457f4613a",  # Full format
    "3f0457f4613a",  # Just version hash
]

print("Testing Replicate API formats...")
print(f"API Token: {os.getenv('REPLICATE_API_TOKEN')[:20]}...")

for fmt in formats_to_test:
    print(f"\nTrying format: {fmt}")
    try:
        # Try creating a prediction with minimal input
        prediction = replicate.predictions.create(
            version=fmt,
            input={"prompt": "test", "num_frames": 14}
        )
        print(f"✅ SUCCESS with format: {fmt}")
        print(f"   Prediction ID: {prediction.id}")
        print(f"   Status: {prediction.status}")
        break
    except Exception as e:
        print(f"❌ FAILED with format: {fmt}")
        print(f"   Error: {e}")

