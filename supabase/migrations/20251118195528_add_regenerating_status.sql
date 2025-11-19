-- Migration: Add 'regenerating' status to jobs table

BEGIN;

-- 1. Drop the existing constraint
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

-- 2. Add the constraint back with 'regenerating' included
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'regenerating'));

COMMIT;

