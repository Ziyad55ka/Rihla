begin;
-- Only the caller's selections plus an aggregate, never another member's choices.
create function public.rihla_get_activity_costs(p_trip_id uuid) returns jsonb
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
