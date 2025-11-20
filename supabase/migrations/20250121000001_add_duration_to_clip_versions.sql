-- Migration: Add duration column to clip_versions table
-- 
-- This migration adds a duration column to track video duration for each clip version.
-- This is needed for proper comparison display and duration mismatch detection.

-- Add duration column (nullable for existing records)
ALTER TABLE clip_versions 
ADD COLUMN IF NOT EXISTS duration DECIMAL(10, 2);

-- Add comment to column
COMMENT ON COLUMN clip_versions.duration IS 'Video duration in seconds. Nullable for backward compatibility with existing records.';

