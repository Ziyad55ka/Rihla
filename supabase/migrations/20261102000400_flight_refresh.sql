-- Sprint 2: the light flight update. Backend only, through the secret key, because
-- these carry a private traveller count and the group's lowest budget.
begin;

-- The caller must be a member. Returns their own city and how many fly from it,
-- which the backend uses for searches and never sends to a browser.
create function public.rihla_flight_context(
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
create function public.rihla_save_flight_refresh(
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

commit;
