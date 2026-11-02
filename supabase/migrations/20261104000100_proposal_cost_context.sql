-- US-13: what the backend needs for a member's cost breakdown and the group total.
-- Apply after 20261102000100_ai_proposals.sql.
--
-- Granted to the backend's secret key alone, like rihla_flight_context. It returns
-- private data (the caller's own budget, how many members fly from each city, and
-- every city's flight prices). The backend turns it into totals and never sends it
-- to a browser. The caller id must come from a verified session.
begin;

create or replace function public.rihla_cost_context(p_trip_id uuid, p_user_id uuid)
returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
    if p_user_id is null or not exists (
        select 1 from public.trip_members where trip_id = p_trip_id and user_id = p_user_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    return jsonb_build_object(
        'member_count', (
            select count(*) from public.trip_members where trip_id = p_trip_id
        ),
        -- The caller's own budget only, never anyone else's.
        'own_budget_sar', (
            select max_budget_sar::text from public.member_preferences
            where trip_id = p_trip_id and user_id = p_user_id
        ),
        -- Same matching as rihla_get_proposals: trimmed and case-insensitive.
        'origins', coalesce((
            select jsonb_agg(jsonb_build_object('origin', city, 'members', members)
                order by city)
            from (
                select lower(btrim(p.departure_city)) as city, count(*) as members
                from public.trip_members m
                join public.member_preferences p
                    on p.trip_id = m.trip_id and p.user_id = m.user_id
                where m.trip_id = p_trip_id and btrim(p.departure_city) <> ''
                group by 1
            ) cities
        ), '[]'::jsonb),
        'proposals', coalesce((
            select jsonb_agg(jsonb_build_object(
                'id', item.data->>'id',
                'flights', coalesce(item.data->'flights', '[]'::jsonb))
                order by item.option_number)
            from public.proposals item where item.trip_id = p_trip_id
        ), '[]'::jsonb));
end;
$$;
revoke all on function public.rihla_cost_context(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rihla_cost_context(uuid, uuid) to service_role;

commit;
