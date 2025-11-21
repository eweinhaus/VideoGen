#!/usr/bin/env python3
"""
Check if job fdde43cf-b811-4b7f-8143-ed6aecd8f19e had a character image uploaded
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
env_path = Path(__file__).parent / "project" / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

job_id = "fdde43cf-b811-4b7f-8143-ed6aecd8f19e"

# Get Supabase credentials
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
    sys.exit(1)

# Create Supabase client
supabase = create_client(supabase_url, supabase_key)

print(f"=== CHECKING UPLOAD INFO FOR JOB {job_id} ===\n")

# Get job details
job_result = supabase.table("jobs").select("*").eq("id", job_id).execute()

if not job_result.data:
    print(f"ERROR: Job {job_id} not found")
    sys.exit(1)

job = job_result.data[0]

# Check if user_id exists to query storage
user_id = job.get("user_id")
print(f"User ID: {user_id}")
print(f"Job ID: {job_id}")
print()

# Try to list files in reference-images bucket for this user/job
print("=== CHECKING SUPABASE STORAGE ===\n")

try:
    # List files in the path where character images should be
    storage_path = f"{user_id}/{job_id}/character_references/"
    
    print(f"Checking storage path: {storage_path}")
    
    # List files
    files = supabase.storage.from_("reference-images").list(storage_path)
    
    if files:
        print(f"\n✓ Found {len(files)} file(s) in character_references folder:")
        for file in files:
            print(f"   - {file['name']} (size: {file.get('metadata', {}).get('size', 'unknown')} bytes)")
            if file['name'].startswith('main_character'):
                print(f"     ^ THIS IS A USER-UPLOADED CHARACTER IMAGE")
    else:
        print(f"\n✗ No files found in {storage_path}")
        print(f"   This means NO character image was uploaded for this job.")
except Exception as e:
    print(f"\nERROR accessing storage: {e}")
    print(f"This could mean:")
    print(f"1. No character image was uploaded")
    print(f"2. The bucket doesn't exist")
    print(f"3. Permission issues")

print(f"\n=== CHECKING JOB STAGES FOR UPLOAD METADATA ===\n")

# Check job_stages for any upload-related metadata
stages_result = supabase.table("job_stages").select("*").eq("job_id", job_id).execute()

for stage in stages_result.data:
    stage_name = stage["stage_name"]
    metadata = stage.get("metadata", {})
    
    # Check if metadata contains any upload-related info
    if "uploaded" in json.dumps(metadata).lower() or "user_uploaded" in json.dumps(metadata).lower():
        print(f"Stage '{stage_name}' contains upload-related metadata:")
        print(json.dumps(metadata, indent=2, default=str)[:500])
        print()

print(f"\n=== FINAL DIAGNOSIS ===\n")
print(f"Based on the findings:")
print(f"1. If NO files found in storage: You likely did NOT upload a character image")
print(f"2. If files found but not in reference_generator: The upload failed to pass through the pipeline")
print(f"3. If no 'user_uploaded' in metadata: The character matching failed")

