-- Migration: Add clip_regenerations table for clip chatbot feature
-- Part 3: Integration & Polish - Cost Tracking
-- 
-- This migration creates the clip_regenerations table to track regeneration history,
-- costs, and conversation history for each clip regeneration.

-- Create clip_regenerations table
CREATE TABLE IF NOT EXISTS clip_regenerations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  clip_index INTEGER NOT NULL,
  original_prompt TEXT NOT NULL,
  modified_prompt TEXT NOT NULL,
  user_instruction TEXT NOT NULL,
  conversation_history JSONB,  -- Store conversation history as JSONB
  cost DECIMAL(10, 4) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  -- Allow multiple regenerations per clip (track history)
  -- No unique constraint, but index for fast lookups
  CONSTRAINT valid_clip_index CHECK (clip_index >= 0)
);

-- Index for fast lookups by job_id and clip_index
CREATE INDEX IF NOT EXISTS idx_clip_regenerations_job ON clip_regenerations(job_id, clip_index);

-- Index for cost analysis queries
CREATE INDEX IF NOT EXISTS idx_clip_regenerations_job_created ON clip_regenerations(job_id, created_at DESC);

-- Enable Row Level Security
ALTER TABLE clip_regenerations ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only view their own job's regenerations
CREATE POLICY "Users can view their own job regenerations"
  ON clip_regenerations
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.id = clip_regenerations.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- Policy: Service role can insert/update regenerations (for backend)
-- Note: In production, you may want to use a service role or JWT with specific claims
CREATE POLICY "Service role can manage regenerations"
  ON clip_regenerations
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Add comment to table
COMMENT ON TABLE clip_regenerations IS 'Tracks clip regeneration history, costs, and conversation context for clip chatbot feature';

