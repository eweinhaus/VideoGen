-- Migration: Add clip_versions table for clip versioning
-- 
-- This migration creates the clip_versions table to track different versions of clips
-- for comparison purposes. Version 1 is always the original clip.

-- Create clip_versions table
CREATE TABLE IF NOT EXISTS clip_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  version_number INTEGER NOT NULL,
  video_url TEXT NOT NULL,
  thumbnail_url TEXT,
  prompt TEXT NOT NULL,
  user_instruction TEXT,
  cost DECIMAL(10, 4) NOT NULL DEFAULT 0.0000,
  is_current BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  -- Ensure one version 1 per clip (original)
  -- Allow multiple regenerated versions (version 2+)
  CONSTRAINT valid_version_number CHECK (version_number >= 1),
  CONSTRAINT valid_clip_index CHECK (clip_index >= 0),
  UNIQUE(job_id, clip_index, version_number)
);

-- Index for fast lookups by job_id and clip_index
CREATE INDEX IF NOT EXISTS idx_clip_versions_job ON clip_versions(job_id, clip_index);

-- Index for finding current version
CREATE INDEX IF NOT EXISTS idx_clip_versions_current ON clip_versions(job_id, clip_index, is_current) WHERE is_current = TRUE;

-- Index for version lookups
CREATE INDEX IF NOT EXISTS idx_clip_versions_version ON clip_versions(job_id, clip_index, version_number);

-- Enable Row Level Security
ALTER TABLE clip_versions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only view their own job's clip versions
CREATE POLICY "Users can view their own job clip versions"
  ON clip_versions
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.id = clip_versions.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- Policy: Service role can manage clip versions (for backend)
CREATE POLICY "Service role can manage clip versions"
  ON clip_versions
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Add comment to table
COMMENT ON TABLE clip_versions IS 'Tracks different versions of clips for comparison. Version 1 is always the original clip.';

