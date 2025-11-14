-- Phase 0: Initial Database Schema Migration
-- Based on schema defined in planning/high-level/Tech.md (Database Schema section)
-- Run this migration in Supabase SQL Editor or via Supabase CLI
--
-- This migration includes:
-- - Base schema from Tech.md
-- - Additional production features: RLS policies, triggers, constraints

-- Note: Using gen_random_uuid() which is built into PostgreSQL 13+ (no extension needed)
-- If uuid-ossp extension is needed for other purposes, enable it separately

-- Jobs table (from Tech.md)
CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  status VARCHAR(20) NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
  audio_url TEXT NOT NULL,
  user_prompt TEXT NOT NULL CHECK (LENGTH(user_prompt) >= 50 AND LENGTH(user_prompt) <= 500),
  current_stage VARCHAR(50),
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  estimated_remaining INTEGER,
  total_cost DECIMAL(10,2) DEFAULT 0.00 CHECK (total_cost >= 0),
  video_url TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Job stages table (from Tech.md)
CREATE TABLE IF NOT EXISTS job_stages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  stage_name VARCHAR(50) NOT NULL,
  status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  duration_seconds INTEGER,
  cost DECIMAL(10,4) DEFAULT 0.0000 CHECK (cost >= 0),
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Job costs table (from Tech.md)
CREATE TABLE IF NOT EXISTS job_costs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  stage_name VARCHAR(50) NOT NULL,
  api_name VARCHAR(50) NOT NULL,  -- whisper, sdxl, svd, gpt-4o, claude
  cost DECIMAL(10,4) NOT NULL CHECK (cost >= 0),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audio analysis cache table (from Tech.md)
CREATE TABLE IF NOT EXISTS audio_analysis_cache (
  file_hash VARCHAR(32) PRIMARY KEY,  -- MD5 hash
  analysis_data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

-- Indexes for performance (from Tech.md)
CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_stages_job ON job_stages(job_id);
CREATE INDEX IF NOT EXISTS idx_job_costs_job ON job_costs(job_id);
CREATE INDEX IF NOT EXISTS idx_audio_cache_expires ON audio_analysis_cache(expires_at);

-- Additional production features (not in Tech.md but required for production):

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on jobs table
DROP TRIGGER IF EXISTS update_jobs_updated_at ON jobs;
CREATE TRIGGER update_jobs_updated_at
  BEFORE UPDATE ON jobs
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (RLS) Policies
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_costs ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for idempotency)
DROP POLICY IF EXISTS "Users can view own jobs" ON jobs;
DROP POLICY IF EXISTS "Users can insert own jobs" ON jobs;
DROP POLICY IF EXISTS "Users can update own jobs" ON jobs;
DROP POLICY IF EXISTS "Users can view own job stages" ON job_stages;
DROP POLICY IF EXISTS "Users can view own job costs" ON job_costs;

-- Policy: Users can only see their own jobs
CREATE POLICY "Users can view own jobs"
  ON jobs FOR SELECT
  USING (auth.uid() = user_id);

-- Policy: Users can insert their own jobs
CREATE POLICY "Users can insert own jobs"
  ON jobs FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update their own jobs
CREATE POLICY "Users can update own jobs"
  ON jobs FOR UPDATE
  USING (auth.uid() = user_id);

-- Similar policies for job_stages and job_costs
CREATE POLICY "Users can view own job stages"
  ON job_stages FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM jobs WHERE jobs.id = job_stages.job_id AND jobs.user_id = auth.uid()
  ));

CREATE POLICY "Users can view own job costs"
  ON job_costs FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM jobs WHERE jobs.id = job_costs.job_id AND jobs.user_id = auth.uid()
  ));

-- Note: Service role key bypasses RLS, so backend can access all data

