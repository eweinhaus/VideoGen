#!/usr/bin/env python3
"""
Script to run the migration that adds video_model, aspect_ratio, and template columns to jobs table.
This script uses the existing database connection from the shared config.
"""

import asyncio
import sys
from pathlib import Path

# Add project backend to path
project_root = Path(__file__).parent
backend_path = project_root / "project" / "backend"
sys.path.insert(0, str(backend_path))

from shared.database import DatabaseClient
from shared.config import settings
from shared.logging import get_logger

logger = get_logger(__name__)

# Migration SQL
MIGRATION_SQL = """
-- Migration: Add video_model, aspect_ratio, and template columns to jobs table
-- These columns store the video generation model, aspect ratio, and template selected by the user

ALTER TABLE jobs 
ADD COLUMN IF NOT EXISTS video_model VARCHAR(50) DEFAULT 'kling_v21';

ALTER TABLE jobs 
ADD COLUMN IF NOT EXISTS aspect_ratio VARCHAR(10) DEFAULT '16:9';

ALTER TABLE jobs 
ADD COLUMN IF NOT EXISTS template VARCHAR(20) DEFAULT 'standard';

-- Add comments explaining the columns
COMMENT ON COLUMN jobs.video_model IS 'Video generation model: kling_v21, kling_v25_turbo, hailuo_23, wan_25_i2v, veo_31';
COMMENT ON COLUMN jobs.aspect_ratio IS 'Aspect ratio for video generation: 16:9, 9:16, 1:1, 4:3, 3:4';
COMMENT ON COLUMN jobs.template IS 'Template to use: standard, lipsync';

-- Add check constraints for valid values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_video_model' 
        AND conrelid = 'jobs'::regclass
    ) THEN
        ALTER TABLE jobs 
        ADD CONSTRAINT check_video_model 
        CHECK (video_model IN ('kling_v21', 'kling_v25_turbo', 'hailuo_23', 'wan_25_i2v', 'veo_31'));
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_aspect_ratio' 
        AND conrelid = 'jobs'::regclass
    ) THEN
        ALTER TABLE jobs 
        ADD CONSTRAINT check_aspect_ratio 
        CHECK (aspect_ratio IN ('16:9', '9:16', '1:1', '4:3', '3:4'));
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_template' 
        AND conrelid = 'jobs'::regclass
    ) THEN
        ALTER TABLE jobs 
        ADD CONSTRAINT check_template 
        CHECK (template IN ('standard', 'lipsync'));
    END IF;
END $$;
"""


async def run_migration():
    """Run the migration to add columns to jobs table."""
    try:
        logger.info("Starting migration: Add video_model, aspect_ratio, and template columns")
        logger.info(f"Connecting to database at: {settings.supabase_url}")
        
        # Create database client
        db_client = DatabaseClient()
        
        # Note: Supabase uses PostgREST which doesn't support raw SQL execution
        # We need to use the Supabase client's RPC function or execute raw SQL via psycopg2
        # For now, we'll use a workaround by executing via the underlying connection
        
        # Try to get the underlying connection
        # The DatabaseClient uses supabase-py which uses postgrest
        # We need to execute raw SQL, so we'll use psycopg2 directly
        
        import psycopg2
        from urllib.parse import urlparse
        
        # Parse Supabase URL to get connection details
        # Supabase URL format: https://project.supabase.co
        # We need to construct the PostgreSQL connection string
        # Format: postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
        
        # Extract project reference from Supabase URL
        parsed_url = urlparse(settings.supabase_url)
        project_ref = parsed_url.netloc.split('.')[0]
        
        # Get database password from environment
        import os
        db_password = os.getenv('SUPABASE_DB_PASSWORD') or os.getenv('DATABASE_PASSWORD')
        
        if not db_password:
            logger.error("SUPABASE_DB_PASSWORD or DATABASE_PASSWORD environment variable is required")
            logger.info("Please set the database password in your environment variables")
            logger.info("You can find it in your Supabase project settings under Database > Connection string")
            return 1
        
        # Construct PostgreSQL connection string
        # Supabase database host format: db.[project-ref].supabase.co
        db_host = f"db.{project_ref}.supabase.co"
        db_name = "postgres"
        db_user = "postgres"
        db_port = 5432
        
        conn_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        logger.info(f"Connecting to PostgreSQL database at {db_host}")
        
        # Connect and execute migration
        conn = psycopg2.connect(conn_string)
        conn.autocommit = True  # Enable autocommit for DDL statements
        
        cursor = conn.cursor()
        
        try:
            logger.info("Executing migration SQL...")
            cursor.execute(MIGRATION_SQL)
            logger.info("✅ Migration executed successfully!")
            
            # Verify the columns were added
            cursor.execute("""
                SELECT column_name, data_type, column_default 
                FROM information_schema.columns 
                WHERE table_name = 'jobs' 
                AND column_name IN ('video_model', 'aspect_ratio', 'template')
                ORDER BY column_name;
            """)
            
            columns = cursor.fetchall()
            if columns:
                logger.info("\n✅ Verified columns added:")
                for col_name, data_type, default in columns:
                    logger.info(f"   - {col_name}: {data_type} (default: {default})")
            else:
                logger.warning("⚠️  Could not verify columns were added")
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error executing migration: {e}", exc_info=e)
            return 1
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=e)
        logger.info("\nAlternative: You can run the migration manually in Supabase SQL Editor:")
        logger.info("1. Go to your Supabase project dashboard")
        logger.info("2. Navigate to SQL Editor")
        logger.info("3. Copy and paste the SQL from: supabase/migrations/20250120000000_add_video_model_aspect_ratio_template.sql")
        logger.info("4. Execute the SQL")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_migration())
    sys.exit(exit_code)

