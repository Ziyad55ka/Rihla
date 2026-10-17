-- Run only on a disposable local Supabase database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(19);

insert into auth.users (id, email) values
    ('11111111-1111-4111-8111-111111111111', 'alice@example.test'),
    ('22222222-2222-4222-8222-222222222222', 'bob@example.test');

select has_table('public', 'profiles', 'Account profiles table exists');
select ok((select relrowsecurity from pg_class where oid = 'public.profiles'::regclass),
    'RLS is enabled');

set local role anon;
select throws_ok('select * from public.profiles', '42501', null,
    'Anonymous users cannot read profiles');
select throws_ok($$insert into public.profiles(id, display_name) values
    ('11111111-1111-4111-8111-111111111111', 'Alice')$$, '42501', null,
    'Anonymous users cannot create profiles');

reset role;
set local role authenticated;
select set_config('request.jwt.claims',
    '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);

select lives_ok($$insert into public.profiles(id, display_name) values
    ('11111111-1111-4111-8111-111111111111', 'Alice')$$,
    'Alice can create her own profile');
select is((select count(*) from public.profiles), 1::bigint,
    'Alice sees her own profile');
select throws_ok($$insert into public.profiles(id, display_name) values
    ('22222222-2222-4222-8222-222222222222', 'Fake Bob')$$, '42501', null,
    'Alice cannot create a profile for Bob');
select lives_ok($$update public.profiles set display_name = 'Alice Updated'
    where id = '11111111-1111-4111-8111-111111111111'$$,
    'Alice can edit her own name');
select throws_ok($$update public.profiles set id = '22222222-2222-4222-8222-222222222222'
    where id = '11111111-1111-4111-8111-111111111111'$$, '42501', null,
    'Alice cannot transfer profile ownership');
select throws_ok($$update public.profiles set created_at = now()$$, '42501', null,
    'Clients cannot rewrite creation timestamps');
select throws_ok($$update public.profiles set display_name = 'x'$$, '23514', null,
    'Database rejects a name shorter than two characters');
select throws_ok($$update public.profiles set display_name = repeat('x', 81)$$,
    '23514', null, 'Database rejects a name longer than eighty characters');
select throws_ok($$update public.profiles set display_name = ' Alice '$$,
    '23514', null, 'Database rejects untrimmed names');

select set_config('request.jwt.claims',
    '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
select is((select count(*) from public.profiles), 0::bigint,
    'Bob cannot read Alice profile');
select results_eq($$update public.profiles set display_name = 'Tampered'
    where id = '11111111-1111-4111-8111-111111111111' returning id$$,
    array[]::uuid[], 'Bob cannot update Alice profile');
select lives_ok($$insert into public.profiles(id, display_name) values
    ('22222222-2222-4222-8222-222222222222', 'Bob')
    on conflict(id) do update set id = excluded.id, display_name = excluded.display_name$$,
    'Bob can upsert his own profile using API column grants');
select lives_ok($$insert into public.profiles(id, display_name) values
    ('22222222-2222-4222-8222-222222222222', 'Bob Updated')
    on conflict(id) do update set id = excluded.id, display_name = excluded.display_name$$,
    'Repeated save updates the existing profile');
select throws_ok('delete from public.profiles', '42501', null,
    'Users cannot delete profiles directly');
select is((select count(*) from public.profiles), 1::bigint,
    'Bob only sees his own profile after both users saved');

reset role;
select * from finish();
rollback;
