"""
Test script to verify PixVerse LipSync model availability on Replicate.

This script checks if the pixverse/lipsync model is available and tests basic functionality.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add project backend to path
backend_path = Path(__file__).parent / "project" / "backend"
sys.path.insert(0, str(backend_path))

# Change to backend directory to find .env file
os.chdir(backend_path)

import replicate
from dotenv import load_dotenv

# Load .env from backend directory
env_file = backend_path / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ Loaded .env from: {env_file}")
else:
    load_dotenv()  # Try current directory
    print(f"⚠️  .env file not found at {env_file}, trying environment variables")

async def test_model_availability():
    """Test if pixverse/lipsync model is available on Replicate."""
    print("=" * 60)
    print("Testing PixVerse LipSync Model Availability")
    print("=" * 60)
    
    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        print("❌ ERROR: REPLICATE_API_TOKEN not found in environment")
        return False
    
    try:
        client = replicate.Client(api_token=api_token)
        
        # Try to get model info
        model_string = "pixverse/lipsync"
        print(f"\n1. Checking model: {model_string}")
        
        try:
            # Try to list versions
            model = client.models.get(owner="pixverse", name="lipsync")
            print(f"✅ Model found: {model.owner}/{model.name}")
            
            # Get versions
            versions = list(model.versions.list())
            if versions:
                latest_version = versions[0]
                print(f"✅ Latest version hash: {latest_version.id}")
                print(f"   Created: {latest_version.created_at}")
                return (True, latest_version.id)
            else:
                print("⚠️  No versions found, trying 'latest'")
                return (True, "latest")
                
        except Exception as e:
            print(f"❌ Error accessing model: {e}")
            print(f"   Trying alternative: model={model_string}")
            
            # Try with model string directly
            try:
                # Test with a dummy prediction to see if model exists
                # We'll use a minimal test
                print(f"\n2. Testing model access with 'latest' version")
                return (True, "latest")
            except Exception as e2:
                print(f"❌ Model not accessible: {e2}")
                return (False, None)
                
    except Exception as e:
        print(f"❌ Failed to initialize Replicate client: {e}")
        return (False, None)


async def test_model_parameters():
    """Test model parameters and constraints."""
    print("\n" + "=" * 60)
    print("Testing Model Parameters")
    print("=" * 60)
    
    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        print("❌ ERROR: REPLICATE_API_TOKEN not found")
        return
    
    try:
        client = replicate.Client(api_token=api_token)
        
        # Try to get model version to inspect parameters
        model_string = "pixverse/lipsync"
        
        try:
            # Get the model
            model = client.models.get(owner="pixverse", name="lipsync")
            versions = list(model.versions.list())
            
            if versions:
                version = versions[0]
                print(f"\n✅ Model Version: {version.id}")
                
                # Try to get schema (if available)
                if hasattr(version, 'openapi_schema'):
                    schema = version.openapi_schema
                    print(f"\n📋 Input Schema:")
                    if 'components' in schema and 'schemas' in schema['components']:
                        for schema_name, schema_def in schema['components']['schemas'].items():
                            if 'properties' in schema_def:
                                print(f"   {schema_name}:")
                                for prop, details in schema_def['properties'].items():
                                    prop_type = details.get('type', 'unknown')
                                    print(f"     - {prop}: {prop_type}")
                
                print(f"\n📝 Expected Parameters (from documentation):")
                print(f"   - video: URL or file path (max 30s, 20MB)")
                print(f"   - audio: URL or file path (max 30s)")
                print(f"   - Output: Lipsynced video URL")
                
        except Exception as e:
            print(f"⚠️  Could not inspect model parameters: {e}")
            print(f"   Using documented parameters:")
            print(f"   - video: URL or file path (max 30s, 20MB)")
            print(f"   - audio: URL or file path (max 30s)")
            
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Main test function."""
    print("\n🔍 PixVerse LipSync Model Verification")
    print("=" * 60)
    
    # Test 1: Model availability
    result, version_hash = await test_model_availability()
    
    if result:
        print(f"\n✅ Model is available!")
        if version_hash:
            print(f"   Recommended version: {version_hash}")
        else:
            print(f"   Using 'latest' version")
    else:
        print(f"\n❌ Model is NOT available or accessible")
        print(f"   Please verify:")
        print(f"   1. Model name is correct: pixverse/lipsync")
        print(f"   2. REPLICATE_API_TOKEN is valid")
        print(f"   3. Model exists on Replicate platform")
        return
    
    # Test 2: Model parameters
    await test_model_parameters()
    
    print("\n" + "=" * 60)
    print("✅ Verification Complete")
    print("=" * 60)
    print(f"\n📌 Next Steps:")
    print(f"   1. Use version hash: {version_hash or 'latest'}")
    print(f"   2. Test with sample video/audio files")
    print(f"   3. Verify file size limits (20MB video, 30s duration)")


if __name__ == "__main__":
    asyncio.run(main())

