-- Backend-only city research lease. No direct browser writes or invented sources.
begin;
create table public.activity_research_jobs (
    proposal_id uuid primary key references public.proposals(id) on delete cascade,
    token uuid not null,
    locked_until timestamptz not null
);
alter table public.activity_research_jobs enable row level security;
revoke all on public.activity_research_jobs from public, anon, authenticated;

create function public.rihla_begin_activity_research(
    p_trip_id uuid, p_proposal_id uuid, p_user_id uuid, p_version integer, p_token uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_item public.proposals; v_taken uuid;
begin
    if p_user_id is null or not exists(select 1 from public.trip_members
        where trip_id=p_trip_id and user_id=p_user_id) then
        raise exception using errcode='42501', message='trip_access_denied';
    end if;
    select * into v_item from public.proposals where trip_id=p_trip_id
        and data->>'id'=p_proposal_id::text for share;
    if not found or v_item.version is distinct from p_version then
        raise exception using errcode='P0001', message='proposal_not_found';
    end if;
    if v_item.data->>'activity_research_status'='ready' then
        return jsonb_build_object('ready',true,'started',false);
    end if;
    insert into public.activity_research_jobs values(v_item.id,p_token,now()+interval '10 minutes')
    on conflict(proposal_id) do update set token=excluded.token,locked_until=excluded.locked_until
        where public.activity_research_jobs.locked_until < now()
    returning proposal_id into v_taken;
    return jsonb_build_object('ready',false,'started',v_taken is not null,
        'proposal',case when v_taken is not null then v_item.data else null end);
end;
$$;

create function public.rihla_finish_activity_research(
    p_trip_id uuid, p_proposal_id uuid, p_user_id uuid, p_version integer, p_token uuid,
    p_cities jsonb, p_sources jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_item public.proposals; v_cities jsonb;
begin
    if p_user_id is null or not exists(select 1 from public.trip_members
        where trip_id=p_trip_id and user_id=p_user_id) then
        raise exception using errcode='42501', message='trip_access_denied';
    end if;
    select * into v_item from public.proposals where trip_id=p_trip_id
        and data->>'id'=p_proposal_id::text for update;
    if not found or v_item.version is distinct from p_version then
        raise exception using errcode='P0001', message='proposal_not_found';
    end if;
    if not exists(select 1 from public.activity_research_jobs
        where proposal_id=v_item.id and token=p_token and locked_until>now()) then
        raise exception using errcode='P0001',message='activity_research_expired';
    end if;
    if jsonb_typeof(p_cities)<>'array' or jsonb_typeof(p_sources)<>'array'
        or jsonb_array_length(p_cities)<>jsonb_array_length(v_item.data->'cities') then
        raise exception using errcode='23514',message='invalid_activity_research';
    end if;
    -- Patch activities only: preserve newer flight prices and every teammate field.
    select jsonb_agg(jsonb_set(city,'{activities}',coalesce(
        (select fresh->'activities' from jsonb_array_elements(p_cities) fresh
         where fresh->>'order'=city->>'order'),'[]'::jsonb)) order by position)
        into v_cities from jsonb_array_elements(v_item.data->'cities') with ordinality c(city,position);
    update public.proposals set data=jsonb_set(jsonb_set(jsonb_set(data,
        '{cities}',v_cities),'{sources}',p_sources),'{activity_research_status}','"ready"'::jsonb)
        where id=v_item.id;
    delete from public.activity_research_jobs where proposal_id=v_item.id and token=p_token;
    return jsonb_build_object('ready',true);
end;
$$;

create function public.rihla_fail_activity_research(p_token uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
    -- Brief backoff stops repeated paid requests when a provider fails.
    update public.activity_research_jobs set locked_until=now()+interval '30 seconds'
        where token=p_token;
    return jsonb_build_object('released',true);
end;
$$;
revoke all on function public.rihla_begin_activity_research(uuid,uuid,uuid,integer,uuid) from public,anon,authenticated;
revoke all on function public.rihla_finish_activity_research(uuid,uuid,uuid,integer,uuid,jsonb,jsonb) from public,anon,authenticated;
revoke all on function public.rihla_fail_activity_research(uuid) from public,anon,authenticated;
grant execute on function public.rihla_begin_activity_research(uuid,uuid,uuid,integer,uuid) to service_role;
grant execute on function public.rihla_finish_activity_research(uuid,uuid,uuid,integer,uuid,jsonb,jsonb) to service_role;
grant execute on function public.rihla_fail_activity_research(uuid) to service_role;
commit;
