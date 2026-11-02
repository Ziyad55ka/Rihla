-- Sprint 2: AI proposals. Merged from five files, and safe to run on a database that
-- already has them: nothing here deletes data, and every statement can run twice.
-- Conflicts return categories only. Generation inputs, saving proposals and the flight
-- update are for the backend's secret key alone, because a function granted to
-- authenticated could be called from a browser. Direct table access is denied to every
-- browser role, and reads filter flights inside the database, because these functions
-- can be called directly with a member's token.
begin;

-- Supabase always has this role. Only a bare test database needs it created.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin;
    end if;
end
$$;

-- The countries named, or null if any word is unknown. Doubtful text is not a
-- clear conflict, so generation's first planning request judges it instead.
-- Mirrors COUNTRY_WORDS in backend/app/services/generation_precheck.py.
create or replace function rihla_private.destination_countries(p_text text) returns text[]
language sql immutable set search_path = '' as $$
    with words as (
        select lower(match[1]) as word
        from regexp_matches(coalesce(p_text, ''), '\w+', 'g') as match
    ), meaningful as (
        select word from words
        where word not in ('or', 'and', 'the', 'to', 'in', 'أو', 'و', 'في', 'إلى')
    ), known(word, country) as (values
        ('turkey', 'turkey'), ('türkiye', 'turkey'), ('turkiye', 'turkey'), ('تركيا', 'turkey'),
        ('egypt', 'egypt'), ('مصر', 'egypt'),
        ('jordan', 'jordan'), ('الأردن', 'jordan'), ('الاردن', 'jordan'),
        ('georgia', 'georgia'), ('جورجيا', 'georgia'),
        ('azerbaijan', 'azerbaijan'), ('أذربيجان', 'azerbaijan'), ('اذربيجان', 'azerbaijan'),
        ('oman', 'oman'), ('عمان', 'oman'),
        ('qatar', 'qatar'), ('قطر', 'qatar'),
        ('bahrain', 'bahrain'), ('البحرين', 'bahrain'),
        ('kuwait', 'kuwait'), ('الكويت', 'kuwait'),
        ('uae', 'uae'), ('الإمارات', 'uae'), ('الامارات', 'uae'),
        ('lebanon', 'lebanon'), ('لبنان', 'lebanon'),
        ('morocco', 'morocco'), ('المغرب', 'morocco'),
        ('tunisia', 'tunisia'), ('تونس', 'tunisia'),
        ('malaysia', 'malaysia'), ('ماليزيا', 'malaysia'),
        ('thailand', 'thailand'), ('تايلاند', 'thailand'),
        ('indonesia', 'indonesia'), ('إندونيسيا', 'indonesia'), ('اندونيسيا', 'indonesia'),
        ('japan', 'japan'), ('اليابان', 'japan'),
        ('italy', 'italy'), ('إيطاليا', 'italy'), ('ايطاليا', 'italy'),
        ('france', 'france'), ('فرنسا', 'france'),
        ('spain', 'spain'), ('إسبانيا', 'spain'), ('اسبانيا', 'spain'),
        ('greece', 'greece'), ('اليونان', 'greece'),
        ('germany', 'germany'), ('ألمانيا', 'germany'), ('المانيا', 'germany')
    )
    select case
        when not exists (select 1 from meaningful) then null
        when exists (
            select 1 from meaningful m
            where not exists (select 1 from known k where k.word = m.word)
        ) then null
        else (
            select array_agg(distinct k.country)
            from meaningful m join known k on k.word = m.word
        )
    end
$$;
revoke all on function rihla_private.destination_countries(text) from public, anon, authenticated;

-- For every member of the trip. Returns categories only, never who or which value.
-- The budget floor is fixed here rather than passed in, because a caller-chosen
-- floor would let a member search for the group's lowest budget.
-- Keep 250 in step with MIN_BUDGET_SAR_PER_DAY in the backend settings.
create or replace function public.rihla_get_group_conflicts(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_conflicts text[] := '{}';
    v_own_review text[] := '{}';
    v_count bigint;
    v_date_count bigint;
    v_all_ready boolean;
    v_start date;
    v_end date;
    v_lowest numeric;
    v_essentials bigint;
    v_doubtful bigint;
    v_own_destination jsonb;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;

    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end),
        bool_and(cardinality(rihla_private.preference_missing_fields(p)) = 0),
        min(p.max_budget_sar)
        into v_count, v_date_count, v_start, v_end, v_all_ready, v_lowest
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id where m.trip_id = p_trip_id;

    if not v_all_ready then
        v_conflicts := v_conflicts || 'readiness'::text;
    end if;
    if v_date_count <> v_count or v_start > v_end then
        v_conflicts := v_conflicts || 'dates'::text;
    end if;

    -- These need complete inputs, the same point at which generation could start.
    if cardinality(v_conflicts) = 0 then
        with wanted as (
            select rihla_private.destination_countries(p.destinations->>'value') as countries
            from public.trip_members m join public.member_preferences p
                on p.trip_id = m.trip_id and p.user_id = m.user_id
            where m.trip_id = p_trip_id and p.destinations->>'importance' = 'Essential'
                and btrim(p.destinations->>'value') <> ''
        )
        select count(*), count(*) filter(where countries is null)
            into v_essentials, v_doubtful from wanted;

        if v_essentials > 1 and v_doubtful = 0 and not exists (
            with wanted as (
                select rihla_private.destination_countries(p.destinations->>'value') as countries
                from public.trip_members m join public.member_preferences p
                    on p.trip_id = m.trip_id and p.user_id = m.user_id
                where m.trip_id = p_trip_id and p.destinations->>'importance' = 'Essential'
                    and btrim(p.destinations->>'value') <> ''
            )
            select 1 from wanted w, unnest(w.countries) as country
            group by country having count(*) = v_essentials
        ) then
            v_conflicts := v_conflicts || 'destinations'::text;
        end if;

        if v_lowest < 250 * (v_end - v_start + 1) then
            v_conflicts := v_conflicts || 'budget'::text;
        end if;
    end if;

    -- Only the caller's own Essential decides this notice. Budget never gets one,
    -- because it would tell a member that their budget is the lowest.
    if 'destinations' = any(v_conflicts) then
        select p.destinations into v_own_destination from public.member_preferences p
            where p.trip_id = p_trip_id and p.user_id = v_user;
        if v_own_destination->>'importance' = 'Essential'
            and btrim(v_own_destination->>'value') <> '' then
            v_own_review := v_own_review || 'destinations'::text;
        end if;
    end if;

    return jsonb_build_object('conflicts', to_jsonb(v_conflicts),
        'own_review', to_jsonb(v_own_review),
        'can_generate', cardinality(v_conflicts) = 0);
end;
$$;
revoke all on function public.rihla_get_group_conflicts(uuid) from public, anon, authenticated;
grant execute on function public.rihla_get_group_conflicts(uuid) to authenticated;

-- Backend only. There is no signed-in user with the secret key, so the backend
-- passes the account it verified, and this checks that account is the administrator.
-- Labels are not in join order, and no account ids or names are returned.
create or replace function public.rihla_trip_generation_inputs(p_trip_id uuid, p_admin_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    v_count bigint;
    v_date_count bigint;
    v_all_ready boolean;
    v_start date;
    v_end date;
begin
    if p_admin_id is null or not exists (
        select 1 from public.trips where id = p_trip_id and created_by = p_admin_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;

    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end),
        bool_and(cardinality(rihla_private.preference_missing_fields(p)) = 0)
        into v_count, v_date_count, v_start, v_end, v_all_ready
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id where m.trip_id = p_trip_id;
    if not v_all_ready or v_date_count <> v_count or v_start > v_end then
        raise exception using errcode = 'P0001', message = 'generation_not_ready';
    end if;

    return jsonb_build_object('trip_id', p_trip_id, 'shared_start', v_start,
        'shared_end', v_end, 'members', (
            select jsonb_agg(jsonb_build_object(
                'label', 'Member ' || position,
                'departure_city', departure_city,
                'max_budget_sar', max_budget_sar::text,
                'destinations', destinations,
                'interests', interests,
                'flights', flights,
                'accommodation', accommodation) order by position)
            from (
                select p.*, row_number() over (
                    order by md5(p.trip_id::text || p.user_id::text)
                ) as position
                from public.member_preferences p
                join public.trip_members m on m.trip_id = p.trip_id and m.user_id = p.user_id
                where p.trip_id = p_trip_id
            ) ordered
        ));
end;
$$;
revoke all on function public.rihla_trip_generation_inputs(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rihla_trip_generation_inputs(uuid, uuid) to service_role;

create table if not exists public.proposals (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references public.trips(id) on delete cascade,
    version integer not null check (version >= 1),
    option_number integer not null check (option_number between 1 and 3),
    data jsonb not null check (jsonb_typeof(data) = 'object'),
    created_at timestamptz not null default now(),
    unique (trip_id, version, option_number)
);

-- One row per trip: the latest generation, and the lock against parallel runs.
-- input_hash is keyed in the backend and is never returned to a browser.
create table if not exists public.proposal_generations (
    trip_id uuid primary key references public.trips(id) on delete cascade,
    latest_version integer not null default 0,
    input_hash text not null default '',
    complete boolean not null default false,
    generated_at timestamptz,
    locked_until timestamptz,
    -- Compared inside the database and never returned. Null on proposals saved before
    -- this existed, so only the departure city check applies to them.
    pending_fingerprint text,
    input_fingerprint text
);

alter table public.proposal_generations
    add column if not exists pending_fingerprint text,
    add column if not exists input_fingerprint text;

alter table public.proposals enable row level security;
alter table public.proposal_generations enable row level security;
revoke all on public.proposals, public.proposal_generations from public, anon, authenticated;

create or replace function rihla_private.require_trip_admin(p_trip_id uuid) returns uuid
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
begin
    if not exists (select 1 from public.trips where id = p_trip_id and created_by = v_user) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    return v_user;
end;
$$;
revoke all on function rihla_private.require_trip_admin(uuid) from public, anon, authenticated;

-- Keeps only the flights from this departure city, and only the sources still cited,
-- since a source link can name another member's city.
create or replace function rihla_private.proposal_for_member(p_data jsonb, p_city text) returns jsonb
language plpgsql immutable set search_path = '' as $$
declare
    v_view jsonb;
begin
    v_view := jsonb_set(p_data, '{flights}', coalesce((
        select jsonb_agg(flight)
        from jsonb_array_elements(p_data->'flights') as flight
        where lower(btrim(flight->>'origin')) = lower(btrim(coalesce(p_city, '')))
    ), '[]'::jsonb));
    return jsonb_set(v_view, '{sources}', coalesce((
        select jsonb_agg(source)
        from jsonb_array_elements(p_data->'sources') as source
        where (source->>'id')::int in (
            select (cited #>> '{}')::int
            from jsonb_path_query(v_view - 'sources', '$.**.source_id') as cited
        )
    ), '[]'::jsonb));
end;
$$;
revoke all on function rihla_private.proposal_for_member(jsonb, text) from public, anon, authenticated;

-- Covers what the backend's input hash covers: every member, their generation inputs,
-- and the shared dates. A member with no preferences yet still changes the count.
create or replace function rihla_private.trip_inputs_fingerprint(p_trip_id uuid) returns text
language sql stable security definer set search_path = '' as $$
    select md5(jsonb_build_object(
        'shared_start', max(available_start),
        'shared_end', min(available_end),
        'members', jsonb_agg(inputs order by inputs))::text)
    from (
        select p.available_start, p.available_end, lower(jsonb_build_object(
            'departure_city', btrim(p.departure_city),
            'max_budget_sar', p.max_budget_sar,
            'destinations', p.destinations,
            'interests', p.interests,
            'flights', p.flights,
            'accommodation', p.accommodation)::text) as inputs
        from public.trip_members m
        left join public.member_preferences p
            on p.trip_id = m.trip_id and p.user_id = m.user_id
        where m.trip_id = p_trip_id
    ) members;
$$;
revoke all on function rihla_private.trip_inputs_fingerprint(uuid) from public, anon, authenticated;

-- Administrator only. Takes the lock atomically,
-- Fingerprinted before the inputs are read, so a change during generation is not missed. and returns started false if a
-- generation is already running. A crashed run frees the lock after ten minutes.
create or replace function public.rihla_begin_proposal_generation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_version integer;
    v_fingerprint text;
begin
    perform rihla_private.require_trip_admin(p_trip_id);
    v_fingerprint := rihla_private.trip_inputs_fingerprint(p_trip_id);
    insert into public.proposal_generations(trip_id, locked_until, pending_fingerprint)
        values (p_trip_id, now() + interval '10 minutes', v_fingerprint)
        on conflict (trip_id) do update set locked_until = excluded.locked_until,
            pending_fingerprint = excluded.pending_fingerprint
        where public.proposal_generations.locked_until is null
            or public.proposal_generations.locked_until < now()
        returning latest_version into v_version;
    if v_version is null then
        return jsonb_build_object('started', false, 'version', null);
    end if;
    return jsonb_build_object('started', true, 'version', v_version + 1);
end;
$$;
revoke all on function public.rihla_begin_proposal_generation(uuid) from public, anon, authenticated;
grant execute on function public.rihla_begin_proposal_generation(uuid) to authenticated;

create or replace function public.rihla_end_proposal_generation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
    perform rihla_private.require_trip_admin(p_trip_id);
    update public.proposal_generations set locked_until = null where trip_id = p_trip_id;
    return jsonb_build_object('ended', true);
end;
$$;
revoke all on function public.rihla_end_proposal_generation(uuid) from public, anon, authenticated;
grant execute on function public.rihla_end_proposal_generation(uuid) to authenticated;

-- Administrator only. Answers yes or no, and never returns the stored hash.
create or replace function public.rihla_has_saved_proposals(
    p_trip_id uuid, p_input_hash text, p_max_age_hours integer
) returns boolean
language plpgsql stable security definer set search_path = '' as $$
begin
    perform rihla_private.require_trip_admin(p_trip_id);
    return exists (
        select 1 from public.proposal_generations
        where trip_id = p_trip_id and complete and input_hash = p_input_hash
            and generated_at > now() - make_interval(hours => p_max_age_hours)
    );
end;
$$;
revoke all on function public.rihla_has_saved_proposals(uuid, text, integer) from public, anon, authenticated;
grant execute on function public.rihla_has_saved_proposals(uuid, text, integer) to authenticated;

-- Backend only, through the secret key, so nobody can store invented proposals or
-- booking links. There is no signed-in user here, so the backend passes the account
-- it verified. Requires the lock from this run. Older versions are replaced.
create or replace function public.rihla_save_proposals(
    p_trip_id uuid, p_admin_id uuid, p_version integer, p_input_hash text,
    p_complete boolean, p_proposals jsonb
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_item jsonb;
begin
    if p_admin_id is null or not exists (
        select 1 from public.trips where id = p_trip_id and created_by = p_admin_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    if jsonb_typeof(p_proposals) <> 'array' or jsonb_array_length(p_proposals) not between 1 and 3 then
        raise exception using errcode = '23514', message = 'invalid_proposals';
    end if;
    if not exists (
        select 1 from public.proposal_generations
        where trip_id = p_trip_id and locked_until > now() and latest_version = p_version - 1
    ) then
        raise exception using errcode = 'P0001', message = 'generation_not_locked';
    end if;

    delete from public.proposals where trip_id = p_trip_id;
    for v_item in select value from jsonb_array_elements(p_proposals) loop
        if (v_item->>'trip_id')::uuid is distinct from p_trip_id
            or jsonb_typeof(v_item->'flights') <> 'array'
            or jsonb_typeof(v_item->'sources') <> 'array'
            or v_item ?| array['max_budget_sar', 'budget', 'label', 'input_hash'] then
            raise exception using errcode = '23514', message = 'invalid_proposals';
        end if;
        insert into public.proposals(trip_id, version, option_number, data)
            values (p_trip_id, p_version, (v_item->>'option_number')::int, v_item);
    end loop;
    update public.proposal_generations set latest_version = p_version,
        input_hash = p_input_hash, complete = p_complete,
        input_fingerprint = pending_fingerprint,
        generated_at = now(), locked_until = null
        where trip_id = p_trip_id;
    return jsonb_build_object('saved', true, 'version', p_version);
end;
$$;
revoke all on function public.rihla_save_proposals(uuid, uuid, integer, text, boolean, jsonb) from public, anon, authenticated;
grant execute on function public.rihla_save_proposals(uuid, uuid, integer, text, boolean, jsonb) to service_role;

-- Any member. Each caller receives only the flights from their own departure city.
create or replace function public.rihla_get_proposals(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_city text;
    v_generation public.proposal_generations;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select p.departure_city into v_city from public.member_preferences p
        where p.trip_id = p_trip_id and p.user_id = v_user;
    select * into v_generation from public.proposal_generations where trip_id = p_trip_id;
    return jsonb_build_object(
        'version', nullif(coalesce(v_generation.latest_version, 0), 0),
        'complete', coalesce(v_generation.complete, false),
        'generated_at', v_generation.generated_at,
        'generating', coalesce(v_generation.locked_until > now(), false),
        -- Proposals exist, but the group's inputs changed since they were generated,
        -- or none has flights from the caller's departure city.
        'needs_regeneration', exists (
            select 1 from public.proposals item where item.trip_id = p_trip_id
        ) and (
            coalesce(v_generation.input_fingerprint
                <> rihla_private.trip_inputs_fingerprint(p_trip_id), false)
            or not exists (
                select 1 from public.proposals item,
                    jsonb_array_elements(item.data->'flights') as flight
                where item.trip_id = p_trip_id
                    and lower(btrim(flight->>'origin')) = lower(btrim(coalesce(v_city, '')))
            )
        ),
        'proposals', coalesce((
            select jsonb_agg(rihla_private.proposal_for_member(item.data, v_city)
                order by item.option_number)
            from public.proposals item where item.trip_id = p_trip_id
        ), '[]'::jsonb));
end;
$$;
revoke all on function public.rihla_get_proposals(uuid) from public, anon, authenticated;
grant execute on function public.rihla_get_proposals(uuid) to authenticated;

-- The caller must be a member. Returns their own city and how many fly from it,
-- which the backend uses for searches and never sends to a browser.
create or replace function public.rihla_flight_context(
    p_trip_id uuid, p_proposal_id uuid, p_user_id uuid
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_city text;
    v_data jsonb;
begin
    if p_user_id is null or not exists (
        select 1 from public.trip_members where trip_id = p_trip_id and user_id = p_user_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select data into v_data from public.proposals
        where id = p_proposal_id and trip_id = p_trip_id;
    if v_data is null then
        -- Saved rows keep the id the generator gave inside the data.
        select data into v_data from public.proposals
            where trip_id = p_trip_id and data->>'id' = p_proposal_id::text;
    end if;
    if v_data is null then
        raise exception using errcode = 'P0001', message = 'proposal_not_found';
    end if;
    select departure_city into v_city from public.member_preferences
        where trip_id = p_trip_id and user_id = p_user_id;
    return jsonb_build_object(
        'city', v_city,
        'adults', (
            select count(*) from public.member_preferences p
            join public.trip_members m on m.trip_id = p.trip_id and m.user_id = p.user_id
            where p.trip_id = p_trip_id
                and lower(btrim(p.departure_city)) = lower(btrim(coalesce(v_city, '')))
        ),
        'ceiling', (
            select min(p.max_budget_sar)::text from public.member_preferences p
            join public.trip_members m on m.trip_id = p.trip_id and m.user_id = p.user_id
            where p.trip_id = p_trip_id
        ),
        'proposal', v_data);
end;
$$;
revoke all on function public.rihla_flight_context(uuid, uuid, uuid) from public, anon, authenticated;
grant execute on function public.rihla_flight_context(uuid, uuid, uuid) to service_role;

-- Replaces only the caller's own city's flights, and budget_status when given.
create or replace function public.rihla_save_flight_refresh(
    p_trip_id uuid, p_proposal_id uuid, p_user_id uuid, p_flights jsonb, p_budget_status text
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_city text;
begin
    if p_user_id is null or not exists (
        select 1 from public.trip_members where trip_id = p_trip_id and user_id = p_user_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select departure_city into v_city from public.member_preferences
        where trip_id = p_trip_id and user_id = p_user_id;
    if jsonb_typeof(p_flights) <> 'object'
        or lower(btrim(p_flights->>'origin')) is distinct from lower(btrim(v_city))
        or (p_budget_status is not null and p_budget_status not in
            ('within_group_budget', 'includes_unconfirmed', 'over_group_budget')) then
        raise exception using errcode = '23514', message = 'invalid_flights';
    end if;
    update public.proposals item set data = jsonb_set(
        case when p_budget_status is null then item.data
            else jsonb_set(item.data, '{budget_status}', to_jsonb(p_budget_status)) end,
        '{flights}',
        (select coalesce(jsonb_agg(case
            when lower(btrim(flight->>'origin')) = lower(btrim(v_city)) then p_flights
            else flight end), '[]'::jsonb)
         from jsonb_array_elements(item.data->'flights') as flight))
    where item.trip_id = p_trip_id
        and (item.id = p_proposal_id or item.data->>'id' = p_proposal_id::text);
    if not found then
        raise exception using errcode = 'P0001', message = 'proposal_not_found';
    end if;
    return jsonb_build_object('saved', true);
end;
$$;
revoke all on function public.rihla_save_flight_refresh(uuid, uuid, uuid, jsonb, text) from public, anon, authenticated;
grant execute on function public.rihla_save_flight_refresh(uuid, uuid, uuid, jsonb, text) to service_role;

create or replace function public.rihla_flight_group(p_trip_id uuid, p_user_id uuid)
returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_members integer;
    v_cities integer;
    v_known integer;
begin
    if p_user_id is null or not exists (
        select 1 from public.trip_members where trip_id = p_trip_id and user_id = p_user_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select count(*),
        count(distinct lower(btrim(p.departure_city))),
        count(nullif(btrim(p.departure_city), ''))
    into v_members, v_cities, v_known
    from public.trip_members m
    left join public.member_preferences p on p.trip_id = m.trip_id and p.user_id = m.user_id
    where m.trip_id = p_trip_id;
    return jsonb_build_object(
        'all_same_city', v_cities = 1 and v_known = v_members,
        'members', v_members);
end;
$$;
revoke all on function public.rihla_flight_group(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rihla_flight_group(uuid, uuid) to service_role;

commit;
