-- Add audio_data column to jobs table
-- This column stores the full audio analysis results from the audio parser module

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS audio_data JSONB;

-- Create index for faster queries on audio_data
CREATE INDEX IF NOT EXISTS idx_jobs_audio_data ON jobs USING GIN (audio_data);

COMMENT ON COLUMN jobs.audio_data IS 'Full audio analysis results including BPM, beats, structure, mood, lyrics, and clip boundaries';

