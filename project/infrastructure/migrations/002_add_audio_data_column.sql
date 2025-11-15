-- Migration: Add audio_data column to jobs table
-- Date: 2025-11-14
-- Purpose: Store audio analysis data directly in jobs table for easier access

-- Add audio_data JSONB column to jobs table
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS audio_data JSONB;

-- Create GIN index for efficient JSONB queries on audio_data
CREATE INDEX IF NOT EXISTS idx_jobs_audio_data ON jobs USING GIN (audio_data);

