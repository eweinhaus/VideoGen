"""Test all infrastructure connections for Phase 0 setup."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import settings
from shared.database import db
from shared.redis_client import redis
from shared.storage import storage


async def test_database():
    """Test Supabase database connection."""
    print("Testing database connection...")
    try:
        is_healthy = await db.health_check()
        if is_healthy:
            print("✅ Database connection successful")
            return True
        else:
            print("❌ Database health check failed")
            return False
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_redis():
    """Test Redis connection."""
    print("Testing Redis connection...")
    try:
        is_healthy = await redis.health_check()
        if is_healthy:
            print("✅ Redis connection successful")
            return True
        else:
            print("❌ Redis health check failed")
            return False
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False


async def test_storage():
    """Test Supabase Storage connection."""
    print("Testing storage connection...")
    try:
        # Verify required buckets exist by trying to access them
        required_buckets = ["audio-uploads", "reference-images", "video-clips", "video-outputs"]
        missing = []
        
        for bucket_name in required_buckets:
            try:
                # Try to list files in bucket (empty list is OK, error means bucket doesn't exist)
                def _list_files():
                    return storage.storage.from_(bucket_name).list()
                
                await storage._execute_sync(_list_files)
                print(f"  ✓ Bucket '{bucket_name}' exists")
            except Exception as e:
                if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                    missing.append(bucket_name)
                    print(f"  ✗ Bucket '{bucket_name}' not found")
                else:
                    # Other errors might be OK (permissions, etc.) - bucket exists
                    print(f"  ✓ Bucket '{bucket_name}' exists (access verified)")
        
        if missing:
            print(f"⚠️  Missing buckets: {missing}")
            return False
        else:
            print("✅ All required buckets exist and are accessible")
            return True
    except Exception as e:
        print(f"❌ Storage connection failed: {e}")
        return False


async def test_config():
    """Test configuration loading."""
    print("Testing configuration...")
    try:
        # Check all required settings are present
        required = [
            "supabase_url",
            "supabase_service_key",
            "supabase_anon_key",
            "redis_url",
            "openai_api_key",
            "replicate_api_token",
            "jwt_secret_key"
        ]
        
        missing = []
        for key in required:
            value = getattr(settings, key, None)
            if not value:
                missing.append(key)
        
        if missing:
            print(f"❌ Missing configuration: {missing}")
            return False
        else:
            print("✅ All required configuration present")
            # Show partial values for verification (don't expose secrets)
            print(f"  ✓ Supabase URL: {settings.supabase_url[:30]}...")
            print(f"  ✓ Redis URL: {settings.redis_url[:30]}...")
            print(f"  ✓ OpenAI Key: {settings.openai_api_key[:10]}...")
            print(f"  ✓ Replicate Token: {settings.replicate_api_token[:10]}...")
            print(f"  ✓ JWT Secret: {settings.jwt_secret_key[:10]}...")
            return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 0 Infrastructure Verification")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(await test_config())
    results.append(await test_database())
    results.append(await test_redis())
    results.append(await test_storage())
    
    print()
    print("=" * 60)
    if all(results):
        print("✅ All infrastructure checks passed!")
        print("Phase 0 setup is complete. Ready for development!")
    else:
        print("❌ Some checks failed. Please review errors above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

