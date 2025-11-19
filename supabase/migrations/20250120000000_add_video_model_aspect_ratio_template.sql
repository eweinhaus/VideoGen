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
ALTER TABLE jobs 
ADD CONSTRAINT IF NOT EXISTS check_video_model 
CHECK (video_model IN ('kling_v21', 'kling_v25_turbo', 'hailuo_23', 'wan_25_i2v', 'veo_31'));

ALTER TABLE jobs 
ADD CONSTRAINT IF NOT EXISTS check_aspect_ratio 
CHECK (aspect_ratio IN ('16:9', '9:16', '1:1', '4:3', '3:4'));

ALTER TABLE jobs 
ADD CONSTRAINT IF NOT EXISTS check_template 
CHECK (template IN ('standard', 'lipsync'));

