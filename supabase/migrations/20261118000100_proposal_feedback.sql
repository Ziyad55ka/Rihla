begin;

create table public.proposal_revision_history (
    proposal_row uuid not null references public.proposals(id) on delete cascade,
    revision integer not null,
    previous_data jsonb not null,
    previous_choices jsonb not null,
    feedback text not null,
    revised_at timestamptz not null default now(),
    primary key (proposal_row, revision)
);
alter table public.proposal_revision_history enable row level security;
revoke all on public.proposal_revision_history from public, anon, authenticated;

create function public.rihla_revision_context(p_trip_id uuid, p_proposal_id uuid, p_admin_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare item public.proposals; inputs text; choices jsonb;
begin
    if not exists(select 1 from public.trips where id=p_trip_id and created_by=p_admin_id) then
        raise exception using errcode='42501', message='trip_access_denied';
    end if;
    select * into item from public.proposals where trip_id=p_trip_id and data->>'id'=p_proposal_id::text;
    if not found then raise exception 'proposal_not_found'; end if;
    inputs := rihla_private.trip_inputs_fingerprint(p_trip_id);
    if not exists(select 1 from public.proposal_generations where trip_id=p_trip_id
        and input_fingerprint=inputs and coalesce(locked_until,now())<=now()) then
        raise exception 'revision_stale';
    end if;
    select coalesce(jsonb_agg(to_jsonb(s) order by s.user_id),'[]') into choices
        from public.activity_selections s where s.proposal_id=item.id;
    return jsonb_build_object('proposal',item.data,'token',md5(item.data::text || inputs || choices::text));
end $$;

create function public.rihla_save_revision(p_trip_id uuid, p_proposal_id uuid, p_admin_id uuid,
    p_token text, p_feedback text, p_data jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare item public.proposals; old_revision integer; context jsonb;
begin
    perform 1 from public.proposal_generations where trip_id=p_trip_id for update;
    select * into item from public.proposals where trip_id=p_trip_id and data->>'id'=p_proposal_id::text for update;
    context := public.rihla_revision_context(p_trip_id,p_proposal_id,p_admin_id);
    old_revision := coalesce((item.data->>'revision')::integer,1);
    if p_token is distinct from context->>'token'
        or (p_data->>'revision')::integer is distinct from old_revision+1
        or (p_data->>'version')::integer is distinct from item.version
        or (p_data->>'option_number')::integer is distinct from item.option_number
        or p_data->>'id' is distinct from p_proposal_id::text
        or p_data->>'trip_id' is distinct from p_trip_id::text then raise exception 'revision_stale'; end if;
    insert into public.proposal_revision_history(proposal_row,revision,previous_data,previous_choices,feedback)
        select item.id,old_revision,item.data,coalesce(jsonb_agg(to_jsonb(s)),'[]'),p_feedback
        from public.activity_selections s where s.proposal_id=item.id;
    delete from public.activity_research_jobs where proposal_id=item.id;
    delete from public.activity_selections where proposal_id=item.id;
    update public.proposals set data=p_data where id=item.id;
    return jsonb_build_object('revision',old_revision+1);
end $$;

create function public.rihla_revision_history(p_trip_id uuid,p_proposal_id uuid)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare city text;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode='42501',message='trip_access_denied';
    end if;
    select departure_city into city from public.member_preferences
        where trip_id=p_trip_id and user_id=rihla_private.require_user();
    return (select coalesce(jsonb_agg(rihla_private.proposal_for_member(h.previous_data,city)
        order by h.revision desc),'[]') from public.proposal_revision_history h
        join public.proposals p on p.id=h.proposal_row where p.trip_id=p_trip_id and p.data->>'id'=p_proposal_id::text);
end $$;
revoke all on function public.rihla_revision_context(uuid,uuid,uuid), public.rihla_save_revision(uuid,uuid,uuid,text,text,jsonb),public.rihla_revision_history(uuid,uuid) from public,anon,authenticated;
grant execute on function public.rihla_revision_context(uuid,uuid,uuid), public.rihla_save_revision(uuid,uuid,uuid,text,text,jsonb) to service_role;
grant execute on function public.rihla_revision_history(uuid,uuid) to authenticated;
commit;
