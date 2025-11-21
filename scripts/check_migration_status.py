#!/usr/bin/env python3
"""
Check if the template migration has already been applied.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "project" / "backend"))

def check_migration():
    """Check if migration columns exist."""
    try:
        from shared.database import DatabaseClient
        
        print("Checking migration status...")
        db_client = DatabaseClient()
        
        # Try to query the jobs table with the new columns
        # If columns don't exist, this will fail
        import asyncio
        
        async def check():
            try:
                # Try to select one of the new columns
                result = await db_client.table("jobs").select("template, video_model, aspect_ratio").limit(1).execute()
                print("✅ Migration already applied! Columns exist:")
                print("  - template")
                print("  - video_model") 
                print("  - aspect_ratio")
                return True
            except Exception as e:
                error_msg = str(e).lower()
                if "template" in error_msg or "column" in error_msg or "pgrst" in error_msg:
                    print("❌ Migration not applied. Columns are missing.")
                    print(f"   Error: {str(e)[:200]}")
                    return False
                else:
                    # Other error, might be connection issue
                    print(f"⚠️  Could not verify: {str(e)[:200]}")
                    return None
        
        result = asyncio.run(check())
        return result
        
    except Exception as e:
        print(f"❌ Error checking migration: {str(e)}")
        return None

if __name__ == "__main__":
    result = check_migration()
    if result is False:
        print("\n📋 To apply the migration, run the SQL in Supabase SQL Editor:")
        print("   https://supabase.com/dashboard/project/hpjpsachyrnzobswmhnh/sql/new")
        sys.exit(1)
    elif result is True:
        print("\n✅ No action needed - migration is already applied!")
        sys.exit(0)
    else:
        print("\n⚠️  Could not determine migration status")
        sys.exit(2)

