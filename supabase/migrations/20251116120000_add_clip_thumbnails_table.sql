-- Migration: Add clip_thumbnails table for clip chatbot feature

-- Part 1: Foundation & Data Infrastructure

--

-- This migration creates the clip_thumbnails table to store thumbnail URLs

-- for video clips, enabling the clip selector UI component.

-- Create clip_thumbnails table

CREATE TABLE IF NOT EXISTS clip_thumbnails (

  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

  clip_index INTEGER NOT NULL,

  thumbnail_url TEXT NOT NULL,

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(job_id, clip_index)

);

-- Index for fast lookups by job_id

CREATE INDEX IF NOT EXISTS idx_clip_thumbnails_job_id ON clip_thumbnails(job_id);

-- Enable Row Level Security

ALTER TABLE clip_thumbnails ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for idempotency)

DROP POLICY IF EXISTS "Users can view own thumbnails" ON clip_thumbnails;

DROP POLICY IF EXISTS "Service role can manage thumbnails" ON clip_thumbnails;

-- Policy: Users can view thumbnails for their own jobs

CREATE POLICY "Users can view own thumbnails"

  ON clip_thumbnails FOR SELECT

  USING (EXISTS (

    SELECT 1 FROM jobs

    WHERE jobs.id = clip_thumbnails.job_id

    AND jobs.user_id = auth.uid()

  ));

-- Policy: Service role can insert/update/delete thumbnails

-- Note: Service role key bypasses RLS, so backend can manage all thumbnails

-- This policy is for explicit service role access if needed

CREATE POLICY "Service role can manage thumbnails"

  ON clip_thumbnails FOR ALL

  USING (auth.role() = 'service_role')

  WITH CHECK (auth.role() = 'service_role');

-- Note: Service role key bypasses RLS by default, so backend operations

-- will work without explicit policy checks. The policies above provide

-- explicit user access control.

