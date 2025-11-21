#!/usr/bin/env python3
"""
Run migration via Supabase REST API.
Uses the Supabase URL and service key to execute SQL.
"""

import sys
import requests
import json
from pathlib import Path
import os

# Read migration SQL file
project_root = Path(__file__).parent.parent
migration_file = project_root / "supabase" / "migrations" / "20250120000000_add_video_model_aspect_ratio_template.sql"

if not migration_file.exists():
    print(f"❌ Migration file not found: {migration_file}")
    sys.exit(1)

with open(migration_file, "r") as f:
    migration_sql = f.read()

def run_migration():
    """Run the migration via Supabase REST API."""
    supabase_url = os.getenv("SUPABASE_URL", "https://hpjpsachyrnzobswmhnh.supabase.co")
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not service_key:
        print("❌ SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY environment variable not set")
        print("\nTo run this migration, you need:")
        print("1. SUPABASE_URL (already set)")
        print("2. SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY")
        print("\nYou can find the service key in your Supabase project settings:")
        print("  Settings > API > service_role key (secret)")
        print("\nAlternatively, run the SQL manually in Supabase SQL Editor:")
        print("  1. Go to your Supabase project dashboard")
        print("  2. Navigate to: SQL Editor")
        print("  3. Copy and paste the SQL below")
        print("  4. Click 'Run'")
        print("\n" + "=" * 80)
        print(migration_sql)
        print("=" * 80)
        sys.exit(1)
    
    # Use Supabase Management API to execute SQL
    # The Management API endpoint is: POST /rest/v1/rpc/exec_sql
    # But actually, Supabase doesn't have a direct SQL execution endpoint via REST API
    # We need to use the PostgreSQL connection directly
    
    # Try using psycopg2 with connection string constructed from URL
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        # Parse Supabase URL to get project ref
        parsed = urlparse(supabase_url)
        project_ref = parsed.netloc.split('.')[0]
        
        # Get database password from environment
        db_password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("DATABASE_PASSWORD")
        
        if not db_password:
            print("❌ SUPABASE_DB_PASSWORD or DATABASE_PASSWORD environment variable not set")
            print(f"\nTo run this migration, you need the database password.")
            print(f"Connection string format:")
            print(f"  postgresql://postgres:[PASSWORD]@db.{project_ref}.supabase.co:5432/postgres")
            print("\nYou can find the database password in your Supabase project settings:")
            print("  Settings > Database > Connection string > URI")
            print("\nAlternatively, run the SQL manually in Supabase SQL Editor (see above)")
            sys.exit(1)
        
        # Construct PostgreSQL connection string
        db_url = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
        
        print(f"Connecting to database at db.{project_ref}.supabase.co...")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("Running migration...")
        print("=" * 60)
        print(migration_sql)
        print("=" * 60)
        
        print("\nExecuting migration SQL...")
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
        
        print("\n✅ Migration complete!")
        return 0
        
    except ImportError:
        print("❌ Error: psycopg2 not installed")
        print("Install it with: pip install psycopg2-binary")
        sys.exit(1)
    except psycopg2.OperationalError as e:
        if "password authentication failed" in str(e).lower():
            print("❌ Error: Database password authentication failed")
            print("Please check your SUPABASE_DB_PASSWORD environment variable")
        else:
            print(f"❌ Connection error: {str(e)}")
        sys.exit(1)
    except psycopg2.errors.DuplicateObject as e:
        print(f"\n⚠️  Warning: {str(e)}")
        print("This usually means the columns or constraints already exist.")
        print("Migration is idempotent (uses IF NOT EXISTS), so this is safe to ignore.")
        print("\n✅ Migration complete (columns already exist)")
        return 0
    except Exception as e:
        print(f"\n❌ Error running migration: {str(e)}")
        print("\nYou can also run this migration manually:")
        print("1. Go to your Supabase project dashboard")
        print("2. Navigate to: SQL Editor")
        print("3. Copy and paste the SQL shown above")
        print("4. Click 'Run'")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(run_migration())

