-- Private per-trip inputs. Apply after accounts and trips/invitations.
begin;

create function rihla_private.valid_optional_preference(p jsonb) returns boolean
language sql immutable set search_path = '' as $$
    select case when jsonb_typeof(p) = 'object' then coalesce(
        p - array['value', 'importance'] = '{}'::jsonb
        and jsonb_typeof(p->'value') = 'string'
        and char_length(p->>'value') <= 500
        and p->>'importance' in ('Essential', 'Flexible'), false) else false end;
$$;
revoke all on function rihla_private.valid_optional_preference(jsonb) from public, anon;
grant execute on function rihla_private.valid_optional_preference(jsonb) to authenticated;

create table public.member_preferences (
    trip_id uuid not null,
    user_id uuid not null,
    departure_city text not null default '' check (char_length(departure_city) <= 100),
    -- Unconstrained numeric plus an explicit scale check rejects excess precision
    -- instead of silently rounding it. Null permits an incomplete saved draft.
    max_budget_sar numeric check (max_budget_sar > 0 and max_budget_sar < 10000000000
        and max_budget_sar = round(max_budget_sar, 2)),
    available_start date,
    available_end date,
    destinations jsonb not null default '{"value":"","importance":"Flexible"}'
        check (rihla_private.valid_optional_preference(destinations)),
    interests jsonb not null default '{"value":"","importance":"Flexible"}'
        check (rihla_private.valid_optional_preference(interests)),
    flights jsonb not null default '{"value":"","importance":"Flexible"}'
        check (rihla_private.valid_optional_preference(flights)),
    accommodation jsonb not null default '{"value":"","importance":"Flexible"}'
        check (rihla_private.valid_optional_preference(accommodation)),
    updated_at timestamptz not null default now(),
    primary key(trip_id, user_id),
    foreign key(trip_id, user_id) references public.trip_members(trip_id, user_id) on delete cascade,
    check (available_start is null or available_start between date '0001-01-01' and date '9999-12-31'),
    check (available_end is null or available_end between date '0001-01-01' and date '9999-12-31'),
    check (available_start is null or available_end is null or available_start <= available_end)
);
alter table public.member_preferences enable row level security;
revoke all on public.member_preferences from public, anon, authenticated;
grant select, insert, update on public.member_preferences to authenticated;

create policy preferences_read_own on public.member_preferences for select to authenticated
    using (user_id = (select auth.uid()) and rihla_private.is_trip_member(trip_id));
create policy preferences_insert_own on public.member_preferences for insert to authenticated
    with check (user_id = (select auth.uid()) and rihla_private.is_trip_member(trip_id));
create policy preferences_update_own on public.member_preferences for update to authenticated
    using (user_id = (select auth.uid()) and rihla_private.is_trip_member(trip_id))
    with check (user_id = (select auth.uid()) and rihla_private.is_trip_member(trip_id));

-- These normal reads/writes execute as the current user; RLS is still applied.
create function public.rihla_get_preferences(p_trip_id uuid) returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_result jsonb;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select to_jsonb(p) - array['trip_id', 'user_id'] into v_result
        from public.member_preferences p where trip_id = p_trip_id and user_id = v_user;
    return coalesce(v_result, jsonb_build_object(
        'departure_city', '', 'max_budget_sar', null, 'available_start', null,
        'available_end', null, 'updated_at', null,
        'destinations', '{"value":"","importance":"Flexible"}'::jsonb,
        'interests', '{"value":"","importance":"Flexible"}'::jsonb,
        'flights', '{"value":"","importance":"Flexible"}'::jsonb,
        'accommodation', '{"value":"","importance":"Flexible"}'::jsonb
    )) || jsonb_build_object('currency', 'SAR');
end;
$$;

create function public.rihla_save_preferences(p_trip_id uuid, p_preferences jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_user uuid := rihla_private.require_user();
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    if p_preferences is null or jsonb_typeof(p_preferences) <> 'object' then
        raise exception using errcode = '23514', message = 'invalid_preferences';
    end if;
    if p_preferences - array['departure_city','max_budget_sar','available_start',
            'available_end','destinations','interests','flights','accommodation'] <> '{}'::jsonb then
        raise exception using errcode = '23514', message = 'invalid_preferences';
    end if;
    insert into public.member_preferences(trip_id, user_id, departure_city, max_budget_sar,
        available_start, available_end, destinations, interests, flights, accommodation)
    values(p_trip_id, v_user, btrim(coalesce(p_preferences->>'departure_city', '')),
        (p_preferences->>'max_budget_sar')::numeric,
        (p_preferences->>'available_start')::date, (p_preferences->>'available_end')::date,
        coalesce(p_preferences->'destinations', '{"value":"","importance":"Flexible"}'::jsonb),
        coalesce(p_preferences->'interests', '{"value":"","importance":"Flexible"}'::jsonb),
        coalesce(p_preferences->'flights', '{"value":"","importance":"Flexible"}'::jsonb),
        coalesce(p_preferences->'accommodation', '{"value":"","importance":"Flexible"}'::jsonb))
    on conflict(trip_id, user_id) do update set
        departure_city = excluded.departure_city, max_budget_sar = excluded.max_budget_sar,
        available_start = excluded.available_start, available_end = excluded.available_end,
        destinations = excluded.destinations, interests = excluded.interests,
        flights = excluded.flights, accommodation = excluded.accommodation, updated_at = now();
    return public.rihla_get_preferences(p_trip_id);
end;
$$;

revoke all on function public.rihla_get_preferences(uuid),
    public.rihla_save_preferences(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.rihla_get_preferences(uuid),
    public.rihla_save_preferences(uuid, jsonb) to authenticated;
commit;
