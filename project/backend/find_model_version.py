#!/usr/bin/env python3
"""
Find and test available versions for video generation models.

This script helps you find the correct version ID for any Replicate model.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    import replicate
    import requests
except ImportError as e:
    print(f"ERROR: Missing package. Install with: pip install replicate requests")
    sys.exit(1)

api_token = os.getenv("REPLICATE_API_TOKEN")
if not api_token:
    print("ERROR: REPLICATE_API_TOKEN not found in environment.")
    sys.exit(1)

# Models to check
MODELS_TO_CHECK = [
    {
        "name": "sunfjun/stable-video-diffusion",
        "owner": "sunfjun",
        "model": "stable-video-diffusion",
        "description": "Direct SVD replacement"
    },
    {
        "name": "bytedance/seedance-1-pro-fast",
        "owner": "bytedance",
        "model": "seedance-1-pro-fast",
        "description": "Fast, official ByteDance model"
    },
    {
        "name": "wan-video/wan-2.2-i2v-fast",
        "owner": "wan-video",
        "model": "wan-2.2-i2v-fast",
        "description": "Fast image-to-video"
    },
    {
        "name": "kwaivgi/kling-v2.1",
        "owner": "kwaivgi",
        "model": "kling-v2.1",
        "description": "High quality Kling model"
    },
]


def get_model_versions(owner: str, model: str):
    """Get available versions for a model."""
    try:
        url = f"https://api.replicate.com/v1/models/{owner}/{model}/versions"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("results", [])
        else:
            return None
    except Exception as e:
        print(f"  Error fetching versions: {e}")
        return None


def test_version(version_id: str, owner: str, model: str):
    """Test if a version is accessible."""
    try:
        # Try to get version details
        url = f"https://api.replicate.com/v1/models/{owner}/{model}/versions/{version_id}"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, None
    except Exception as e:
        return False, None


def main():
    print("=" * 80)
    print("Finding Available Versions for Video Generation Models")
    print("=" * 80)
    print()
    
    results = {}
    
    for model_info in MODELS_TO_CHECK:
        print(f"Checking: {model_info['name']}")
        print(f"  Description: {model_info['description']}")
        print(f"  URL: https://replicate.com/{model_info['name']}")
        
        versions = get_model_versions(model_info['owner'], model_info['model'])
        
        if versions is None:
            print(f"  ⚠️  Could not fetch versions (may not exist or API issue)")
            print()
            continue
        
        if not versions:
            print(f"  ⚠️  No versions found")
            print()
            continue
        
        # Sort by creation date (newest first)
        sorted_versions = sorted(
            versions,
            key=lambda v: v.get("created_at", ""),
            reverse=True
        )
        
        print(f"  ✓ Found {len(sorted_versions)} version(s):")
        print()
        
        for i, version in enumerate(sorted_versions[:3], 1):  # Show top 3
            version_id = version.get("id", "unknown")
            created = version.get("created_at", "Unknown")
            
            # Test if accessible
            is_accessible, version_data = test_version(version_id, model_info['owner'], model_info['model'])
            
            status = "✓ ACCESSIBLE" if is_accessible else "⚠️  Check manually"
            
            print(f"    {i}. Version: {version_id[:20]}...")
            print(f"       Created: {created}")
            print(f"       Status: {status}")
            print(f"       URL: https://replicate.com/{model_info['name']}/versions/{version_id}")
            
            if is_accessible and version_data:
                openapi = version_data.get("openapi_schema", {})
                if openapi:
                    print(f"       ✓ Schema available")
            
            print()
        
        # Store latest version
        if sorted_versions:
            latest = sorted_versions[0]
            results[model_info['name']] = {
                "latest_version": latest.get("id"),
                "accessible": test_version(latest.get("id"), model_info['owner'], model_info['model'])[0],
                "url": f"https://replicate.com/{model_info['name']}"
            }
        
        print("-" * 80)
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY - Recommended Versions")
    print("=" * 80)
    print()
    
    for model_name, info in results.items():
        status_icon = "✅" if info['accessible'] else "⚠️"
        print(f"{status_icon} {model_name}")
        print(f"   Latest Version: {info['latest_version']}")
        print(f"   URL: {info['url']}")
        print()
    
    print("=" * 80)
    print("How to Use")
    print("=" * 80)
    print("""
1. Choose a model from the list above
2. Copy the version ID
3. Update your .env file:
   SVD_MODEL_VERSION=<version_id>
   
   Or update config.py:
   SVD_MODEL_VERSION = os.getenv("SVD_MODEL_VERSION", "<version_id>")
   SVD_MODEL = f"<owner>/<model>:{SVD_MODEL_VERSION}"

4. Test with:
   python3 test_svd_version.py
    """)


if __name__ == "__main__":
    main()

