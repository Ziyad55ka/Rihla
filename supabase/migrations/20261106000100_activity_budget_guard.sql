-- Local migration: also guard writes made directly through the authenticated RPC.
-- These are known costs plus planning allowances, never a booking guarantee.
begin;
create or replace function rihla_private.guard_activity_budget()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    v_trip uuid;
    v_data jsonb;
    v_ceiling numeric;
    v_days integer;
    v_flights numeric;
    v_stays numeric;
    v_transport numeric;
    v_activities numeric;
begin
    select trip_id, data into v_trip, v_data from public.proposals
        where id = new.proposal_id;
    if v_trip is null or not exists (
        select 1 from public.trip_members where trip_id = v_trip and user_id = new.user_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select min(p.max_budget_sar) into v_ceiling
        from public.member_preferences p join public.trip_members m
        on m.trip_id = p.trip_id and m.user_id = p.user_id where p.trip_id = v_trip;
    if v_ceiling is null then
        raise exception using errcode = '23514', message = 'activity_budget_unavailable';
    end if;
    if exists (
        select 1 from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id
        where m.trip_id = v_trip and p.max_budget_sar is null
    ) then
        raise exception using errcode = '23514', message = 'activity_budget_unavailable';
    end if;
    if exists (
        select 1 from public.proposal_generations g where g.trip_id = v_trip
        and g.input_fingerprint is not null
        and g.input_fingerprint <> rihla_private.trip_inputs_fingerprint(v_trip)
    ) then
        raise exception using errcode = 'P0001', message = 'proposal_changed';
    end if;
    v_days := greatest(coalesce((nullif(v_data->>'end_date', '')::date
        - nullif(v_data->>'start_date', '')::date) + 1, 0), 0);
    select coalesce(max((f#>>'{price_per_person,amount_sar}')::numeric), 0)
        into v_flights from jsonb_array_elements(coalesce(v_data->'flights', '[]')) f;
    select coalesce(sum(coalesce((c->>'nights')::integer, 0)
        * coalesce((c#>>'{hotel_price_per_night,amount_sar}')::numeric, 0)), 0)
        into v_stays from jsonb_array_elements(coalesce(v_data->'cities', '[]')) c;
    select coalesce(sum((t#>>'{price_per_person,amount_sar}')::numeric), 0)
        into v_transport from jsonb_array_elements(coalesce(v_data->'intercity_transport', '[]')) t;
    -- Keep the expiring public admission guides consistent with the API's
    -- reviewed catalogue, including legacy proposals without stored prices.
    -- Review these values with landmark_catalog.py when updating the guides.
    select coalesce(sum(case when guide is not null
            and a#>>'{price_per_person,status}' = 'Unconfirmed'
            and coalesce(a#>'{price_per_person,evidence}', '[]'::jsonb) = '[]'::jsonb
            then guide else coalesce((a#>>'{price_per_person,amount_sar}')::numeric, guide) end), 0)
        into v_activities from (
            select a, case when (now() at time zone 'UTC')::date <= date '2026-12-06' then
                case lower(btrim(c->>'city')) || '|' || translate(lower(btrim(
                    regexp_replace(regexp_replace(a#>>'{name,value}',
                    '\([^)]*\)', ' ', 'g'), '\s+', ' ', 'g'))), 'ı', 'i')
                    when 'madrid|prado museum' then 70
                    when 'madrid|متحف برادو' then 70
                    when 'madrid|royal palace of madrid' then 85
                    when 'madrid|القصر الملكي في مدريد' then 85
                    when 'istanbul|hagia sophia' then 105
                    when 'istanbul|آيا صوفيا' then 105
                    when 'istanbul|topkapi palace' then 210
                    when 'istanbul|قصر توبكابي' then 210
                    else null end
                else null end as guide
            from jsonb_array_elements(coalesce(v_data->'cities', '[]')) c,
            jsonb_array_elements(coalesce(c->'activities', '[]')) a
            where a->>'id' = any(array(select id::text from unnest(new.activity_ids) id))
        ) priced;
    -- Database floor matches the project's default SAR 150/day meal allowance.
    -- A higher backend configuration is additionally checked before this write.
    if v_flights + v_stays + v_transport + 150 * v_days
        + v_activities > v_ceiling then
        raise exception using errcode = '23514', message = 'activity_budget_exceeded';
    end if;
    return new;
end;
$$;
revoke all on function rihla_private.guard_activity_budget() from public, anon, authenticated;
drop trigger if exists activity_budget_guard on public.activity_selections;
create trigger activity_budget_guard before insert or update of activity_ids
    on public.activity_selections for each row execute function rihla_private.guard_activity_budget();
-- Distinguish intentional zero choices from members still using a reserve.
create or replace function public.rihla_get_activity_costs(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user();
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode='42501',message='trip_access_denied';
    end if;
    return jsonb_build_object('proposals',coalesce((
        select jsonb_agg(jsonb_build_object('id',p.data->>'id',
            'activity_ids',coalesce((select to_jsonb(s.activity_ids)
                from public.activity_selections s where s.proposal_id=p.id and s.user_id=v_user),'[]'::jsonb),
            'has_selection',exists(select 1 from public.activity_selections s where s.proposal_id=p.id and s.user_id=v_user),
            'saved_members',(select count(*) from public.activity_selections s join public.trip_members m on m.trip_id=p.trip_id and m.user_id=s.user_id where s.proposal_id=p.id),
            'group_cost',(select jsonb_build_object(
                'amount_sar',coalesce(sum((a.value->'price_per_person'->>'amount_sar')::numeric),0)::text,
                'status',case when bool_or(a.value->'price_per_person'->>'status'='Unconfirmed')
                    then 'Unconfirmed' else 'Estimated' end,
                'partial',coalesce(bool_or(a.value is null or a.value->'price_per_person'->>'amount_sar' is null),false))
                from public.activity_selections s
                join public.trip_members m on m.trip_id=p.trip_id and m.user_id=s.user_id
                cross join lateral unnest(s.activity_ids) selected
                left join lateral (
                    select activity as value from jsonb_array_elements(p.data->'cities') city,
                        jsonb_array_elements(coalesce(city->'activities','[]'::jsonb)) activity
                    where activity->>'id'=selected::text
                ) a on true where s.proposal_id=p.id)
        ) order by p.option_number) from public.proposals p where p.trip_id=p_trip_id
    ),'[]'::jsonb));
end;
$$;
revoke all on function public.rihla_get_activity_costs(uuid) from public,anon,authenticated;
grant execute on function public.rihla_get_activity_costs(uuid) to authenticated;
commit;
