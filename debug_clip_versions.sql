-- Check what versions exist for clip 4 of job 060ba1e4-ad6f-4734-8fe1-e69514f57833

SELECT 
    version_number,
    is_current,
    video_url,
    prompt,
    user_instruction,
    duration,
    created_at
FROM clip_versions
WHERE job_id = '060ba1e4-ad6f-4734-8fe1-e69514f57833'
AND clip_index = 4
ORDER BY version_number ASC;

-- This should show:
-- v1: is_current=false, video_url=<original clip>, user_instruction=NULL
-- v2: is_current=true, video_url=<regenerated clip>, user_instruction="boat should be a lot bigger"

