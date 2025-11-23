-- Migration: Add user_reference_images table
-- This migration creates the table for storing user-uploaded reference images
-- 
-- To apply this migration:
-- 1. If using Supabase CLI: Run `supabase db push` or `supabase migration up`
-- 2. If using Supabase Dashboard: Copy and paste this SQL into the SQL Editor
-- 3. If using direct PostgreSQL: Run `psql -f 20251122193630_add_user_reference_images.sql`
--
-- This table stores user-uploaded reference images that can be matched to
-- characters, scenes, or objects from the scene plan.

-- Create user_reference_images table
CREATE TABLE IF NOT EXISTS user_reference_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  image_type VARCHAR(20) NOT NULL CHECK (image_type IN ('character', 'scene', 'object')),
  user_title VARCHAR(100) NOT NULL,
  original_filename VARCHAR(255) NOT NULL,
  storage_path TEXT NOT NULL,
  final_storage_path TEXT,
  image_url TEXT NOT NULL,
  matched_character_id VARCHAR(100),
  matched_character_name VARCHAR(100),
  matched_scene_id VARCHAR(100),
  matched_object_id VARCHAR(100),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_ref_images_job ON user_reference_images(job_id);
CREATE INDEX IF NOT EXISTS idx_user_ref_images_type ON user_reference_images(job_id, image_type);

-- RLS Policies
ALTER TABLE user_reference_images ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own reference images" ON user_reference_images;
CREATE POLICY "Users can view own reference images" ON user_reference_images
  FOR SELECT USING (
    job_id IN (SELECT id FROM jobs WHERE user_id = auth.uid())
  );

DROP POLICY IF EXISTS "Users can insert own reference images" ON user_reference_images;
CREATE POLICY "Users can insert own reference images" ON user_reference_images
  FOR INSERT WITH CHECK (
    job_id IN (SELECT id FROM jobs WHERE user_id = auth.uid())
  );

