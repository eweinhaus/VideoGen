-- Migration: Add regeneration_analytics table for clip chatbot analytics
-- Part 6: Comparison Tools & Analytics
-- 
-- This migration creates the regeneration_analytics table to track regeneration events,
-- success rates, costs, and usage patterns for analytics dashboard.

-- Create regeneration_analytics table
CREATE TABLE IF NOT EXISTS regeneration_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  clip_index INTEGER NOT NULL,
  instruction TEXT NOT NULL,
  template_id TEXT,
  cost DECIMAL(10, 4) NOT NULL,
  success BOOLEAN NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT valid_clip_index CHECK (clip_index >= 0)
);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_user ON regeneration_analytics(user_id);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_job ON regeneration_analytics(job_id);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_instruction ON regeneration_analytics(instruction);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_created ON regeneration_analytics(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_job_clip ON regeneration_analytics(job_id, clip_index);

-- Create archive table for old data (same schema)
CREATE TABLE IF NOT EXISTS regeneration_analytics_archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL,
  user_id UUID NOT NULL,
  clip_index INTEGER NOT NULL,
  instruction TEXT NOT NULL,
  template_id TEXT,
  cost DECIMAL(10, 4) NOT NULL,
  success BOOLEAN NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE,
  archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT valid_clip_index_archive CHECK (clip_index >= 0)
);

-- Index for archive table
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_archive_user ON regeneration_analytics_archive(user_id);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_archive_job ON regeneration_analytics_archive(job_id);
CREATE INDEX IF NOT EXISTS idx_regeneration_analytics_archive_created ON regeneration_analytics_archive(created_at DESC);

-- Enable Row Level Security
ALTER TABLE regeneration_analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE regeneration_analytics_archive ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only view their own job's analytics
CREATE POLICY "Users can view their own job analytics"
  ON regeneration_analytics
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.id = regeneration_analytics.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- Policy: Service role can insert/update analytics (for backend)
CREATE POLICY "Service role can manage analytics"
  ON regeneration_analytics
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Policy: Users can only view their own archived analytics
CREATE POLICY "Users can view their own archived analytics"
  ON regeneration_analytics_archive
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.id = regeneration_analytics_archive.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- Policy: Service role can manage archived analytics
CREATE POLICY "Service role can manage archived analytics"
  ON regeneration_analytics_archive
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Add comments to tables
COMMENT ON TABLE regeneration_analytics IS 'Tracks regeneration events for analytics dashboard - Part 6: Comparison Tools & Analytics';
COMMENT ON TABLE regeneration_analytics_archive IS 'Archived regeneration analytics data (older than retention period)';

