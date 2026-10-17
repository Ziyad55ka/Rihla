-- Small, privacy-preserving aggregates for the trip cards and preferences page.
-- Apply after readiness/shared dates; existing private table policies stay intact.
begin;

create or replace function public.rihla_get_planning_status(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_admin boolean;
    v_missing text[];
    v_saved boolean;
    v_all_ready boolean;
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
    select rihla_private.preference_missing_fields(p), p.user_id is not null
        into v_missing, v_saved
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

    -- Only one group readiness boolean is shared with ordinary members.
    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end),
        bool_and(cardinality(rihla_private.preference_missing_fields(p)) = 0)
        into v_count, v_date_count, v_start, v_end, v_all_ready
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
        'missing_fields', to_jsonb(v_missing), 'has_saved_preferences', v_saved),
        'all_members_ready', v_all_ready, 'member_readiness', v_members, 'shared_dates', v_dates);
end;
$$;
revoke all on function public.rihla_get_planning_status(uuid) from public, anon, authenticated;
grant execute on function public.rihla_get_planning_status(uuid) to authenticated;

-- Checks an unsaved candidate against all other members, excluding the caller's
-- stored range. It returns no dates, names or private inputs and writes nothing.
create function public.rihla_check_trip_dates(p_trip_id uuid, p_start date, p_end date)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_count bigint;
    v_date_count bigint;
    v_start date;
    v_end date;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    if p_start is null or p_end is null or p_start > p_end
        or p_start not between date '0001-01-01' and date '9999-12-31'
        or p_end not between date '0001-01-01' and date '9999-12-31' then
        raise exception using errcode = '23514', message = 'invalid_date_range';
    end if;

    select count(*), count(*) filter(where p.available_start is not null and p.available_end is not null),
        max(p.available_start) filter(where p.available_start is not null and p.available_end is not null),
        min(p.available_end) filter(where p.available_start is not null and p.available_end is not null)
        into v_count, v_date_count, v_start, v_end
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id
        where m.trip_id = p_trip_id and m.user_id <> v_user;

    if greatest(p_start, v_start) > least(p_end, v_end) then
        return jsonb_build_object('status', 'conflict');
    elsif v_count <> v_date_count then
        return jsonb_build_object('status', 'pending');
    end if;
    return jsonb_build_object('status', 'available');
end;
$$;
revoke all on function public.rihla_check_trip_dates(uuid, date, date) from public, anon, authenticated;
grant execute on function public.rihla_check_trip_dates(uuid, date, date) to authenticated;

commit;
