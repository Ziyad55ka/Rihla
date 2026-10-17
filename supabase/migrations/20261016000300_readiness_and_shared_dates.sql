-- Readiness is derived from current saved inputs; no writable Ready flag.
begin;

create function rihla_private.preference_missing_fields(p public.member_preferences)
returns text[] language sql immutable set search_path = '' as $$
    select array_remove(array[
        case when coalesce(btrim(p.departure_city), '') = '' then 'departure_city' end,
        case when p.max_budget_sar is null or p.max_budget_sar <= 0 then 'max_budget_sar' end,
        case when p.available_start is null then 'available_start' end,
        case when p.available_end is null then 'available_end' end
    ], null);
$$;
revoke all on function rihla_private.preference_missing_fields(public.member_preferences)
    from public, anon, authenticated;

-- Narrow aggregation needs access to private rows. Check membership first, keep
-- the search path empty, and return no other member's inputs or missing fields.
create function public.rihla_get_planning_status(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_admin boolean;
    v_missing text[];
    v_members jsonb := null;
    v_dates jsonb;
    v_count bigint;
    v_date_count bigint;
    v_start date;
    v_end date;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select created_by = v_user into v_admin from public.trips where id = p_trip_id;
    select rihla_private.preference_missing_fields(p) into v_missing
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id
        where m.trip_id = p_trip_id and m.user_id = v_user;

    if v_admin then
        select jsonb_agg(jsonb_build_object('user_id', m.user_id,
            'status', case when cardinality(rihla_private.preference_missing_fields(p)) = 0
                then 'Ready' else 'Incomplete' end) order by m.joined_at, m.user_id)
        into v_members from public.trip_members m left join public.member_preferences p
            on p.trip_id = m.trip_id and p.user_id = m.user_id
            where m.trip_id = p_trip_id;
    end if;

    -- Include every member, including the administrator. Budget/city readiness
    -- does not determine date overlap: these are deliberately separate results.
    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end)
        into v_count, v_date_count, v_start, v_end
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id where m.trip_id = p_trip_id;
    if v_date_count <> v_count then
        v_dates := jsonb_build_object('status', 'pending', 'start', null, 'end', null, 'duration_days', null);
    elsif v_start > v_end then
        v_dates := jsonb_build_object('status', 'conflict', 'start', null, 'end', null, 'duration_days', null);
    else
        v_dates := jsonb_build_object('status', 'available', 'start', v_start, 'end', v_end,
            'duration_days', v_end - v_start + 1);
    end if;
    return jsonb_build_object('own_readiness', jsonb_build_object(
        'status', case when cardinality(v_missing) = 0 then 'Ready' else 'Incomplete' end,
        'missing_fields', to_jsonb(v_missing)), 'member_readiness', v_members, 'shared_dates', v_dates);
end;
$$;
revoke all on function public.rihla_get_planning_status(uuid) from public, anon, authenticated;
grant execute on function public.rihla_get_planning_status(uuid) to authenticated;
commit;
