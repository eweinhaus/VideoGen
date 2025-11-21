#!/usr/bin/env python3
"""
Run migration to add template column to jobs table.
Uses DatabaseClient to execute the migration SQL.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "project" / "backend"))

# Read migration SQL file
migration_file = project_root / "supabase" / "migrations" / "20250120000000_add_video_model_aspect_ratio_template.sql"

if not migration_file.exists():
    print(f"❌ Migration file not found: {migration_file}")
    sys.exit(1)

with open(migration_file, "r") as f:
    migration_sql = f.read()

async def run_migration():
    """Run the migration using DatabaseClient."""
    try:
        from shared.database import DatabaseClient
        
        print("Connecting to database...")
        db_client = DatabaseClient()
        
        print("Running migration...")
        print("=" * 60)
        print(migration_sql)
        print("=" * 60)
        
        # Execute migration SQL using raw SQL execution
        # Note: Supabase PostgREST doesn't support raw SQL, so we need to use psycopg2
        # For now, we'll use a workaround by executing via the underlying connection
        
        # Try to get the underlying connection from the Supabase client
        # The DatabaseClient uses supabase-py which uses postgrest
        # We need to execute raw SQL, so we'll use psycopg2 directly
        
        import psycopg2
        from urllib.parse import urlparse
        import os
        
        # Get database connection string from environment
        db_url = os.getenv("SUPABASE_DB_URL")
        
        if not db_url:
            print("\n❌ Error: SUPABASE_DB_URL environment variable not set")
            print("\nTo run this migration, you have two options:")
            print("\nOption 1: Set SUPABASE_DB_URL environment variable")
            print("  Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres")
            print("  You can find this in your Supabase project settings under Database > Connection string")
            print("\nOption 2: Run the SQL manually in Supabase SQL Editor")
            print("  1. Go to your Supabase project dashboard")
            print("  2. Navigate to: SQL Editor (in the left sidebar)")
            print("  3. Click 'New query'")
            print("  4. Copy and paste the SQL above")
            print("  5. Click 'Run' or press Cmd/Ctrl + Enter")
            sys.exit(1)
        
        print(f"\nConnecting to database...")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("Executing migration SQL...")
        cursor.execute(migration_sql)
        
        print("\n✅ Migration completed successfully!")
        print("\nAdded columns:")
        print("  - video_model VARCHAR(50) DEFAULT 'kling_v21'")
        print("  - aspect_ratio VARCHAR(10) DEFAULT '16:9'")
        print("  - template VARCHAR(20) DEFAULT 'standard'")
        
        # Verify columns were added
        print("\nVerifying columns...")
        cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'jobs'
            AND column_name IN ('video_model', 'aspect_ratio', 'template')
            ORDER BY column_name
        """)
        
        columns = cursor.fetchall()
        if columns:
            print("\n✅ Columns verified:")
            for col in columns:
                print(f"  - {col[0]}: {col[1]} (default: {col[2]})")
        else:
            print("\n⚠️  Warning: Could not verify columns (they may already exist)")
        
        cursor.close()
        conn.close()
        
    except psycopg2.errors.DuplicateObject as e:
        print(f"\n⚠️  Warning: {str(e)}")
        print("This usually means the columns or constraints already exist.")
        print("Migration is idempotent (uses IF NOT EXISTS), so this is safe to ignore.")
    except Exception as e:
        print(f"\n❌ Error running migration: {str(e)}")
        print("\nYou can also run this migration manually:")
        print("1. Go to your Supabase project dashboard")
        print("2. Navigate to: SQL Editor")
        print("3. Copy and paste the SQL shown above")
        print("4. Click 'Run'")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migration())

