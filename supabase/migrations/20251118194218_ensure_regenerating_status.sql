-- Ensure 'regenerating' status is included in jobs status constraint
-- This migration is idempotent and safe to run multiple times
-- Fixes: Database operation failed - 'regenerating' status violates check constraint

BEGIN;

-- Drop the existing constraint if it exists
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

-- Add the constraint back with all required statuses including 'regenerating'
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check 
    CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'regenerating'));

COMMIT;

-- Verification query (optional - run separately if needed):
-- SELECT conname, pg_get_constraintdef(oid) 
-- FROM pg_constraint 
-- WHERE conrelid = 'jobs'::regclass 
--   AND conname = 'jobs_status_check';

