-- ROBUST FIX for jobs status constraint
-- Run this in Supabase SQL Editor

BEGIN;

-- 1. Drop the existing constraint
-- We use IF EXISTS to avoid errors if it was already dropped
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

-- 2. Add the constraint back with the 'regenerating' status included
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check 
    CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'regenerating'));

COMMIT;

-- Verification (optional - run separately if needed)
-- SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'jobs'::regclass AND conname = 'jobs_status_check';

