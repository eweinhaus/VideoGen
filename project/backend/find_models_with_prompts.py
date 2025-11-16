#!/usr/bin/env python3
"""
Find models that support both image AND text prompts (image-to-video with prompts).
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    import replicate
    import requests
except ImportError:
    print("ERROR: Install packages: pip install replicate requests")
    sys.exit(1)

api_token = os.getenv("REPLICATE_API_TOKEN")
if not api_token:
    print("ERROR: REPLICATE_API_TOKEN not found")
    sys.exit(1)

# Models that likely support image + prompt
MODELS = [
    {"owner": "bytedance", "model": "seedance-1-pro-fast", "name": "bytedance/seedance-1-pro-fast"},
    {"owner": "wan-video", "model": "wan-2.2-i2v-fast", "name": "wan-video/wan-2.2-i2v-fast"},
    {"owner": "kwaivgi", "model": "kling-v2.1", "name": "kwaivgi/kling-v2.1"},
    {"owner": "pixverse", "model": "pixverse-v4.5", "name": "pixverse/pixverse-v4.5"},
    {"owner": "wavespeedai", "model": "wan-2.1-i2v-480p", "name": "wavespeedai/wan-2.1-i2v-480p"},
]

def get_model_info(owner, model):
    """Get model information and check if it supports image + prompt."""
    try:
        url = f"https://api.replicate.com/v1/models/{owner}/{model}"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        return response.json()
    except Exception as e:
        return None

def get_versions(owner, model):
    """Get available versions."""
    try:
        url = f"https://api.replicate.com/v1/models/{owner}/{model}/versions"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("results", [])
        return None
    except:
        return None

def check_supports_prompts(owner, model, version_id):
    """Check if model version supports image + text prompts."""
    try:
        url = f"https://api.replicate.com/v1/models/{owner}/{model}/versions/{version_id}"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return False, None
        
        data = response.json()
        schema = data.get("openapi_schema", {})
        
        if not schema or "components" not in schema:
            return False, None
        
        inputs = schema.get("components", {}).get("schemas", {}).get("Input", {}).get("properties", {})
        
        # Check for both image and prompt parameters
        has_image = any("image" in key.lower() for key in inputs.keys())
        has_prompt = any("prompt" in key.lower() for key in inputs.keys())
        
        return has_image and has_prompt, inputs
    except:
        return False, None

def main():
    print("=" * 80)
    print("Finding Models That Support Image + Text Prompts")
    print("=" * 80)
    print()
    
    results = []
    
    for model_info in MODELS:
        print(f"Checking: {model_info['name']}")
        
        # Get model info
        model_data = get_model_info(model_info['owner'], model_info['model'])
        if not model_data:
            print(f"  ⚠️  Model not found or not accessible")
            print()
            continue
        
        # Get versions
        versions = get_versions(model_info['owner'], model_info['model'])
        if not versions:
            print(f"  ⚠️  Could not fetch versions")
            print()
            continue
        
        # Sort by date (newest first)
        sorted_versions = sorted(versions, key=lambda v: v.get("created_at", ""), reverse=True)
        latest = sorted_versions[0]
        version_id = latest.get("id")
        
        # Check if supports prompts
        supports_prompts, input_params = check_supports_prompts(
            model_info['owner'], model_info['model'], version_id
        )
        
        status = "✅ SUPPORTS PROMPTS" if supports_prompts else "❌ Image only"
        
        print(f"  {status}")
        print(f"  Latest Version: {version_id}")
        print(f"  URL: https://replicate.com/{model_info['name']}")
        
        if supports_prompts and input_params:
            print(f"  Input Parameters:")
            for param in list(input_params.keys())[:8]:  # Show first 8
                param_type = input_params[param].get("type", "unknown")
                print(f"    - {param}: {param_type}")
        
        print()
        
        if supports_prompts:
            results.append({
                "name": model_info['name'],
                "owner": model_info['owner'],
                "model": model_info['model'],
                "version": version_id,
                "url": f"https://replicate.com/{model_info['name']}",
                "inputs": input_params
            })
        
        print("-" * 80)
        print()
    
    # Summary
    print("=" * 80)
    print("RECOMMENDED MODELS (Support Image + Prompts)")
    print("=" * 80)
    print()
    
    if not results:
        print("❌ No models found that support both image and prompts")
        print("   You may need to use image-only models or check manually")
    else:
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['name']}")
            print(f"   Version: {result['version']}")
            print(f"   URL: {result['url']}")
            print()
    
    # Save results
    if results:
        import json
        with open("model_recommendations.json", "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Saved recommendations to: model_recommendations.json")
        print()
        print("Best match: " + results[0]['name'])

if __name__ == "__main__":
    main()

