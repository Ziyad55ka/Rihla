-- Private per-member selections. Saved proposals remain immutable.
begin;
create table public.activity_selections (
    proposal_id uuid not null references public.proposals(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    activity_ids uuid[] not null default '{}',
    primary key (proposal_id, user_id)
);
alter table public.activity_selections enable row level security;
revoke all on public.activity_selections from public, anon, authenticated;

create function public.rihla_get_activity_selection(p_trip_id uuid, p_proposal_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_proposal public.proposals;
    v_ids uuid[];
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select * into v_proposal from public.proposals
        where data->>'id' = p_proposal_id::text and trip_id = p_trip_id;
    if not found then
        raise exception using errcode = 'P0001', message = 'proposal_changed';
    end if;
    select activity_ids into v_ids from public.activity_selections
        where proposal_id = v_proposal.id and user_id = v_user;
    return jsonb_build_object('proposal_id', p_proposal_id, 'version', v_proposal.version,
        'activity_ids', coalesce(v_ids, '{}'::uuid[]));
end;
$$;

create function public.rihla_set_activity_selection(
    p_trip_id uuid, p_proposal_id uuid, p_version integer, p_activity_ids uuid[]
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_proposal public.proposals;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    -- Keep regeneration from removing this proposal during the save.
    select * into v_proposal from public.proposals
        where data->>'id' = p_proposal_id::text and trip_id = p_trip_id for share;
    if not found or v_proposal.version is distinct from p_version then
        raise exception using errcode = 'P0001', message = 'proposal_changed';
    end if;
    if p_activity_ids is null or cardinality(p_activity_ids) > 300
        or cardinality(p_activity_ids) <> (select count(distinct id) from unnest(p_activity_ids) id)
        or exists (
            select 1 from unnest(p_activity_ids) selected
            where not exists (
                select 1 from jsonb_array_elements(v_proposal.data->'cities') city,
                    jsonb_array_elements(coalesce(city->'activities', '[]'::jsonb)) activity
                where activity->>'id' = selected::text
            )
        ) then
        raise exception using errcode = '23514', message = 'invalid_activity_selection';
    end if;
    insert into public.activity_selections(proposal_id, user_id, activity_ids)
        values (v_proposal.id, v_user, p_activity_ids)
        on conflict (proposal_id, user_id) do update set activity_ids = excluded.activity_ids;
    return public.rihla_get_activity_selection(p_trip_id, p_proposal_id);
end;
$$;
revoke all on function public.rihla_get_activity_selection(uuid, uuid) from public, anon, authenticated;
revoke all on function public.rihla_set_activity_selection(uuid, uuid, integer, uuid[]) from public, anon, authenticated;
grant execute on function public.rihla_get_activity_selection(uuid, uuid) to authenticated;
grant execute on function public.rihla_set_activity_selection(uuid, uuid, integer, uuid[]) to authenticated;
commit;
