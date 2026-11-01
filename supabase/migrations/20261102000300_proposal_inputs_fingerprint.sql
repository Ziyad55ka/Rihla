-- Sprint 2: tell the group when members or preferences changed after generation.
-- The fingerprint is compared inside the database and is never returned. Reads answer
-- only yes or no, with no member, city or value. Proposals saved before this migration
-- have no fingerprint, so only the departure city check applies to them.
begin;

alter table public.proposal_generations
    add column pending_fingerprint text,
    add column input_fingerprint text;

-- Covers what the backend's input hash covers: every member, their generation inputs,
-- and the shared dates. A member with no preferences yet still changes the count.
create function rihla_private.trip_inputs_fingerprint(p_trip_id uuid) returns text
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

-- Fingerprinted before the inputs are read, so a change during generation is not missed.
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

commit;
