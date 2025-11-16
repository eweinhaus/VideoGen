#!/usr/bin/env python3
"""
Check Replicate account for available Stable Video Diffusion versions.

This script helps you:
1. List all available versions of Stable Video Diffusion on Replicate
2. Verify which version your code is currently using
3. Test if a specific version is accessible with your API token

Usage:
    python check_replicate_svd_version.py
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import replicate
    import requests
except ImportError as e:
    missing = str(e).split("'")[1] if "'" in str(e) else "package"
    print(f"ERROR: {missing} not installed.")
    if "replicate" in missing.lower():
        print("Install with: pip install replicate")
    if "requests" in missing.lower():
        print("Install with: pip install requests")
    sys.exit(1)

# Check API token
api_token = os.getenv("REPLICATE_API_TOKEN")
if not api_token:
    print("ERROR: REPLICATE_API_TOKEN not found in environment.")
    print("Please set it in your .env file or export it as an environment variable.")
    sys.exit(1)

# Set API token explicitly
os.environ['REPLICATE_API_TOKEN'] = api_token
print(f"✓ API Token found: {api_token[:20]}...{api_token[-4:]}\n")

# Get current version from config
try:
    from modules.video_generator.config import SVD_MODEL_VERSION, SVD_MODEL
    print(f"Current configured version: {SVD_MODEL_VERSION}")
    print(f"Current full model string: {SVD_MODEL}\n")
except Exception as e:
    print(f"Warning: Could not load config: {e}\n")
    SVD_MODEL_VERSION = None
    SVD_MODEL = None


def check_model_versions():
    """Check available versions for Stable Video Diffusion using Replicate HTTP API."""
    print("=" * 70)
    print("Checking Stable Video Diffusion versions on Replicate...")
    print("=" * 70)
    
    import requests
    
    model_owner = "stability-ai"
    model_name = "stable-video-diffusion"
    
    try:
        # Get model information
        print(f"\nFetching model: {model_owner}/{model_name}")
        model_url = f"https://api.replicate.com/v1/models/{model_owner}/{model_name}"
        headers = {"Authorization": f"Bearer {api_token}"}
        
        response = requests.get(model_url, headers=headers)
        if response.status_code == 200:
            model_data = response.json()
            print(f"\n✓ Model found: {model_data.get('name', model_name)}")
            print(f"  Description: {model_data.get('description', 'No description')}")
            print(f"  Visibility: {model_data.get('visibility', 'unknown')}")
        else:
            print(f"  ⚠ Could not fetch model details: {response.status_code}")
        
        # Get versions (this endpoint may not be available for all models)
        print(f"\nFetching available versions...")
        versions_url = f"https://api.replicate.com/v1/models/{model_owner}/{model_name}/versions"
        response = requests.get(versions_url, headers=headers)
        
        if response.status_code == 200:
            versions_data = response.json()
            versions = versions_data.get("results", [])
            
            if versions:
                print(f"\n✓ Found {len(versions)} version(s):\n")
                
                # Sort versions by creation date (newest first)
                sorted_versions = sorted(
                    versions, 
                    key=lambda v: v.get("created_at", ""), 
                    reverse=True
                )
                
                for i, version in enumerate(sorted_versions, 1):
                    version_id = version.get("id", "unknown")
                    created = version.get("created_at", "Unknown")
                    if created and created != "Unknown":
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            created = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                    
                    # Check if this is the currently configured version
                    is_current = ""
                    if SVD_MODEL_VERSION and version_id == SVD_MODEL_VERSION:
                        is_current = " ← CURRENTLY CONFIGURED"
                    
                    print(f"  {i}. Version: {version_id}")
                    print(f"     Created: {created}")
                    print(f"     URL: https://replicate.com/{model_owner}/{model_name}/versions/{version_id}{is_current}\n")
                
                # Show latest version
                if sorted_versions:
                    latest = sorted_versions[0]
                    latest_id = latest.get("id", "unknown")
                    if latest_id != SVD_MODEL_VERSION:
                        print(f"⚠ Your configured version ({SVD_MODEL_VERSION}) is not the latest.")
                        print(f"  Latest version: {latest_id}")
                        print(f"  Consider updating: Set SVD_MODEL_VERSION={latest_id} in your .env file")
                    else:
                        print("✓ You are using the latest version!")
            else:
                print("  ⚠ No versions found in response")
        else:
            print(f"  ⚠ Versions list endpoint not available (HTTP {response.status_code})")
            print("  This is normal - not all models expose versions via API.")
            print("  Visit https://replicate.com/stability-ai/stable-video-diffusion to see all versions.")
        
        # Test current version if configured
        if SVD_MODEL_VERSION:
            print("\n" + "=" * 70)
            print(f"Testing configured version: {SVD_MODEL_VERSION}")
            print("=" * 70)
            test_version(SVD_MODEL_VERSION)
        
    except ImportError:
        print("\n❌ Error: 'requests' library not installed.")
        print("Install it with: pip install requests")
    except Exception as e:
        print(f"\n❌ Error checking versions: {e}")
        import traceback
        traceback.print_exc()


def test_version(version_id: str):
    """Test if a specific version is accessible."""
    print(f"\nTesting version: {version_id}")
    
    try:
        import requests
        
        # Try to get version details via HTTP API
        version_url = f"https://api.replicate.com/v1/models/stability-ai/stable-video-diffusion/versions/{version_id}"
        headers = {"Authorization": f"Bearer {api_token}"}
        
        response = requests.get(version_url, headers=headers)
        
        if response.status_code == 200:
            version_data = response.json()
            print(f"✓ Version accessible: {version_data.get('id', version_id)}")
            
            created = version_data.get("created_at", "Unknown")
            if created and created != "Unknown":
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            print(f"  Created: {created}")
            
            # Try to get schema (input/output parameters)
            openapi_schema = version_data.get("openapi_schema", {})
            if openapi_schema and "components" in openapi_schema:
                components = openapi_schema.get("components", {})
                schemas = components.get("schemas", {})
                input_schema = schemas.get("Input", {})
                properties = input_schema.get("properties", {})
                if properties:
                    print(f"\n  Available input parameters:")
                    for param, details in list(properties.items())[:5]:  # Show first 5
                        param_type = details.get("type", "unknown")
                        param_desc = details.get("description", "")
                        desc_text = f" - {param_desc}" if param_desc else ""
                        print(f"    - {param}: {param_type}{desc_text}")
            
            return True
        else:
            print(f"❌ Version not accessible: HTTP {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            print(f"  This version may not exist or may not be available with your API token.")
            return False
        
    except ImportError:
        print("❌ Error: 'requests' library not installed.")
        return False
    except Exception as e:
        print(f"❌ Error testing version: {e}")
        return False


def show_usage_instructions():
    """Show instructions for updating the version."""
    print("\n" + "=" * 70)
    print("How to Update the Version")
    print("=" * 70)
    print("""
1. Set environment variable in your .env file:
   SVD_MODEL_VERSION=<version_id>

2. Or update the default in config.py:
   SVD_MODEL_VERSION = os.getenv("SVD_MODEL_VERSION", "<version_id>")

3. Restart your application to use the new version.

Note: Pinning to a specific version (not "latest") is recommended for:
   - Predictable behavior
   - Consistent costs
   - Easier debugging
   - Production stability
""")


if __name__ == "__main__":
    try:
        check_model_versions()
        show_usage_instructions()
        
        print("\n" + "=" * 70)
        print("Additional Resources")
        print("=" * 70)
        print("""
- Replicate Dashboard: https://replicate.com/account
- Model Page: https://replicate.com/stability-ai/stable-video-diffusion
- API Docs: https://replicate.com/docs/reference/http
- Python Client: https://github.com/replicate/replicate-python
        """)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

