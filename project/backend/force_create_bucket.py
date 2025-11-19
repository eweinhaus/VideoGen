#!/usr/bin/env python3
"""
Force create a Supabase Storage bucket via REST API.

This script uses the Supabase REST API to create storage buckets programmatically.
Useful when the bucket is missing and causing silent upload failures.
"""
import sys
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("force_create_bucket")

# Bucket configuration
BUCKET_CONFIG = {
    "clip-thumbnails": {
        "public": False,
        "file_size_limit": 1 * 1024 * 1024,  # 1MB
        "allowed_mime_types": ["image/jpeg", "image/jpg"]
    }
}


def create_bucket_via_api(bucket_name: str, config: dict) -> bool:
    """
    Create a storage bucket using Supabase REST API.
    
    Args:
        bucket_name: Name of the bucket to create
        config: Bucket configuration
        
    Returns:
        True if successful, False otherwise
    """
    # Extract project reference from Supabase URL
    # URL format: https://<project-ref>.supabase.co
    supabase_url = settings.supabase_url
    if "/rest/v1" in supabase_url:
        base_url = supabase_url.replace("/rest/v1", "")
    else:
        base_url = supabase_url.rstrip("/")
    
    # Storage API endpoint
    storage_url = f"{base_url}/storage/v1/bucket"
    
    # Request payload
    payload = {
        "name": bucket_name,
        "public": config["public"],
        "file_size_limit": config["file_size_limit"],
        "allowed_mime_types": config.get("allowed_mime_types", [])
    }
    
    # Headers
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
        "apikey": settings.supabase_service_key
    }
    
    try:
        print(f"Creating bucket '{bucket_name}' via API...")
        print(f"  URL: {storage_url}")
        print(f"  Public: {config['public']}")
        print(f"  File size limit: {config['file_size_limit'] / (1024*1024):.0f}MB")
        
        response = requests.post(
            storage_url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"  ✅ Bucket '{bucket_name}' created successfully!")
            return True
        elif response.status_code == 409:
            print(f"  ℹ️  Bucket '{bucket_name}' already exists")
            return True
        else:
            print(f"  ❌ Failed to create bucket: {response.status_code}")
            print(f"     Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error creating bucket: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False


def verify_bucket_exists(bucket_name: str) -> bool:
    """
    Verify that a bucket exists and is accessible.
    
    Args:
        bucket_name: Name of the bucket
        
    Returns:
        True if bucket exists and is accessible, False otherwise
    """
    try:
        from supabase import create_client
        client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
        
        # Try to list files in the bucket (will fail if bucket doesn't exist)
        try:
            client.storage.from_(bucket_name).list()
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                return False
            # Other errors might mean bucket exists but is empty or has permission issues
            # For our purposes, if we can call list(), bucket exists
            return True
    except Exception as e:
        print(f"  ⚠️  Error verifying bucket: {e}")
        return False


def main():
    """Force create clip-thumbnails bucket."""
    print("=" * 60)
    print("Force Create Storage Bucket")
    print("=" * 60)
    print()
    
    bucket_name = "clip-thumbnails"
    config = BUCKET_CONFIG[bucket_name]
    
    # Check if bucket already exists
    print(f"Checking if bucket '{bucket_name}' exists...")
    if verify_bucket_exists(bucket_name):
        print(f"  ✅ Bucket '{bucket_name}' already exists and is accessible")
        print()
        print("No action needed. Bucket is ready to use.")
        return 0
    
    print(f"  ✗ Bucket '{bucket_name}' does not exist")
    print()
    
    # Create bucket
    success = create_bucket_via_api(bucket_name, config)
    
    if success:
        # Verify creation
        print()
        print("Verifying bucket creation...")
        if verify_bucket_exists(bucket_name):
            print(f"  ✅ Bucket '{bucket_name}' verified and ready to use!")
            print()
            print("Next steps:")
            print("  1. Run fix_job_data.py to backfill thumbnails for existing jobs")
            print("  2. New jobs will automatically generate thumbnails")
            return 0
        else:
            print(f"  ⚠️  Bucket creation reported success but verification failed")
            print(f"     You may need to create it manually via Supabase Dashboard")
            return 1
    else:
        print()
        print("Failed to create bucket via API.")
        print("Alternative: Create bucket manually via Supabase Dashboard:")
        print(f"  1. Go to: {settings.supabase_url.replace('/rest/v1', '')}/project/_/storage/buckets")
        print(f"  2. Click 'New bucket'")
        print(f"  3. Name: {bucket_name}")
        print(f"  4. Public: {'Yes' if config['public'] else 'No'}")
        print(f"  5. File size limit: {config['file_size_limit'] / (1024*1024):.0f}MB")
        return 1


if __name__ == "__main__":
    sys.exit(main())

