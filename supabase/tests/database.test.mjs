import { createFixtureDatabase } from './fixture.mjs'
import { before, beforeEach, afterEach, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'

// Real PostgreSQL engine in memory; only Supabase's Auth schema/claims are stubbed.
// No credentials, cloud connections, service-role keys or persistent database.
let db
const ALICE = '11111111-1111-4111-8111-111111111111'
const BOB = '22222222-2222-4222-8222-222222222222'
const CAROL = '33333333-3333-4333-8333-333333333333'


async function role(user, extraClaims = {}) {
  await db.exec('set local role authenticated')
  await db.query("select set_config('request.jwt.claims', $1, true)", [JSON.stringify({ sub: user, role: 'authenticated', ...extraClaims })])
}
async function root() { await db.exec('reset role') }
async function rpc(name, args = []) {
  const placeholders = args.map((_, index) => `$${index + 1}`).join(',')
  const { rows } = await db.query(`select public.${name}(${placeholders}) as result`, args)
  return rows[0].result
}
async function denied(action, code = '42501') {
  await db.exec('savepoint expected_failure')
  try { await assert.rejects(action, (error) => error.code === code) }
  finally { await db.exec('rollback to savepoint expected_failure; release savepoint expected_failure') }
}
async function trip() {
  await role(ALICE)
  return rpc('rihla_create_trip', ['A weekend away', 'Our next group adventure'])
}
async function invitedTrip() {
  const created = await trip()
  const invitation = await rpc('rihla_issue_invitation', [created.id])
  return { created, invitation }
}

before(async () => { db = await createFixtureDatabase() })
beforeEach(() => db.exec('begin'))
afterEach(async () => { await db.exec('rollback'); await root() })
after(() => db.close())

const inputs = {
  departure_city: 'Riyadh', max_budget_sar: '4500.50',
  available_start: '2026-11-10', available_end: '2026-11-15',
  destinations: { value: 'Japan', importance: 'Flexible' },
  flights: { value: 'Direct flights', importance: 'Essential' },
}
async function savePreferences(id, data = inputs) {
  return rpc('rihla_save_preferences', [id, JSON.stringify(data)])
}

const planning = (id) => rpc('rihla_get_planning_status', [id])

test('readiness starts Incomplete with only the caller’s missing fields and pending group dates', async () => {
  const created = await trip()
  const result = await planning(created.id)
  assert.deepEqual(result.own_readiness, { status: 'Incomplete', missing_fields: ['departure_city', 'max_budget_sar', 'available_start', 'available_end'] })
  assert.deepEqual(result.member_readiness, [{ user_id: ALICE, status: 'Incomplete' }])
  assert.deepEqual(result.shared_dates, { status: 'pending', start: null, end: null, duration_days: null })
})

test('required inputs automatically make a member Ready; optional Essential blanks do not block readiness', async () => {
  const created = await trip()
  await savePreferences(created.id, { ...inputs, destinations: { value: '', importance: 'Essential' } })
  const result = await planning(created.id)
  assert.deepEqual(result.own_readiness, { status: 'Ready', missing_fields: [] })
  assert.deepEqual(result.shared_dates, { status: 'available', start: '2026-11-10', end: '2026-11-15', duration_days: 6 })
})

test('group intersection uses latest start and earliest end, including administrator availability', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-12', available_end: '2026-11-20' })
  const result = await planning(created.id)
  assert.deepEqual(result.shared_dates, { status: 'available', start: '2026-11-12', end: '2026-11-15', duration_days: 4 })
  assert.equal(result.member_readiness, null)
  await role(ALICE)
  const administrator = await planning(created.id)
  assert.deepEqual(administrator.member_readiness, [{ user_id: ALICE, status: 'Ready' }, { user_id: BOB, status: 'Ready' }])
  assert.deepEqual(administrator.shared_dates, result.shared_dates)
})

test('administrator sees only status for other members; ordinary members get no readiness roster', async () => {
  const { created, invitation } = await invitedTrip()
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { departure_city: 'Private city', max_budget_sar: '5432.10', interests: { value: 'Private interests', importance: 'Essential' } })
  const own = await planning(created.id)
  assert.deepEqual(own.own_readiness.missing_fields, ['available_start', 'available_end'])
  assert.equal(own.member_readiness, null)
  await role(ALICE)
  const administrator = await planning(created.id)
  assert.deepEqual(administrator.member_readiness.find((member) => member.user_id === BOB), { user_id: BOB, status: 'Incomplete' })
  assert.equal(JSON.stringify(administrator).includes('Private'), false)
  assert.equal(JSON.stringify(administrator).includes('5432'), false)
  assert.equal((await db.query('select * from public.member_preferences where user_id = $1', [BOB])).rows.length, 0)
})

test('all Ready members with nonoverlapping dates have a group conflict without revealing individual dates', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-16', available_end: '2026-11-20' })
  assert.equal((await planning(created.id)).own_readiness.status, 'Ready')
  await role(ALICE)
  const result = await planning(created.id)
  assert.ok(result.member_readiness.every((member) => member.status === 'Ready'))
  assert.deepEqual(result.shared_dates, { status: 'conflict', start: null, end: null, duration_days: null })
  assert.equal(JSON.stringify(result).includes('2026-11'), false)
})

test('touching endpoints are a one-day overlap, and edits immediately resolve a conflict', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-16', available_end: '2026-11-20' })
  assert.equal((await planning(created.id)).shared_dates.status, 'conflict')
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-15', available_end: '2026-11-20' })
  assert.deepEqual((await planning(created.id)).shared_dates, { status: 'available', start: '2026-11-15', end: '2026-11-15', duration_days: 1 })
})

test('calendar duration includes leap day without timezone or DST arithmetic', async () => {
  const created = await trip()
  await savePreferences(created.id, { ...inputs, available_start: '2028-02-28', available_end: '2028-03-01' })
  assert.equal((await planning(created.id)).shared_dates.duration_days, 3)
})

test('clearing required information reverses readiness while valid dates remain a separate result', async () => {
  const created = await trip()
  await savePreferences(created.id)
  assert.equal((await planning(created.id)).own_readiness.status, 'Ready')
  await savePreferences(created.id, { ...inputs, departure_city: '   ', max_budget_sar: null })
  const result = await planning(created.id)
  assert.deepEqual(result.own_readiness, { status: 'Incomplete', missing_fields: ['departure_city', 'max_budget_sar'] })
  assert.equal(result.shared_dates.status, 'available')
  await savePreferences(created.id, { ...inputs, available_end: null })
  assert.equal((await planning(created.id)).shared_dates.status, 'pending')
})

test('a new member without inputs makes shared dates pending, duplicate joins do not reset saved inputs', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id)
  assert.equal((await planning(created.id)).shared_dates.status, 'available')
  await rpc('rihla_join_trip', [invitation.token])
  assert.equal((await planning(created.id)).own_readiness.status, 'Ready')
  await role(CAROL); await rpc('rihla_join_trip', [invitation.token])
  assert.equal((await planning(created.id)).shared_dates.status, 'pending')
  await role(ALICE)
  const result = await planning(created.id)
  assert.equal(result.member_readiness.length, 3)
  assert.deepEqual(result.member_readiness.find((member) => member.user_id === CAROL), { user_id: CAROL, status: 'Incomplete' })
})

test('planning aggregation rejects unrelated, signed-out and anonymous Auth callers', async () => {
  const created = await trip()
  await role(BOB); await denied(() => planning(created.id))
  await db.exec('set local role anon'); await denied(() => planning(created.id))
  await role(ALICE, { is_anonymous: true }); await denied(() => planning(created.id))
  await role(ALICE)
  await denied(() => db.query('select rihla_private.preference_missing_fields(null::public.member_preferences)'))
})

test('invalid preference updates leave readiness and shared dates unchanged', async () => {
  const created = await trip()
  await savePreferences(created.id)
  const original = await planning(created.id)
  await denied(() => savePreferences(created.id, { ...inputs, available_end: '2026-11-01' }), '23514')
  assert.deepEqual(await planning(created.id), original)
})

test('preferences return a private empty draft before the first save', async () => {
  const created = await trip()
  const draft = await rpc('rihla_get_preferences', [created.id])
  assert.equal(draft.departure_city, '')
  assert.equal(draft.max_budget_sar, null)
  assert.equal(draft.available_start, null)
  assert.equal(draft.updated_at, null)
  assert.equal(draft.currency, 'SAR')
  assert.deepEqual(draft.interests, { value: '', importance: 'Flexible' })
  assert.equal('user_id' in draft, false)
})

test('own preferences save, persist, update and clear without affecting another trip', async () => {
  const first = await trip()
  const second = await trip()
  const saved = await savePreferences(first.id)
  assert.equal(saved.departure_city, 'Riyadh')
  assert.equal(Number(saved.max_budget_sar), 4500.5)
  assert.equal(saved.available_start, '2026-11-10')
  assert.equal(saved.flights.importance, 'Essential')
  assert.ok(saved.updated_at)
  assert.deepEqual(await rpc('rihla_get_preferences', [first.id]), saved)
  const updated = await savePreferences(first.id, { ...inputs, departure_city: 'Jeddah' })
  assert.equal(updated.departure_city, 'Jeddah')
  assert.equal((await rpc('rihla_get_preferences', [second.id])).updated_at, null)
  const cleared = await savePreferences(first.id, {})
  assert.equal(cleared.max_budget_sar, null)
  assert.equal(cleared.available_end, null)
  assert.equal(cleared.departure_city, '')
  assert.equal((await db.query('select * from public.member_preferences')).rows.length, 1)
})

test('incomplete drafts and inclusive single-day availability are allowed', async () => {
  const created = await trip()
  await savePreferences(created.id, { departure_city: 'Riyadh', available_start: '2026-11-10' })
  const result = await savePreferences(created.id, { available_start: '2026-11-10', available_end: '2026-11-10' })
  assert.equal(result.available_start, result.available_end)
  assert.equal(result.max_budget_sar, null)
})

test('members and administrators cannot read or update each other’s private inputs', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  assert.equal((await rpc('rihla_get_preferences', [created.id])).updated_at, null)
  await savePreferences(created.id, { ...inputs, departure_city: 'Dammam', max_budget_sar: '8000' })
  assert.deepEqual((await db.query('select user_id from public.member_preferences')).rows, [{ user_id: BOB }])
  assert.equal((await db.query('update public.member_preferences set departure_city = $1 where user_id = $2 returning *', ['Forged', ALICE])).rows.length, 0)
  await role(ALICE)
  assert.equal((await rpc('rihla_get_preferences', [created.id])).departure_city, 'Riyadh')
  assert.deepEqual((await db.query('select user_id from public.member_preferences')).rows, [{ user_id: ALICE }])
  assert.equal((await db.query('select * from public.member_preferences where user_id = $1', [BOB])).rows.length, 0)
  assert.equal((await db.query('update public.member_preferences set departure_city = $1 where user_id = $2 returning *', ['Forged', BOB])).rows.length, 0)
  assert.equal(JSON.stringify(await rpc('rihla_get_trip', [created.id])).includes('max_budget_sar'), false)
})

test('nonmembers cannot use preference RPCs or write their own row in another trip', async () => {
  const created = await trip()
  await role(CAROL)
  await denied(() => rpc('rihla_get_preferences', [created.id]))
  await denied(() => savePreferences(created.id))
  await denied(() => db.query('insert into public.member_preferences(trip_id, user_id) values($1,$2)', [created.id, CAROL]))
  assert.equal((await db.query('select * from public.member_preferences')).rows.length, 0)
})

test('even an administrator cannot insert a preference row with another member’s identity', async () => {
  const { created, invitation } = await invitedTrip()
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await role(ALICE)
  await denied(() => db.query('insert into public.member_preferences(trip_id, user_id) values($1,$2)', [created.id, BOB]))
  await savePreferences(created.id)
  await denied(() => db.query('update public.member_preferences set user_id = $1', [BOB]))
})

test('preference data and RPCs deny anonymous requests and anonymous Auth users', async () => {
  const created = await trip()
  await savePreferences(created.id)
  await db.exec('set local role anon')
  await denied(() => db.exec('select * from public.member_preferences'))
  await denied(() => rpc('rihla_get_preferences', [created.id]))
  await denied(() => savePreferences(created.id))
  await role(ALICE, { is_anonymous: true })
  assert.equal((await db.query('select * from public.member_preferences')).rows.length, 0)
  await denied(() => savePreferences(created.id))
})

test('invalid budgets, date order and malformed optional preferences roll back the save', async () => {
  const created = await trip()
  const original = await savePreferences(created.id)
  for (const patch of [
    { max_budget_sar: '-1' }, { max_budget_sar: '0' }, { max_budget_sar: '1.001' },
    { max_budget_sar: '10000000000' }, { max_budget_sar: 'NaN' },
    { available_end: '2026-11-09' }, { available_end: 'infinity' },
    { departure_city: 'x'.repeat(101) },
    { interests: { value: 'x'.repeat(501), importance: 'Flexible' } },
    { interests: { value: 'Food', importance: 'Maybe' } },
    { destinations: { value: 'Japan', importance: 'Flexible', user_id: BOB } },
    { accommodation: null }, { flights: 'Direct flights' },
    { user_id: BOB }, { currency: 'USD' },
  ]) await denied(() => savePreferences(created.id, { ...inputs, ...patch }), '23514')
  assert.deepEqual(await rpc('rihla_get_preferences', [created.id]), original)
})

test('direct Data API writes still enforce preference constraints and RLS', async () => {
  const created = await trip()
  await savePreferences(created.id)
  await denied(() => db.exec("update public.member_preferences set max_budget_sar = -10"), '23514')
  await denied(() => db.exec("update public.member_preferences set interests = '{}'::jsonb"), '23514')
  await denied(() => db.exec('delete from public.member_preferences'))
  await root()
  assert.equal((await db.query("select relrowsecurity from pg_class where oid = 'public.member_preferences'::regclass")).rows[0].relrowsecurity, true)
})

test('trip creation includes creator membership and an administrator role', async () => {
  const created = await trip()
  assert.equal(created.role, 'administrator')
  assert.equal(created.member_count, 1)
  assert.deepEqual(created.members.map(({ user_id, role }) => ({ user_id, role })), [{ user_id: ALICE, role: 'administrator' }])
  assert.equal(created.members[0].display_name, 'Alice')
  assert.equal((await rpc('rihla_list_trips')).length, 1)
})

test('unrelated users see no trips or memberships, and cannot fetch details', async () => {
  const created = await trip()
  await role(BOB)
  assert.deepEqual(await rpc('rihla_list_trips'), [])
  assert.equal((await db.query('select * from public.trips')).rows.length, 0)
  assert.equal((await db.query('select * from public.trip_members')).rows.length, 0)
  await denied(() => rpc('rihla_get_trip', [created.id]))
})

test('table writes cannot forge membership or change the administrator', async () => {
  const created = await trip()
  await role(BOB)
  await denied(() => db.query('insert into public.trip_members(trip_id, user_id) values ($1, $2)', [created.id, BOB]))
  await denied(() => db.query('update public.trips set created_by = $1 where id = $2', [BOB, created.id]))
  await denied(() => db.exec('delete from public.trip_members'))
  await role(ALICE)
  await denied(() => db.exec("update public.trips set title = 'Bypass'"))
})

test('invalid title/description input rolls back without a trip', async () => {
  await role(ALICE)
  for (const title of ['', 'x', 'x'.repeat(101)]) await denied(() => rpc('rihla_create_trip', [title, '']), '23514')
  await denied(() => rpc('rihla_create_trip', ['Valid title', 'x'.repeat(501)]), '23514')
  assert.deepEqual(await rpc('rihla_list_trips'), [])
})

test('membership failure rolls back the trip insert atomically', async () => {
  await db.exec(`create function public.test_fail_membership() returns trigger language plpgsql as
    $$begin raise exception using errcode = '23514', message = 'simulated membership failure'; end$$;
    create trigger test_fail_membership before insert on public.trip_members for each row execute function public.test_fail_membership();`)
  await role(ALICE)
  await denied(() => rpc('rihla_create_trip', ['Must roll back', '']), '23514')
  await root()
  assert.equal((await db.query('select count(*)::int as count from public.trips')).rows[0].count, 0)
})

test('anonymous callers cannot read tables or execute trip RPCs', async () => {
  const created = await trip()
  await db.exec('set local role anon')
  await denied(() => db.exec('select * from public.trips'))
  await denied(() => db.exec('select * from public.trip_invitations'))
  await denied(() => rpc('rihla_list_trips'))
  await denied(() => rpc('rihla_get_trip', [created.id]))
  await denied(() => rpc('rihla_create_trip', ['Forged', '']))
  await denied(() => rpc('rihla_join_trip', ['a'.repeat(64)]))
})

test('anonymous Supabase Auth accounts cannot use guarded RPCs', async () => {
  const { invitation } = await invitedTrip()
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  await role(BOB, { is_anonymous: true })
  assert.equal((await db.query('select * from public.trips')).rows.length, 0)
  assert.equal((await db.query('select * from public.trip_members')).rows.length, 0)
  await denied(() => rpc('rihla_create_trip', ['Anonymous account', '']))
  await denied(() => rpc('rihla_list_trips'))
})

test('invitation is strong, stored as a hash and valid for exactly seven days', async () => {
  const { created, invitation } = await invitedTrip()
  assert.match(invitation.token, /^[0-9a-f]{64}$/)
  await denied(() => db.exec('select * from public.trip_invitations'))
  const status = await rpc('rihla_get_invitation', [created.id])
  assert.equal(status.exists, true)
  assert.equal(status.revoked, false)
  assert.equal('token' in status, false)
  await root()
  const row = (await db.query('select token_hash, extract(epoch from expires_at - created_at)::int as seconds from public.trip_invitations')).rows[0]
  assert.equal(row.token_hash, createHash('sha256').update(invitation.token).digest('hex'))
  assert.notEqual(row.token_hash, invitation.token)
  assert.equal(row.seconds, 7 * 24 * 60 * 60)
})

test('invitation join creates one ordinary membership and is idempotent', async () => {
  const { invitation } = await invitedTrip()
  await role(BOB)
  const first = await rpc('rihla_join_trip', [invitation.token])
  assert.equal(first.already_member, false)
  assert.equal(first.trip.role, 'member')
  assert.equal(first.trip.member_count, 2)
  const again = await rpc('rihla_join_trip', [invitation.token])
  assert.equal(again.already_member, true)
  assert.equal(again.trip.member_count, 2)
  assert.equal((await rpc('rihla_list_trips')).length, 1)
})

test('creator joining their own invitation stays administrator without duplication', async () => {
  const { invitation } = await invitedTrip()
  const result = await rpc('rihla_join_trip', [invitation.token])
  assert.equal(result.already_member, true)
  assert.equal(result.trip.role, 'administrator')
  assert.equal(result.trip.member_count, 1)
})

test('ordinary members cannot inspect, replace or revoke invitations', async () => {
  const { created, invitation } = await invitedTrip()
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  for (const name of ['rihla_get_invitation', 'rihla_issue_invitation', 'rihla_revoke_invitation']) await denied(() => rpc(name, [created.id]))
  await denied(() => db.exec('select * from public.trip_invitations'))
})

test('replacing an invitation immediately invalidates the previous token', async () => {
  const { created, invitation } = await invitedTrip()
  const replacement = await rpc('rihla_issue_invitation', [created.id])
  assert.notEqual(replacement.token, invitation.token)
  await role(BOB)
  await denied(() => rpc('rihla_join_trip', [invitation.token]), 'P0001')
  assert.equal((await rpc('rihla_join_trip', [replacement.token])).trip.member_count, 2)
  await root()
  assert.equal((await db.query('select count(*)::int as count from public.trip_invitations')).rows[0].count, 1)
})

test('revocation blocks joins and does not remove existing members', async () => {
  const { created, invitation } = await invitedTrip()
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  await role(ALICE)
  assert.equal((await rpc('rihla_revoke_invitation', [created.id])).revoked, true)
  await role(CAROL)
  await denied(() => rpc('rihla_join_trip', [invitation.token]), 'P0001')
  await role(BOB)
  assert.equal((await rpc('rihla_get_trip', [created.id])).member_count, 2)
})

test('expired invitations cannot add a member', async () => {
  const { created, invitation } = await invitedTrip()
  await root()
  await db.query("update public.trip_invitations set created_at = now() - interval '8 days', expires_at = now() - interval '1 day' where trip_id = $1", [created.id])
  await role(BOB)
  await denied(() => rpc('rihla_join_trip', [invitation.token]), 'P0001')
  assert.deepEqual(await rpc('rihla_list_trips'), [])
})

test('invalid invitation input cannot reveal a trip or add membership', async () => {
  await role(BOB)
  for (const token of ['bad', '', 'a'.repeat(64)]) await denied(() => rpc('rihla_join_trip', [token]), 'P0001')
  assert.deepEqual(await rpc('rihla_list_trips'), [])
})

test('member roster exposes names and roles, not email or private profile access', async () => {
  const { invitation } = await invitedTrip()
  await role(BOB)
  const { trip } = await rpc('rihla_join_trip', [invitation.token])
  assert.deepEqual(Object.keys(trip.members[0]).sort(), ['display_name', 'joined_at', 'role', 'user_id'])
  assert.equal(JSON.stringify(trip).includes('email'), false)
  assert.deepEqual((await db.query('select id from public.profiles')).rows.map((row) => row.id), [BOB])
  // An invisible row yields zero updates rather than an exception.
  const update = await db.query("update public.profiles set display_name = 'Tampered' where id = $1 returning id", [ALICE])
  assert.equal(update.rows.length, 0)
})

test('all trip tables have RLS and anonymous RPC execution is revoked', async () => {
  const rows = (await db.query("select relname, relrowsecurity from pg_class where oid in ('public.trips'::regclass, 'public.trip_members'::regclass, 'public.trip_invitations'::regclass)")).rows
  assert.equal(rows.length, 3)
  assert.ok(rows.every((row) => row.relrowsecurity))
  const grants = (await db.query("select has_function_privilege('anon', 'public.rihla_issue_invitation(uuid)', 'execute') as anonymous, has_table_privilege('authenticated', 'public.trip_invitations', 'select') as invitation_read")).rows[0]
  assert.equal(grants.anonymous, false)
  assert.equal(grants.invitation_read, false)

})

test('private profile grants reject anonymous access and forged owners', async () => {
  await db.exec('set local role anon')
  await denied(() => db.exec('select * from public.profiles'))
  await role(BOB)
  await denied(() => db.query('update public.profiles set id = $1 where id = $2', [CAROL, BOB]))
  await denied(() => db.exec('update public.profiles set created_at = now()'))
  await denied(() => db.exec('delete from public.profiles'))
})

test('profile name constraints hold in PostgreSQL, and own upsert works', async () => {
  await role(BOB)
  for (const name of ['x', '  Bob  ', 'x'.repeat(81)]) {
    await denied(() => db.query('update public.profiles set display_name = $1', [name]), '23514')
  }
  await db.query('insert into public.profiles(id, display_name) values ($1,$2) on conflict(id) do update set id = excluded.id, display_name = excluded.display_name', [BOB, 'Bob Updated'])
  assert.equal((await db.query('select display_name from public.profiles')).rows[0].display_name, 'Bob Updated')
})
