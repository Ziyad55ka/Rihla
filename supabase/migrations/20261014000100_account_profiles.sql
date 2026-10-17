-- Account slice only. Auth owns users/passwords; this table stores a private name.
begin;

create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name text not null
        check (char_length(display_name) between 2 and 80
            and display_name = btrim(display_name)),
    created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Explicit grants also work when automatic exposure of new tables is disabled.
revoke all on table public.profiles from public, anon, authenticated;
grant usage on schema public to authenticated;
grant select on table public.profiles to authenticated;
grant insert (id, display_name) on public.profiles to authenticated;
-- PostgREST upsert updates both supplied columns. RLS forbids changing the owner.
grant update (id, display_name) on public.profiles to authenticated;

create policy profiles_read_own on public.profiles
    for select to authenticated using ((select auth.uid()) = id);
create policy profiles_insert_own on public.profiles
    for insert to authenticated with check ((select auth.uid()) = id);
create policy profiles_update_own on public.profiles
    for update to authenticated using ((select auth.uid()) = id)
    with check ((select auth.uid()) = id);

-- No delete grant/policy, email copies, custom passwords, or global admin roles.
commit;
