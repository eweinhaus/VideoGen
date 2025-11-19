#!/usr/bin/env python3
"""
Create required Supabase Storage buckets.

This script creates all required storage buckets for the video generation pipeline.
"""
import asyncio
import sys
import os
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from supabase import create_client
from shared.config import settings
from shared.logging import get_logger

logger = get_logger("create_buckets")

# Required buckets and their configurations
REQUIRED_BUCKETS = {
    "audio-uploads": {
        "public": False,
        "file_size_limit": 10 * 1024 * 1024,  # 10MB
        "allowed_mime_types": ["audio/mpeg", "audio/wav", "audio/flac", "audio/mp3"]
    },
    "reference-images": {
        "public": False,
        "file_size_limit": 5 * 1024 * 1024,  # 5MB
        "allowed_mime_types": ["image/png", "image/jpeg", "image/jpg"]
    },
    "video-clips": {
        "public": False,
        "file_size_limit": 50 * 1024 * 1024,  # 50MB
        "allowed_mime_types": ["video/mp4", "video/mpeg"]
    },
    "video-outputs": {
        "public": False,
        "file_size_limit": 500 * 1024 * 1024,  # 500MB
        "allowed_mime_types": ["video/mp4"]
    },
    "clip-thumbnails": {
        "public": False,
        "file_size_limit": 1 * 1024 * 1024,  # 1MB (thumbnails are small)
        "allowed_mime_types": ["image/jpeg", "image/jpg"]
    }
}


def create_bucket(client, bucket_name: str, config: dict):
    """
    Create a storage bucket in Supabase.
    
    Args:
        client: Supabase client
        bucket_name: Name of the bucket
        config: Bucket configuration (public, file_size_limit, etc.)
    """
    try:
        # Check if bucket already exists
        try:
            existing = client.storage.get_bucket(bucket_name)
            if existing:
                print(f"  ✓ Bucket '{bucket_name}' already exists")
                return True
        except Exception:
            # Bucket doesn't exist, create it
            pass
        
        # Create bucket
        # Note: Supabase Python client doesn't have a direct create_bucket method
        # We need to use the REST API or Supabase dashboard
        # For now, we'll provide instructions
        
        print(f"  ⚠️  Bucket '{bucket_name}' needs to be created manually")
        print(f"     Go to: {settings.supabase_url.replace('/rest/v1', '')}/project/_/storage/buckets")
        print(f"     Create bucket: {bucket_name}")
        print(f"     Public: {config['public']}")
        print(f"     File size limit: {config['file_size_limit'] / (1024*1024):.0f}MB")
        return False
        
    except Exception as e:
        print(f"  ❌ Error checking/creating bucket '{bucket_name}': {e}")
        return False


def main():
    """Create all required storage buckets."""
    print("Creating Supabase Storage buckets...")
    print(f"Supabase URL: {settings.supabase_url}")
    print()
    
    try:
        client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
        
        created = []
        existing = []
        failed = []
        
        for bucket_name, config in REQUIRED_BUCKETS.items():
            print(f"Checking bucket: {bucket_name}")
            try:
                # Try to access the bucket
                result = client.storage.from_(bucket_name).list()
                print(f"  ✓ Bucket '{bucket_name}' exists and is accessible")
                existing.append(bucket_name)
            except Exception as e:
                error_str = str(e).lower()
                if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                    print(f"  ✗ Bucket '{bucket_name}' does not exist")
                    print(f"     Creating...")
                    
                    # Try to create via API (may not work with Python client)
                    try:
                        # Supabase Python client doesn't have create_bucket
                        # We'll provide manual instructions
                        print(f"     ⚠️  Manual creation required:")
                        print(f"        1. Go to Supabase Dashboard → Storage")
                        print(f"        2. Click 'New bucket'")
                        print(f"        3. Name: {bucket_name}")
                        print(f"        4. Public: {'Yes' if config['public'] else 'No'}")
                        print(f"        5. File size limit: {config['file_size_limit'] / (1024*1024):.0f}MB")
                        print()
                        failed.append(bucket_name)
                    except Exception as create_error:
                        print(f"     ❌ Failed to create: {create_error}")
                        failed.append(bucket_name)
                else:
                    print(f"  ⚠️  Error accessing bucket: {e}")
                    failed.append(bucket_name)
        
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if existing:
            print(f"✅ Existing buckets ({len(existing)}): {', '.join(existing)}")
        if failed:
            print(f"❌ Missing buckets ({len(failed)}): {', '.join(failed)}")
            print()
            print("To create missing buckets:")
            print("1. Go to your Supabase Dashboard")
            print("2. Navigate to Storage → Buckets")
            print("3. Click 'New bucket' for each missing bucket")
            print("4. Configure as follows:")
            print()
            for bucket_name in failed:
                config = REQUIRED_BUCKETS[bucket_name]
                print(f"   {bucket_name}:")
                print(f"     - Public: {config['public']}")
                print(f"     - File size limit: {config['file_size_limit'] / (1024*1024):.0f}MB")
        
        if not failed:
            print("✅ All required buckets exist!")
            return 0
        else:
            return 1
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

