begin;

create table rihla_private.trip_email_jobs (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null,
    user_id uuid not null,
    event_key text not null,
    proposal_id uuid,
    state text not null default 'pending' check (state in ('pending','sent','failed')),
    available_at timestamptz not null default now(),
    attempts integer not null default 0,
    first_attempt timestamptz,
    lease uuid,
    attempted_email text,
    unique (trip_id, user_id, event_key),
    foreign key (trip_id, user_id) references public.trip_members on delete cascade
);
create index trip_email_due on rihla_private.trip_email_jobs(available_at, id)
    where state = 'pending';
alter table rihla_private.trip_email_jobs enable row level security;
revoke all on rihla_private.trip_email_jobs from public, anon, authenticated;

create function rihla_private.queue_trip_emails() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    event text;
    proposal uuid;
begin
    if tg_table_name = 'proposal_generations' then
        event := 'ready/' || new.latest_version;
    else
        proposal := (new.data->>'id')::uuid;
        event := 'revised/' || new.id || '/' || (new.data->>'revision');
    end if;
    insert into rihla_private.trip_email_jobs(trip_id, user_id, event_key, proposal_id)
        select m.trip_id, m.user_id, event, proposal from public.trip_members m
        where m.trip_id = new.trip_id
        on conflict (trip_id, user_id, event_key) do nothing;
    return null;
end $$;
revoke all on function rihla_private.queue_trip_emails() from public, anon, authenticated;

create trigger notify_proposals_ready after update of latest_version on public.proposal_generations
    for each row when (new.latest_version > old.latest_version)
    execute function rihla_private.queue_trip_emails();
create trigger notify_proposal_revised after update of data on public.proposals
    for each row when (coalesce((new.data->>'revision')::int, 1) > coalesce((old.data->>'revision')::int, 1))
    execute function rihla_private.queue_trip_emails();

create function public.rihla_claim_trip_email() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    job rihla_private.trip_email_jobs;
    recipient text;
begin
    select * into job from rihla_private.trip_email_jobs
        where state = 'pending' and available_at <= now()
        order by available_at, id limit 1 for update skip locked;
    if not found then return '{}'::jsonb; end if;
    select email into recipient from auth.users where id = job.user_id;
    -- A crashed sender may already have submitted this email. Retry only with
    -- the same address and within the provider's idempotency window.
    if nullif(btrim(recipient),'') is null or job.attempts >= 8
        or job.first_attempt < now() - interval '23 hours'
        or (job.attempts > 0 and job.attempted_email is distinct from recipient) then
        update rihla_private.trip_email_jobs set state='failed', lease=null, attempted_email=null
            where id=job.id;
        return '{}'::jsonb;
    end if;
    update rihla_private.trip_email_jobs set attempts=attempts+1, lease=gen_random_uuid(),
        first_attempt=coalesce(first_attempt,now()), attempted_email=recipient,
        available_at=now()+interval '90 seconds' where id=job.id returning * into job;
    return jsonb_build_object('id',job.id,'lease',job.lease,'email',recipient,
        'trip_id',job.trip_id,'proposal_id',job.proposal_id);
end $$;

create function public.rihla_finish_trip_email(p_id uuid, p_lease uuid, p_outcome text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
    if p_outcome is null or p_outcome not in ('sent','retry','failed') then
        raise exception 'invalid_email_outcome';
    end if;
    update rihla_private.trip_email_jobs
        set state=case when p_outcome='retry' and attempts<8 then 'pending'
                       when p_outcome='sent' then 'sent' else 'failed' end,
            available_at=now()+interval '1 minute' * power(2,attempts-1),
            attempted_email=case when p_outcome='retry' and attempts<8 then attempted_email end,
            lease=null
        where id=p_id and lease=p_lease and state='pending';
    return found;
end $$;
revoke all on function public.rihla_claim_trip_email(), public.rihla_finish_trip_email(uuid,uuid,text)
    from public, anon, authenticated;
grant execute on function public.rihla_claim_trip_email(), public.rihla_finish_trip_email(uuid,uuid,text)
    to service_role;
commit;
