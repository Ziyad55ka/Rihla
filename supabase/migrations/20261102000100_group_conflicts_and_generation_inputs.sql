-- Sprint 2: conflicts for the trip page, and private inputs for proposal generation.
-- Conflicts return categories only. Generation inputs are for the backend's secret
-- key alone: a function granted to authenticated could be called from a browser.
begin;

-- The countries named, or null if any word is unknown. Doubtful text is not a
-- clear conflict, so generation's first planning request judges it instead.
-- Mirrors COUNTRY_WORDS in backend/app/services/generation_precheck.py.
create function rihla_private.destination_countries(p_text text) returns text[]
language sql immutable set search_path = '' as $$
    with words as (
        select lower(match[1]) as word
        from regexp_matches(coalesce(p_text, ''), '\w+', 'g') as match
    ), meaningful as (
        select word from words
        where word not in ('or', 'and', 'the', 'to', 'in', 'أو', 'و', 'في', 'إلى')
    ), known(word, country) as (values
        ('turkey', 'turkey'), ('türkiye', 'turkey'), ('turkiye', 'turkey'), ('تركيا', 'turkey'),
        ('egypt', 'egypt'), ('مصر', 'egypt'),
        ('jordan', 'jordan'), ('الأردن', 'jordan'), ('الاردن', 'jordan'),
        ('georgia', 'georgia'), ('جورجيا', 'georgia'),
        ('azerbaijan', 'azerbaijan'), ('أذربيجان', 'azerbaijan'), ('اذربيجان', 'azerbaijan'),
        ('oman', 'oman'), ('عمان', 'oman'),
        ('qatar', 'qatar'), ('قطر', 'qatar'),
        ('bahrain', 'bahrain'), ('البحرين', 'bahrain'),
        ('kuwait', 'kuwait'), ('الكويت', 'kuwait'),
        ('uae', 'uae'), ('الإمارات', 'uae'), ('الامارات', 'uae'),
        ('lebanon', 'lebanon'), ('لبنان', 'lebanon'),
        ('morocco', 'morocco'), ('المغرب', 'morocco'),
        ('tunisia', 'tunisia'), ('تونس', 'tunisia'),
        ('malaysia', 'malaysia'), ('ماليزيا', 'malaysia'),
        ('thailand', 'thailand'), ('تايلاند', 'thailand'),
        ('indonesia', 'indonesia'), ('إندونيسيا', 'indonesia'), ('اندونيسيا', 'indonesia'),
        ('japan', 'japan'), ('اليابان', 'japan'),
        ('italy', 'italy'), ('إيطاليا', 'italy'), ('ايطاليا', 'italy'),
        ('france', 'france'), ('فرنسا', 'france'),
        ('spain', 'spain'), ('إسبانيا', 'spain'), ('اسبانيا', 'spain'),
        ('greece', 'greece'), ('اليونان', 'greece'),
        ('germany', 'germany'), ('ألمانيا', 'germany'), ('المانيا', 'germany')
    )
    select case
        when not exists (select 1 from meaningful) then null
        when exists (
            select 1 from meaningful m
            where not exists (select 1 from known k where k.word = m.word)
        ) then null
        else (
            select array_agg(distinct k.country)
            from meaningful m join known k on k.word = m.word
        )
    end
$$;
revoke all on function rihla_private.destination_countries(text) from public, anon, authenticated;

-- For every member of the trip. Returns categories only, never who or which value.
-- The budget floor is fixed here rather than passed in, because a caller-chosen
-- floor would let a member search for the group's lowest budget.
-- Keep 250 in step with MIN_BUDGET_SAR_PER_DAY in the backend settings.
create function public.rihla_get_group_conflicts(p_trip_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
    v_user uuid := rihla_private.require_user();
    v_conflicts text[] := '{}';
    v_own_review text[] := '{}';
    v_count bigint;
    v_date_count bigint;
    v_all_ready boolean;
    v_start date;
    v_end date;
    v_lowest numeric;
    v_essentials bigint;
    v_doubtful bigint;
    v_own_destination jsonb;
begin
    if not rihla_private.is_trip_member(p_trip_id) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;

    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end),
        bool_and(cardinality(rihla_private.preference_missing_fields(p)) = 0),
        min(p.max_budget_sar)
        into v_count, v_date_count, v_start, v_end, v_all_ready, v_lowest
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id where m.trip_id = p_trip_id;

    if not v_all_ready then
        v_conflicts := v_conflicts || 'readiness'::text;
    end if;
    if v_date_count <> v_count or v_start > v_end then
        v_conflicts := v_conflicts || 'dates'::text;
    end if;

    -- These need complete inputs, the same point at which generation could start.
    if cardinality(v_conflicts) = 0 then
        with wanted as (
            select rihla_private.destination_countries(p.destinations->>'value') as countries
            from public.trip_members m join public.member_preferences p
                on p.trip_id = m.trip_id and p.user_id = m.user_id
            where m.trip_id = p_trip_id and p.destinations->>'importance' = 'Essential'
                and btrim(p.destinations->>'value') <> ''
        )
        select count(*), count(*) filter(where countries is null)
            into v_essentials, v_doubtful from wanted;

        if v_essentials > 1 and v_doubtful = 0 and not exists (
            with wanted as (
                select rihla_private.destination_countries(p.destinations->>'value') as countries
                from public.trip_members m join public.member_preferences p
                    on p.trip_id = m.trip_id and p.user_id = m.user_id
                where m.trip_id = p_trip_id and p.destinations->>'importance' = 'Essential'
                    and btrim(p.destinations->>'value') <> ''
            )
            select 1 from wanted w, unnest(w.countries) as country
            group by country having count(*) = v_essentials
        ) then
            v_conflicts := v_conflicts || 'destinations'::text;
        end if;

        if v_lowest < 250 * (v_end - v_start + 1) then
            v_conflicts := v_conflicts || 'budget'::text;
        end if;
    end if;

    -- Only the caller's own Essential decides this notice. Budget never gets one,
    -- because it would tell a member that their budget is the lowest.
    if 'destinations' = any(v_conflicts) then
        select p.destinations into v_own_destination from public.member_preferences p
            where p.trip_id = p_trip_id and p.user_id = v_user;
        if v_own_destination->>'importance' = 'Essential'
            and btrim(v_own_destination->>'value') <> '' then
            v_own_review := v_own_review || 'destinations'::text;
        end if;
    end if;

    return jsonb_build_object('conflicts', to_jsonb(v_conflicts),
        'own_review', to_jsonb(v_own_review),
        'can_generate', cardinality(v_conflicts) = 0);
end;
$$;
revoke all on function public.rihla_get_group_conflicts(uuid) from public, anon, authenticated;
grant execute on function public.rihla_get_group_conflicts(uuid) to authenticated;

-- Backend only. There is no signed-in user with the secret key, so the backend
-- passes the account it verified, and this checks that account is the administrator.
-- Labels are not in join order, and no account ids or names are returned.
create function public.rihla_trip_generation_inputs(p_trip_id uuid, p_admin_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    v_count bigint;
    v_date_count bigint;
    v_all_ready boolean;
    v_start date;
    v_end date;
begin
    if p_admin_id is null or not exists (
        select 1 from public.trips where id = p_trip_id and created_by = p_admin_id
    ) then
        raise exception using errcode = '42501', message = 'trip_access_denied';
    end if;

    select count(*), count(*) filter(where p.available_start is not null
        and p.available_end is not null), max(p.available_start), min(p.available_end),
        bool_and(cardinality(rihla_private.preference_missing_fields(p)) = 0)
        into v_count, v_date_count, v_start, v_end, v_all_ready
        from public.trip_members m left join public.member_preferences p
        on p.trip_id = m.trip_id and p.user_id = m.user_id where m.trip_id = p_trip_id;
    if not v_all_ready or v_date_count <> v_count or v_start > v_end then
        raise exception using errcode = 'P0001', message = 'generation_not_ready';
    end if;

    return jsonb_build_object('trip_id', p_trip_id, 'shared_start', v_start,
        'shared_end', v_end, 'members', (
            select jsonb_agg(jsonb_build_object(
                'label', 'Member ' || position,
                'departure_city', departure_city,
                'max_budget_sar', max_budget_sar::text,
                'destinations', destinations,
                'interests', interests,
                'flights', flights,
                'accommodation', accommodation) order by position)
            from (
                select p.*, row_number() over (
                    order by md5(p.trip_id::text || p.user_id::text)
                ) as position
                from public.member_preferences p
                join public.trip_members m on m.trip_id = p.trip_id and m.user_id = p.user_id
                where p.trip_id = p_trip_id
            ) ordered
        ));
end;
$$;
revoke all on function public.rihla_trip_generation_inputs(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rihla_trip_generation_inputs(uuid, uuid) to service_role;

commit;
