#!/usr/bin/env python3
"""
Run migration independently using Supabase Python client.
Attempts multiple methods to execute the SQL.
"""

import sys
import os
from pathlib import Path

# Read migration SQL file
project_root = Path(__file__).parent.parent
migration_file = project_root / "supabase" / "migrations" / "20250120000000_add_video_model_aspect_ratio_template.sql"

if not migration_file.exists():
    print(f"❌ Migration file not found: {migration_file}")
    sys.exit(1)

with open(migration_file, "r") as f:
    migration_sql = f.read()

def run_migration():
    """Run the migration using available methods."""
    supabase_url = os.getenv("SUPABASE_URL", "https://hpjpsachyrnzobswmhnh.supabase.co")
    
    # Try Method 1: Use Supabase Python client with service key
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if service_key:
        try:
            from supabase import create_client
            
            print(f"Connecting to Supabase at {supabase_url}...")
            client = create_client(supabase_url, service_key)
            
            # Supabase doesn't support raw SQL via REST API directly
            # But we can try using RPC to execute SQL if there's a function
            # For now, we'll need to use direct PostgreSQL connection
            
            print("⚠️  Supabase REST API doesn't support raw SQL execution.")
            print("Need direct PostgreSQL connection with password.")
            
        except Exception as e:
            print(f"❌ Error with Supabase client: {str(e)}")
    
    # Try Method 2: Use psycopg2 with password from various sources
    db_password = (
        os.getenv("SUPABASE_DB_PASSWORD") or 
        os.getenv("DATABASE_PASSWORD") or
        os.getenv("POSTGRES_PASSWORD")
    )
    
    if db_password:
        try:
            import psycopg2
            from urllib.parse import urlparse
            
            parsed = urlparse(supabase_url)
            project_ref = parsed.netloc.split('.')[0]
            db_url = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
            
            print(f"Connecting to database at db.{project_ref}.supabase.co...")
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            cursor = conn.cursor()
            
            print("Running migration...")
            print("=" * 60)
            cursor.execute(migration_sql)
            
            print("\n✅ Migration completed successfully!")
            
            # Verify
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
            
            cursor.close()
            conn.close()
            return 0
            
        except ImportError:
            print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        except Exception as e:
            if "password authentication failed" in str(e).lower():
                print("❌ Database password authentication failed")
            else:
                print(f"❌ Error: {str(e)}")
    
    # If we get here, we couldn't execute automatically
    print("\n" + "=" * 80)
    print("MIGRATION SQL (Run this in Supabase SQL Editor)")
    print("=" * 80)
    print()
    print(migration_sql)
    print()
    print("=" * 80)
    print("\n📋 Instructions:")
    print("1. Go to: https://supabase.com/dashboard/project/hpjpsachyrnzobswmhnh")
    print("2. Navigate to: SQL Editor (left sidebar)")
    print("3. Click 'New query'")
    print("4. Copy and paste the SQL above")
    print("5. Click 'Run' or press Cmd/Ctrl + Enter")
    print("\n✅ The migration is idempotent (safe to run multiple times)")
    
    return 1


if __name__ == "__main__":
    sys.exit(run_migration())

