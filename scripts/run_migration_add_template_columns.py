#!/usr/bin/env python3
"""
Run migration to add video_model, aspect_ratio, and template columns to jobs table.

This script connects directly to the PostgreSQL database to execute the migration SQL.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "project" / "backend"))

from shared.config import settings
import asyncpg


async def run_migration():
    """Run the migration to add template, video_model, and aspect_ratio columns."""
    
    # Read migration SQL file
    migration_file = project_root / "supabase" / "migrations" / "20250120000000_add_video_model_aspect_ratio_template.sql"
    
    if not migration_file.exists():
        print(f"Error: Migration file not found at {migration_file}")
        sys.exit(1)
    
    with open(migration_file, "r") as f:
        migration_sql = f.read()
    
    # Extract database connection info from Supabase URL
    # Supabase URL format: https://<project-ref>.supabase.co
    # We need to construct the direct PostgreSQL connection string
    supabase_url = settings.supabase_url
    
    # Parse Supabase URL to get project ref
    if ".supabase.co" in supabase_url:
        project_ref = supabase_url.replace("https://", "").replace(".supabase.co", "")
    else:
        print(f"Error: Could not parse Supabase URL: {supabase_url}")
        print("Please set SUPABASE_DB_URL environment variable with direct PostgreSQL connection string")
        print("Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres")
        sys.exit(1)
    
    # Try to get direct database connection string from environment
    # This should be set as: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
    import os
    db_url = os.getenv("SUPABASE_DB_URL")
    
    if not db_url:
        print("Error: SUPABASE_DB_URL environment variable not set")
        print("Please set it with your direct PostgreSQL connection string:")
        print("Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres")
        print(f"Example: postgresql://postgres:your_password@db.{project_ref}.supabase.co:5432/postgres")
        sys.exit(1)
    
    try:
        print("Connecting to database...")
        conn = await asyncpg.connect(db_url)
        
        print("Running migration...")
        print("=" * 60)
        print(migration_sql)
        print("=" * 60)
        
        # Execute migration SQL
        await conn.execute(migration_sql)
        
        print("\n✅ Migration completed successfully!")
        print("\nAdded columns:")
        print("  - video_model VARCHAR(50) DEFAULT 'kling_v21'")
        print("  - aspect_ratio VARCHAR(10) DEFAULT '16:9'")
        print("  - template VARCHAR(20) DEFAULT 'standard'")
        
        # Verify columns were added
        print("\nVerifying columns...")
        columns = await conn.fetch("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'jobs'
            AND column_name IN ('video_model', 'aspect_ratio', 'template')
            ORDER BY column_name
        """)
        
        if columns:
            print("\n✅ Columns verified:")
            for col in columns:
                print(f"  - {col['column_name']}: {col['data_type']} (default: {col['column_default']})")
        else:
            print("\n⚠️  Warning: Could not verify columns (they may already exist)")
        
        await conn.close()
        
    except asyncpg.exceptions.DuplicateObjectError as e:
        print(f"\n⚠️  Warning: {str(e)}")
        print("This usually means the columns or constraints already exist.")
        print("Migration is idempotent (uses IF NOT EXISTS), so this is safe to ignore.")
    except Exception as e:
        print(f"\n❌ Error running migration: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migration())

