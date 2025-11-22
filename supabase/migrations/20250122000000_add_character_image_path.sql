ALTER TABLE IF EXISTS public.jobs
ADD COLUMN IF NOT EXISTS character_image_path text;

COMMENT ON COLUMN public.jobs.character_image_path IS
'Supabase Storage path to user-uploaded character image (nullable).';

