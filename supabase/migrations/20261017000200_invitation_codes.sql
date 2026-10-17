-- Add short invitation codes without exposing either invitation secret at rest.
-- Apply after 20261017000100_planning_overview.sql.
begin;

alter table public.trip_invitations
    add column code_hash text
    check (code_hash is null or code_hash ~ '^[0-9a-f]{64}$');
create unique index trip_invitations_code_hash_key
    on public.trip_invitations(code_hash) where code_hash is not null;

create or replace function public.rihla_issue_invitation(p_trip_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_token text;
    v_code text;
    v_code_hash text;
    v_old_code_hash text;
    v_expires timestamptz;
    v_digest bytea;
    v_number bigint;
    v_attempt integer;
begin
    -- Every invite mutation/join locks trip first, then invitation: fixed lock order.
    perform 1 from public.trips where id = p_trip_id and created_by = v_user for update;
    if not found then
        raise exception using errcode = '42501', message = 'administrator_required';
    end if;
    select code_hash into v_old_code_hash
        from public.trip_invitations where trip_id = p_trip_id for update;

    -- The long link token remains high entropy. The short code is protected by
    -- uniqueness here and per-user attempt limiting in FastAPI.
    for v_attempt in 1..20 loop
        v_token := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
        v_digest := sha256(convert_to(gen_random_uuid()::text, 'UTF8'));
        v_number := get_byte(v_digest, 0)::bigint * 16777216
            + get_byte(v_digest, 1)::bigint * 65536
            + get_byte(v_digest, 2)::bigint * 256
            + get_byte(v_digest, 3)::bigint;
        v_code := lpad((v_number % 1000000)::text, 6, '0');
        v_code_hash := encode(sha256(convert_to(v_code, 'UTF8')), 'hex');
        if v_code_hash = v_old_code_hash then
            continue;
        end if;
        v_expires := now() + interval '7 days';
        begin
            insert into public.trip_invitations(
                trip_id, token_hash, code_hash, created_at, expires_at
            ) values (
                p_trip_id,
                encode(sha256(convert_to(v_token, 'UTF8')), 'hex'),
                v_code_hash,
                now(),
                v_expires
            )
            on conflict(trip_id) do update set
                token_hash = excluded.token_hash,
                code_hash = excluded.code_hash,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                revoked_at = null;
            return jsonb_build_object(
                'token', v_token,
                'code', v_code,
                'expires_at', v_expires
            );
        exception when unique_violation then
            -- Retry the extremely unlikely token/code collision.
        end;
    end loop;
    raise exception using errcode = 'P0001', message = 'invitation_generation_failed';
end;
$$;

create or replace function public.rihla_join_trip(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_trip uuid;
    v_hash text;
    v_is_code boolean;
    v_inserted integer;
begin
    v_is_code := p_token is not null and p_token ~ '^[0-9]{6}$';
    if p_token is null or (not v_is_code and p_token !~ '^[0-9a-f]{64}$') then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    v_hash := encode(sha256(convert_to(p_token, 'UTF8')), 'hex');
    if v_is_code then
        select trip_id into v_trip from public.trip_invitations where code_hash = v_hash;
    else
        select trip_id into v_trip from public.trip_invitations where token_hash = v_hash;
    end if;
    if v_trip is null then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    perform 1 from public.trips where id = v_trip for update;
    perform 1 from public.trip_invitations
        where trip_id = v_trip
        and ((v_is_code and code_hash = v_hash) or (not v_is_code and token_hash = v_hash))
        and revoked_at is null and expires_at > clock_timestamp()
        for update;
    if not found then
        raise exception using errcode = 'P0001', message = 'invalid_invitation';
    end if;
    insert into public.trip_members(trip_id, user_id) values(v_trip, v_user)
        on conflict(trip_id, user_id) do nothing;
    get diagnostics v_inserted = row_count;
    return jsonb_build_object(
        'trip', public.rihla_get_trip(v_trip),
        'already_member', v_inserted = 0
    );
end;
$$;

revoke all on function public.rihla_issue_invitation(uuid),
    public.rihla_join_trip(text) from public, anon, authenticated;
grant execute on function public.rihla_issue_invitation(uuid),
    public.rihla_join_trip(text) to authenticated;

commit;
