-- Migration: Add stop_at_stage column to jobs table
-- This column allows users to specify which stage the pipeline should stop at (for testing)

ALTER TABLE jobs 
ADD COLUMN IF NOT EXISTS stop_at_stage VARCHAR(50);

-- Add comment explaining the column
COMMENT ON COLUMN jobs.stop_at_stage IS 'Optional stage to stop at for testing: audio_parser, scene_planner, reference_generator, prompt_generator, video_generator, composer';

