-- Sprint 2: whether the whole trip departs from one city. Backend only, through the
-- secret key. A browser receives only true or false, plus a group total when true.
begin;

create function public.rihla_flight_group(p_trip_id uuid, p_user_id uuid)
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
