-- Sprint 2: stored proposals. Direct table access is denied to every browser role.
-- Reads filter flights inside the database, because these functions can be called
-- directly with a member's token and so cannot rely on the backend to filter.
begin;

create table public.proposals (
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
create table public.proposal_generations (
    trip_id uuid primary key references public.trips(id) on delete cascade,
    latest_version integer not null default 0,
    input_hash text not null default '',
    complete boolean not null default false,
    generated_at timestamptz,
    locked_until timestamptz
);

alter table public.proposals enable row level security;
alter table public.proposal_generations enable row level security;
revoke all on public.proposals, public.proposal_generations from public, anon, authenticated;

create function rihla_private.require_trip_admin(p_trip_id uuid) returns uuid
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
create function rihla_private.proposal_for_member(p_data jsonb, p_city text) returns jsonb
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

-- Administrator only. Takes the lock atomically, and returns started false if a
-- generation is already running. A crashed run frees the lock after ten minutes.
create function public.rihla_begin_proposal_generation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_version integer;
begin
    perform rihla_private.require_trip_admin(p_trip_id);
    insert into public.proposal_generations(trip_id, locked_until)
        values (p_trip_id, now() + interval '10 minutes')
        on conflict (trip_id) do update set locked_until = excluded.locked_until
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

create function public.rihla_end_proposal_generation(p_trip_id uuid) returns jsonb
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
create function public.rihla_has_saved_proposals(
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
create function public.rihla_save_proposals(
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
        generated_at = now(), locked_until = null
        where trip_id = p_trip_id;
    return jsonb_build_object('saved', true, 'version', p_version);
end;
$$;
revoke all on function public.rihla_save_proposals(uuid, uuid, integer, text, boolean, jsonb) from public, anon, authenticated;
grant execute on function public.rihla_save_proposals(uuid, uuid, integer, text, boolean, jsonb) to service_role;

-- Any member. Each caller receives only the flights from their own departure city.
create function public.rihla_get_proposals(p_trip_id uuid) returns jsonb
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
        -- Proposals exist, but none has flights from the caller's departure city,
        -- which happens when it changed after generation.
        'needs_regeneration', exists (
            select 1 from public.proposals item where item.trip_id = p_trip_id
        ) and not exists (
            select 1 from public.proposals item,
                jsonb_array_elements(item.data->'flights') as flight
            where item.trip_id = p_trip_id
                and lower(btrim(flight->>'origin')) = lower(btrim(coalesce(v_city, '')))
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

commit;
