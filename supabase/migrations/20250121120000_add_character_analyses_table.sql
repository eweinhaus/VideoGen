-- Character analyses table for vision-based character feature extraction
-- Note: RLS policies assume Supabase Auth with user_id available via auth.uid()

create table if not exists public.character_analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  image_url text not null,
  image_hash text,
  normalized_analysis jsonb not null,
  raw_provider_output jsonb,
  confidence_per_attribute jsonb,
  analysis_version text not null default 'v1',
  provider text not null default 'openai_gpt4v',
  used_cache boolean not null default false,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  user_edits jsonb not null default '[]'::jsonb
);

create index if not exists idx_character_analyses_user_imagehash
  on public.character_analyses (user_id, image_hash);

create index if not exists idx_character_analyses_created_at
  on public.character_analyses (created_at);

-- Enable Row Level Security
alter table public.character_analyses enable row level security;

-- RLS policies: users can only access their rows
do $$
begin
  if not exists (
    select 1
    from pg_policies
    where polname = 'character_analyses_select_policy'
      and tablename = 'character_analyses'
  ) then
    create policy character_analyses_select_policy
      on public.character_analyses
      for select
      using (auth.uid() = user_id);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where polname = 'character_analyses_insert_policy'
      and tablename = 'character_analyses'
  ) then
    create policy character_analyses_insert_policy
      on public.character_analyses
      for insert
      with check (auth.uid() = user_id);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where polname = 'character_analyses_update_policy'
      and tablename = 'character_analyses'
  ) then
    create policy character_analyses_update_policy
      on public.character_analyses
      for update
      using (auth.uid() = user_id)
      with check (auth.uid() = user_id);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where polname = 'character_analyses_delete_policy'
      and tablename = 'character_analyses'
  ) then
    create policy character_analyses_delete_policy
      on public.character_analyses
      for delete
      using (auth.uid() = user_id);
  end if;
end $$;

-- Optional: automatic cleanup via scheduled job (handled outside migration)
-- Rows can be hard-deleted after expires_at; setup a daily cron separately.


