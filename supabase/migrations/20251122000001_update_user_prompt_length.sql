-- Update user_prompt constraint to allow up to 3000 characters
-- This aligns with the validation in upload.py

-- Drop the old constraint
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_user_prompt_check;

-- Add the new constraint
ALTER TABLE jobs ADD CONSTRAINT jobs_user_prompt_check 
  CHECK (LENGTH(user_prompt) >= 50 AND LENGTH(user_prompt) <= 3000);

