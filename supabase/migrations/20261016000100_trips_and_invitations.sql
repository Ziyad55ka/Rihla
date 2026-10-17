-- Sprint 1: atomic trips and invitations. No preference/readiness data yet.
begin;

create schema if not exists rihla_private;
revoke all on schema rihla_private from public, anon, authenticated;
grant usage on schema rihla_private to authenticated;

create table public.trips (
    id uuid primary key default gen_random_uuid(),
    title text not null check (char_length(title) between 2 and 100 and title = btrim(title)),
    description text not null default '' check (char_length(description) <= 500),
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now()
);
create table public.trip_members (
    trip_id uuid not null references public.trips(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    primary key (trip_id, user_id)
);
create index trip_members_user_id_idx on public.trip_members(user_id, trip_id);
create table public.trip_invitations (
    trip_id uuid primary key references public.trips(id) on delete cascade,
    token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz,
    check (expires_at = created_at + interval '7 days')
);

alter table public.trips enable row level security;
alter table public.trip_members enable row level security;
alter table public.trip_invitations enable row level security;
revoke all on public.trips, public.trip_members, public.trip_invitations
    from public, anon, authenticated;
grant select on public.trips, public.trip_members to authenticated;

-- Bypasses only membership's own RLS lookup to avoid recursive policies.
-- No caller-supplied identity, no arbitrary queries and no exposed private schema.
create function rihla_private.is_trip_member(p_trip_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select not coalesce((auth.jwt()->>'is_anonymous')::boolean, false)
        and exists(select 1 from public.trip_members
        where trip_id = p_trip_id and user_id = (select auth.uid()));
$$;
revoke all on function rihla_private.is_trip_member(uuid) from public, anon;
grant execute on function rihla_private.is_trip_member(uuid) to authenticated;

create policy trips_read_members on public.trips for select to authenticated
    using (rihla_private.is_trip_member(id));
create policy memberships_read_members on public.trip_members for select to authenticated
    using (rihla_private.is_trip_member(trip_id));
-- No direct write grants/policies: guarded RPCs enforce atomic business rules.
-- No invitation SELECT grants/policies, even for administrators.

create function rihla_private.require_user() returns uuid
language plpgsql stable security invoker set search_path = '' as $$
begin
    if auth.uid() is null or coalesce((auth.jwt()->>'is_anonymous')::boolean, false) then
        raise exception using errcode = '42501', message = 'account_required';
    end if;
    return auth.uid();
end;
$$;
revoke all on function rihla_private.require_user() from public, anon;
grant execute on function rihla_private.require_user() to authenticated;

create function public.rihla_get_trip(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_result jsonb;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;
    select jsonb_build_object(
        'id', t.id, 'title', t.title, 'description', t.description,
        'created_at', t.created_at,
        'role', case when t.created_by = v_user then 'administrator' else 'member' end,
        'member_count', (select count(*) from public.trip_members where trip_id = t.id),
        'members', (select jsonb_agg(jsonb_build_object(
            'user_id', m.user_id,
            'display_name', coalesce(p.display_name, 'Trip member'),
            'role', case when m.user_id = t.created_by then 'administrator' else 'member' end,
            'joined_at', m.joined_at) order by m.joined_at, m.user_id)
            from public.trip_members m left join public.profiles p on p.id = m.user_id
            where m.trip_id = t.id)
    ) into v_result from public.trips t where t.id = p_trip_id;
    return v_result;
end;
$$;

create function public.rihla_list_trips() returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
declare v_user uuid := rihla_private.require_user();
begin
    -- Invoker + SELECT policies apply for normal reads.
    return coalesce((select jsonb_agg(item order by item->>'created_at' desc, item->>'id')
        from (select jsonb_build_object(
            'id', t.id, 'title', t.title, 'description', t.description,
            'created_at', t.created_at,
            'role', case when t.created_by = v_user then 'administrator' else 'member' end,
            'member_count', (select count(*) from public.trip_members where trip_id = t.id)
        ) as item from public.trips t) items), '[]'::jsonb);
end;
$$;

create function public.rihla_create_trip(p_title text, p_description text default '')
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_trip uuid;
begin
    insert into public.trips(title, description, created_by)
        values (btrim(p_title), btrim(coalesce(p_description, '')), v_user)
        returning id into v_trip;
    insert into public.trip_members(trip_id, user_id) values (v_trip, v_user);
    return public.rihla_get_trip(v_trip);
end;
$$;

create function public.rihla_get_invitation(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_result jsonb;
begin
    if not exists(select 1 from public.trips where id = p_trip_id and created_by = v_user) then
        raise exception using errcode = '42501', message = 'administrator_required';
    end if;
    select jsonb_build_object('exists', true, 'expires_at', expires_at,
        'revoked', revoked_at is not null) into v_result
        from public.trip_invitations where trip_id = p_trip_id;
    return coalesce(v_result, jsonb_build_object('exists', false, 'expires_at', null, 'revoked', false));
end;
$$;

create function public.rihla_issue_invitation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_token text; v_expires timestamptz;
begin
    -- Every invite mutation/join locks trip first, then invitation: fixed lock order.
    perform 1 from public.trips where id = p_trip_id and created_by = v_user for update;
    if not found then
        raise exception using errcode = '42501', message = 'administrator_required';
    end if;
    -- Two CSPRNG UUIDs provide 244 random bits; no pgcrypto extension dependency.
    v_token := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
    v_expires := now() + interval '7 days';
    insert into public.trip_invitations(trip_id, token_hash, created_at, expires_at)
        values(p_trip_id, encode(sha256(convert_to(v_token, 'UTF8')), 'hex'), now(), v_expires)
        on conflict(trip_id) do update set token_hash = excluded.token_hash,
            created_at = excluded.created_at, expires_at = excluded.expires_at, revoked_at = null;
    return jsonb_build_object('token', v_token, 'expires_at', v_expires);
end;
$$;

create function public.rihla_revoke_invitation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user();
begin
    perform 1 from public.trips where id = p_trip_id and created_by = v_user for update;
    if not found then
        raise exception using errcode = '42501', message = 'administrator_required';
    end if;
    update public.trip_invitations set revoked_at = now()
        where trip_id = p_trip_id and revoked_at is null;
    return public.rihla_get_invitation(p_trip_id);
end;
$$;

create function public.rihla_join_trip(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_user uuid := rihla_private.require_user(); v_trip uuid; v_hash text; v_inserted integer;
begin
    if p_token is null or p_token !~ '^[0-9a-f]{64}$' then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    v_hash := encode(sha256(convert_to(p_token, 'UTF8')), 'hex');
    select trip_id into v_trip from public.trip_invitations where token_hash = v_hash;
    if v_trip is null then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    perform 1 from public.trips where id = v_trip for update;
    perform 1 from public.trip_invitations where trip_id = v_trip and token_hash = v_hash
        and revoked_at is null and expires_at > clock_timestamp() for update;
    if not found then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    insert into public.trip_members(trip_id, user_id) values(v_trip, v_user)
        on conflict(trip_id, user_id) do nothing;
    get diagnostics v_inserted = row_count;
    return jsonb_build_object('trip', public.rihla_get_trip(v_trip),
        'already_member', v_inserted = 0);
end;
$$;

-- Explicitly remove default PUBLIC/anon execution for every exposed RPC.
revoke all on function public.rihla_get_trip(uuid), public.rihla_list_trips(),
    public.rihla_create_trip(text, text), public.rihla_get_invitation(uuid),
    public.rihla_issue_invitation(uuid), public.rihla_revoke_invitation(uuid),
    public.rihla_join_trip(text) from public, anon, authenticated;
grant execute on function public.rihla_get_trip(uuid), public.rihla_list_trips(),
    public.rihla_create_trip(text, text), public.rihla_get_invitation(uuid),
    public.rihla_issue_invitation(uuid), public.rihla_revoke_invitation(uuid),
    public.rihla_join_trip(text) to authenticated;

commit;
