import { createFixtureDatabase } from './fixture.mjs'
import { before, beforeEach, afterEach, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'

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
const checkDates = (id, start, end) => rpc('rihla_check_trip_dates', [id, start, end])

test('upgrading preserves legacy drafts and allows completing them under the new save rule', async () => {
  const upgrade = await createFixtureDatabase({ throughMigration: '20261017000200_invitation_codes.sql' })
  try {
    await upgrade.exec('begin; set local role authenticated')
    await upgrade.query("select set_config('request.jwt.claims', $1, true)", [JSON.stringify({ sub: ALICE, role: 'authenticated' })])
    const { rows } = await upgrade.query("select public.rihla_create_trip('Legacy trip', '') as result")
    const id = rows[0].result.id
    await upgrade.query('select public.rihla_save_preferences($1, $2)', [id, JSON.stringify({ available_start: '2026-11-10' })])
    await upgrade.exec('commit; reset role')
    await upgrade.exec(await readFile(new URL('../migrations/20261021000100_shared_member_dates_and_required_preferences.sql', import.meta.url), 'utf8'))
    await upgrade.exec('begin; set local role authenticated')
    await upgrade.query("select set_config('request.jwt.claims', $1, true)", [JSON.stringify({ sub: ALICE, role: 'authenticated' })])
    const legacy = (await upgrade.query('select public.rihla_get_preferences($1) as result', [id])).rows[0].result
    assert.equal(legacy.departure_city, '')
    assert.equal(legacy.available_start, '2026-11-10')
    assert.equal(legacy.available_end, null)
    const status = (await upgrade.query('select public.rihla_get_planning_status($1) as result', [id])).rows[0].result
    assert.equal(status.own_readiness.status, 'Incomplete')
    assert.deepEqual(status.member_dates, [{ user_id: ALICE, available_start: '2026-11-10', available_end: null }])
    const completed = (await upgrade.query('select public.rihla_save_preferences($1, $2) as result', [id, JSON.stringify(inputs)])).rows[0].result
    assert.equal(completed.departure_city, 'Riyadh')
    await assert.rejects(() => upgrade.query('update public.member_preferences set available_end = null'), (error) => error.code === '23514')
    await upgrade.exec('rollback')
  } finally { await upgrade.close() }
})

test('readiness starts Incomplete with only the caller’s missing fields and pending group dates', async () => {
  const created = await trip()
  const result = await planning(created.id)
  assert.deepEqual(result.own_readiness, { status: 'Incomplete', missing_fields: ['departure_city', 'max_budget_sar', 'available_start', 'available_end'], has_saved_preferences: false })
  assert.equal(result.all_members_ready, false)
  assert.deepEqual(result.member_readiness, [{ user_id: ALICE, status: 'Incomplete' }])
  assert.deepEqual(result.shared_dates, { status: 'pending', start: null, end: null, duration_days: null })
})

test('required inputs automatically make a member Ready; optional Essential blanks do not block readiness', async () => {
  const created = await trip()
  await savePreferences(created.id, { ...inputs, destinations: { value: '', importance: 'Essential' } })
  const result = await planning(created.id)
  assert.deepEqual(result.own_readiness, { status: 'Ready', missing_fields: [], has_saved_preferences: true })
  assert.equal(result.all_members_ready, true)
  assert.deepEqual(result.shared_dates, { status: 'available', start: '2026-11-10', end: '2026-11-15', duration_days: 6 })
})

test('all trip members see each other’s dates, including unsaved members, without exposing other inputs or trips', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  const other = await trip()
  await savePreferences(other.id, { ...inputs, available_start: '2027-01-01', available_end: '2027-01-05' })
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  let result = await planning(created.id)
  assert.equal(result.member_readiness, null)
  assert.deepEqual(result.member_dates, [
    { user_id: ALICE, available_start: '2026-11-10', available_end: '2026-11-15' },
    { user_id: BOB, available_start: null, available_end: null },
  ])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-12', available_end: '2026-11-20' })
  result = await planning(created.id)
  assert.deepEqual(result.member_dates[1], { user_id: BOB, available_start: '2026-11-12', available_end: '2026-11-20' })
  assert.equal((await db.query('select * from public.member_preferences where user_id = $1', [ALICE])).rows.length, 0)
  await role(ALICE)
  assert.deepEqual((await planning(created.id)).member_dates, result.member_dates)
  assert.equal(JSON.stringify(result.member_dates).includes('2027-01'), false)
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
  await savePreferences(created.id, { ...inputs, departure_city: 'Private city', max_budget_sar: '5432.10', interests: { value: 'Private interests', importance: 'Essential' } })
  const own = await planning(created.id)
  assert.deepEqual(own.own_readiness.missing_fields, [])
  assert.equal(own.member_readiness, null)
  await role(ALICE)
  const administrator = await planning(created.id)
  assert.deepEqual(administrator.member_readiness.find((member) => member.user_id === BOB), { user_id: BOB, status: 'Ready' })
  assert.equal(JSON.stringify(administrator).includes('Private'), false)
  assert.equal(JSON.stringify(administrator).includes('5432'), false)
  assert.equal((await db.query('select * from public.member_preferences where user_id = $1', [BOB])).rows.length, 0)
})

test('all Ready members with nonoverlapping dates have a group conflict and shared member dates', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-16', available_end: '2026-11-20' })
  assert.equal((await planning(created.id)).own_readiness.status, 'Ready')
  await role(ALICE)
  const result = await planning(created.id)
  assert.ok(result.member_readiness.every((member) => member.status === 'Ready'))
  assert.deepEqual(result.shared_dates, { status: 'conflict', start: null, end: null, duration_days: null })
  assert.deepEqual(result.member_dates, [
    { user_id: ALICE, available_start: '2026-11-10', available_end: '2026-11-15' },
    { user_id: BOB, available_start: '2026-11-16', available_end: '2026-11-20' },
  ])
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

test('clearing required information is rejected without altering saved preferences or readiness', async () => {
  const created = await trip()
  await savePreferences(created.id)
  assert.equal((await planning(created.id)).own_readiness.status, 'Ready')
  const original = await planning(created.id)
  await denied(() => savePreferences(created.id, { ...inputs, departure_city: '   ', max_budget_sar: null }), '23514')
  await denied(() => savePreferences(created.id, { ...inputs, available_end: null }), '23514')
  assert.deepEqual(await planning(created.id), original)
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

test('members receive a group readiness flag, shared dates and their own saved-input indicator', async () => {
  const { created, invitation } = await invitedTrip()
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  let result = await planning(created.id)
  assert.equal(result.own_readiness.has_saved_preferences, false)
  assert.equal(result.all_members_ready, false)
  assert.equal(result.member_readiness, null)
  await savePreferences(created.id)
  await role(ALICE); await savePreferences(created.id)
  await role(BOB)
  result = await planning(created.id)
  assert.equal(result.all_members_ready, true)
  assert.equal(result.member_readiness, null)
  assert.deepEqual(Object.keys(result).sort(), ['all_members_ready', 'member_dates', 'member_readiness', 'own_readiness', 'shared_dates'])
  await role(CAROL); await rpc('rihla_join_trip', [invitation.token])
  await role(BOB)
  assert.equal((await planning(created.id)).all_members_ready, false)
})

test('candidate dates exclude the caller’s stored range and do not save or alter inputs', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-12-01', available_end: '2026-12-05' })
  const original = await rpc('rihla_get_preferences', [created.id])
  assert.deepEqual(await checkDates(created.id, '2026-11-15', '2026-11-20'), { status: 'available' })
  assert.deepEqual(await checkDates(created.id, '2026-11-16', '2026-11-20'), { status: 'conflict' })
  assert.deepEqual(await rpc('rihla_get_preferences', [created.id]), original)
  assert.equal((await planning(created.id)).shared_dates.status, 'conflict')
})

test('date checks handle an empty group, incomplete other ranges and a known conflict', async () => {
  const { created, invitation } = await invitedTrip()
  assert.deepEqual(await checkDates(created.id, '0001-01-01', '9999-12-31'), { status: 'available' })
  assert.equal((await planning(created.id)).own_readiness.has_saved_preferences, false)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await role(ALICE)
  assert.deepEqual(await checkDates(created.id, '2026-11-10', '2026-11-15'), { status: 'pending' })
  await savePreferences(created.id)
  await role(CAROL); await rpc('rihla_join_trip', [invitation.token])
  assert.deepEqual(await checkDates(created.id, '2026-12-01', '2026-12-05'), { status: 'conflict' })
  assert.deepEqual(await checkDates(created.id, '2026-11-12', '2026-11-15'), { status: 'pending' })
})

test('date checks intersect all other members rather than testing only pairwise overlap', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id)
  await role(BOB); await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, { ...inputs, available_start: '2026-11-16', available_end: '2026-11-20' })
  await role(CAROL); await rpc('rihla_join_trip', [invitation.token])
  assert.deepEqual(await checkDates(created.id, '2026-11-10', '2026-11-20'), { status: 'conflict' })
})

test('date-check RPC rejects invalid ranges and dates beyond the application calendar bounds', async () => {
  const created = await trip()
  for (const [start, end] of [[null, '2026-11-15'], ['2026-11-10', null], ['2026-11-15', '2026-11-10'], ['0001-01-01 BC', '2026-11-15'], ['2026-11-10', '10000-01-01'], ['infinity', 'infinity']]) {
    await denied(() => checkDates(created.id, start, end), '23514')
  }
  assert.equal((await planning(created.id)).own_readiness.has_saved_preferences, false)
})

test('date-check aggregation rejects nonmembers, signed-out users and anonymous Auth users', async () => {
  const created = await trip()
  await role(BOB); await denied(() => checkDates(created.id, '2026-11-10', '2026-11-15'))
  await db.exec('set local role anon'); await denied(() => checkDates(created.id, '2026-11-10', '2026-11-15'))
  await role(ALICE, { is_anonymous: true }); await denied(() => checkDates(created.id, '2026-11-10', '2026-11-15'))
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

test('own preferences save, persist and update without affecting another trip; clearing is rejected', async () => {
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
  await denied(() => savePreferences(first.id, {}), '23514')
  assert.deepEqual(await rpc('rihla_get_preferences', [first.id]), updated)
  assert.equal((await db.query('select * from public.member_preferences')).rows.length, 1)
})

test('incomplete submissions are rejected; complete single-day availability is allowed', async () => {
  const created = await trip()
  await denied(() => savePreferences(created.id, { departure_city: 'Riyadh', available_start: '2026-11-10' }), '23514')
  const result = await savePreferences(created.id, { ...inputs, available_end: '2026-11-10' })
  assert.equal(result.available_start, result.available_end)
  assert.equal(Number(result.max_budget_sar), 4500.5)
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
    { departure_city: '' }, { departure_city: '   ' }, { departure_city: '\t\n' }, { max_budget_sar: null },
    { available_start: null }, { available_end: null },
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
  await denied(() => db.exec("update public.member_preferences set departure_city = '   '"), '23514')
  await denied(() => db.exec('update public.member_preferences set max_budget_sar = null'), '23514')
  await denied(() => db.exec('update public.member_preferences set available_start = null'), '23514')
  await denied(() => db.exec('update public.member_preferences set available_end = null'), '23514')
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
  assert.match(invitation.code, /^[0-9]{6}$/)
  await denied(() => db.exec('select * from public.trip_invitations'))
  const status = await rpc('rihla_get_invitation', [created.id])
  assert.equal(status.exists, true)
  assert.equal(status.revoked, false)
  assert.equal('token' in status, false)
  assert.equal('code' in status, false)
  await root()
  const row = (await db.query('select token_hash, code_hash, extract(epoch from expires_at - created_at)::int as seconds from public.trip_invitations')).rows[0]
  assert.equal(row.token_hash, createHash('sha256').update(invitation.token).digest('hex'))
  assert.equal(row.code_hash, createHash('sha256').update(invitation.code).digest('hex'))
  assert.notEqual(row.token_hash, invitation.token)
  assert.notEqual(row.code_hash, invitation.code)
  assert.equal(row.seconds, 7 * 24 * 60 * 60)
})

test('six-digit invitation code joins the same trip', async () => {
  const { invitation } = await invitedTrip()
  await role(BOB)
  const result = await rpc('rihla_join_trip', [invitation.code])
  assert.equal(result.already_member, false)
  assert.equal(result.trip.role, 'member')
  assert.equal(result.trip.member_count, 2)
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

test('replacing an invitation immediately invalidates the previous token and code', async () => {
  const { created, invitation } = await invitedTrip()
  const replacement = await rpc('rihla_issue_invitation', [created.id])
  assert.notEqual(replacement.token, invitation.token)
  assert.notEqual(replacement.code, invitation.code)
  await role(BOB)
  await denied(() => rpc('rihla_join_trip', [invitation.token]), 'P0001')
  await denied(() => rpc('rihla_join_trip', [invitation.code]), 'P0001')
  assert.equal((await rpc('rihla_join_trip', [replacement.code])).trip.member_count, 2)
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
  await denied(() => rpc('rihla_join_trip', [invitation.code]), 'P0001')
  await role(BOB)
  assert.equal((await rpc('rihla_get_trip', [created.id])).member_count, 2)
})

test('expired invitations cannot add a member', async () => {
  const { created, invitation } = await invitedTrip()
  await root()
  await db.query("update public.trip_invitations set created_at = now() - interval '8 days', expires_at = now() - interval '1 day' where trip_id = $1", [created.id])
  await role(BOB)
  await denied(() => rpc('rihla_join_trip', [invitation.token]), 'P0001')
  await denied(() => rpc('rihla_join_trip', [invitation.code]), 'P0001')
  assert.deepEqual(await rpc('rihla_list_trips'), [])
})

test('invalid invitation input cannot reveal a trip or add membership', async () => {
  const { invitation } = await invitedTrip()
  await role(BOB)
  const unusedCode = invitation.code === '000000' ? '000001' : '000000'
  for (const token of ['bad', '', 'a'.repeat(64), unusedCode]) await denied(() => rpc('rihla_join_trip', [token]), 'P0001')
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

// --- Sprint 2: group conflicts and generation inputs ---
const conflicts = (id) => rpc('rihla_get_group_conflicts', [id])
const generationInputs = (id, admin) => rpc('rihla_trip_generation_inputs', [id, admin])
const member = (extra = {}) => ({ ...inputs, destinations: { value: '', importance: 'Flexible' }, flights: { value: '', importance: 'Flexible' }, ...extra })
const essential = (value) => ({ value, importance: 'Essential' })

async function twoMembers(alice = member(), bob = member()) {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id, alice)
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, bob)
  return created.id
}
async function asServiceRole() {
  await db.exec('set local role service_role')
  await db.query("select set_config('request.jwt.claims', '', true)")
}

test('a clear group has no conflicts and can generate', async () => {
  const id = await twoMembers()
  assert.deepEqual(await conflicts(id), { conflicts: [], own_review: [], can_generate: true })
})

test('conflicts report readiness and dates by category before other checks', async () => {
  const created = await trip()
  assert.deepEqual((await conflicts(created.id)).conflicts, ['readiness', 'dates'])
  const id = await twoMembers(member(), member({ available_start: '2026-12-01', available_end: '2026-12-05' }))
  const report = await conflicts(id)
  assert.deepEqual(report.conflicts, ['dates'])
  assert.equal(report.can_generate, false)
})

test('clearly different Essential countries conflict; only members with an Essential get the notice', async () => {
  const id = await twoMembers(member({ destinations: essential('Turkey') }), member({ destinations: essential('اليابان') }))
  const bob = await conflicts(id)
  assert.deepEqual(bob, { conflicts: ['destinations'], own_review: ['destinations'], can_generate: false })
  const body = JSON.stringify(bob)
  for (const secret of ['Turkey', 'اليابان', ALICE, BOB, 'Alice', '4500']) assert.ok(!body.includes(secret))
})

test('a member without an Essential sees the conflict but no review notice', async () => {
  const { created, invitation } = await invitedTrip()
  await savePreferences(created.id, member({ destinations: essential('Turkey') }))
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id, member({ destinations: essential('Japan') }))
  await role(CAROL)
  await rpc('rihla_join_trip', [invitation.token])
  await savePreferences(created.id)
  await savePreferences(created.id, member())
  assert.deepEqual(await conflicts(created.id), { conflicts: ['destinations'], own_review: [], can_generate: false })
})

test('overlapping or doubtful Essential destinations do not stop at this check', async () => {
  for (const [first, second] of [['Turkey or Egypt', 'مصر'], ['Istanbul', 'Turkey'], ['Somewhere warm', 'Japan'], ['Turkey', 'Türkiye']]) {
    await db.exec('savepoint pair')
    const id = await twoMembers(member({ destinations: essential(first) }), member({ destinations: essential(second) }))
    assert.deepEqual((await conflicts(id)).conflicts, [], `${first} / ${second}`)
    await root()
    await db.exec('rollback to savepoint pair; release savepoint pair')
  }
})

test('budget conflict uses the fixed daily floor and gives no review notice', async () => {
  const six = { available_start: '2026-11-10', available_end: '2026-11-15' }
  const atFloor = await twoMembers(member({ ...six, max_budget_sar: '1500' }), member(six))
  assert.deepEqual((await conflicts(atFloor)).conflicts, [])
  await root()
  const below = await twoMembers(member({ ...six, max_budget_sar: '1499.99' }), member(six))
  await role(ALICE)
  assert.deepEqual(await conflicts(below), { conflicts: ['budget'], own_review: [], can_generate: false })
})

test('non-members cannot read group conflicts, and it needs no outside input', async () => {
  const id = await twoMembers()
  await role(CAROL)
  await denied(() => conflicts(id))
  const definition = (await db.query("select pg_get_function_identity_arguments('public.rihla_get_group_conflicts(uuid)'::regprocedure) as args")).rows[0]
  assert.equal(definition.args, 'p_trip_id uuid')
})

test('browser roles can never call the generation inputs function', async () => {
  const id = await twoMembers()
  await root()
  const privileges = (await db.query(`select
    has_function_privilege('authenticated', 'public.rihla_trip_generation_inputs(uuid,uuid)', 'execute') as signed_in,
    has_function_privilege('anon', 'public.rihla_trip_generation_inputs(uuid,uuid)', 'execute') as anonymous,
    has_function_privilege('service_role', 'public.rihla_trip_generation_inputs(uuid,uuid)', 'execute') as backend`)).rows[0]
  assert.deepEqual(privileges, { signed_in: false, anonymous: false, backend: true })

  await role(ALICE)
  await denied(() => generationInputs(id, ALICE))
  await role(BOB)
  await denied(() => generationInputs(id, ALICE))
  await db.exec('reset role; set local role anon')
  await denied(() => generationInputs(id, ALICE))
})

test('the backend role gets anonymous inputs for the administrator only', async () => {
  const id = await twoMembers(member({ destinations: essential('Egypt') }), member({ departure_city: 'Jeddah', max_budget_sar: '3000' }))
  await root()
  await asServiceRole()
  const result = await generationInputs(id, ALICE)

  assert.equal(result.trip_id, id)
  assert.equal(result.shared_start, '2026-11-10')
  assert.deepEqual(result.members.map((item) => item.label), ['Member 1', 'Member 2'])
  assert.deepEqual(result.members.map((item) => item.departure_city).sort(), ['Jeddah', 'Riyadh'])
  const body = JSON.stringify(result)
  for (const identity of [ALICE, BOB, 'Alice', 'Bob', 'user_id', 'alice@example.test']) assert.ok(!body.includes(identity))
  assert.deepEqual(Object.keys(result.members[0]).sort(), ['accommodation', 'departure_city', 'destinations', 'flights', 'interests', 'label', 'max_budget_sar'])

  await denied(() => generationInputs(id, BOB))
  await denied(() => generationInputs(id, CAROL))
  await denied(() => generationInputs(id, null))
})

test('generation inputs refuse an unready group or unavailable dates', async () => {
  const created = await trip()
  await savePreferences(created.id, member())
  const invitation = await rpc('rihla_issue_invitation', [created.id])
  await role(BOB)
  await rpc('rihla_join_trip', [invitation.token])
  await root()
  await asServiceRole()
  await denied(() => generationInputs(created.id, ALICE), 'P0001')
  await root()
  await role(BOB)
  await savePreferences(created.id, member({ available_start: '2026-12-01', available_end: '2026-12-05' }))
  await root()
  await asServiceRole()
  await denied(() => generationInputs(created.id, ALICE), 'P0001')
})

// --- Sprint 2: stored proposals ---
function storedProposal(tripId, option = 1) {
  const fare = (sourceId) => ({ value: 'Mock Air', status: 'Estimated', evidence: [{ source_id: sourceId, quote: 'A quote.' }] })
  return {
    trip_id: tripId, option_number: option, title: `Option ${option}`, destination: 'Cairo', cities: [],
    flights: [{ origin: 'Riyadh', airline: fare(1), legs: [] }, { origin: 'Jeddah', airline: fare(2), legs: [] }],
    sources: [
      { id: 1, title: 'Riyadh fares', url: 'https://example.com/riyadh' },
      { id: 2, title: 'Jeddah fares', url: 'https://example.com/jeddah' },
    ],
  }
}
const begin = (id) => rpc('rihla_begin_proposal_generation', [id])
const finish = (id) => rpc('rihla_end_proposal_generation', [id])
const saveArgs = (id, admin, version, hash, complete, list) => [id, admin, version, hash, complete, JSON.stringify(list)]
async function saveAll(id, version = 1, hash = 'hash-a', complete = true, list = [storedProposal(id)], admin = ALICE) {
  await asServiceRole()
  const result = await rpc('rihla_save_proposals', saveArgs(id, admin, version, hash, complete, list))
  await role(ALICE)
  return result
}
const hasSaved = (id, hash = 'hash-a', hours = 24) => rpc('rihla_has_saved_proposals', [id, hash, hours])
const proposals = (id) => rpc('rihla_get_proposals', [id])

async function savedTrip() {
  const id = await twoMembers(member(), member({ departure_city: 'Jeddah' }))
  await role(ALICE)
  await begin(id)
  await saveAll(id)
  return id
}

test('browser roles have no direct access to proposal tables', async () => {
  const id = await savedTrip()
  const rows = (await db.query("select relname, relrowsecurity from pg_class where oid in ('public.proposals'::regclass, 'public.proposal_generations'::regclass)")).rows
  assert.ok(rows.length === 2 && rows.every((row) => row.relrowsecurity))
  for (const statement of ['select * from public.proposals', 'select input_hash from public.proposal_generations', `delete from public.proposals where trip_id = '${id}'`]) {
    await role(ALICE)
    await denied(() => db.query(statement))
    await db.exec('reset role; set local role anon')
    await denied(() => db.query(statement))
  }
})

test('each member receives only their own departure city and its sources', async () => {
  const id = await savedTrip()
  await role(ALICE)
  const alice = (await proposals(id)).proposals[0]
  assert.deepEqual(alice.flights.map((item) => item.origin), ['Riyadh'])
  assert.deepEqual(alice.sources.map((item) => item.id), [1])
  assert.ok(!JSON.stringify(alice).includes('Jeddah') && !JSON.stringify(alice).includes('jeddah'))
  await role(BOB)
  const bob = (await proposals(id)).proposals[0]
  assert.deepEqual(bob.flights.map((item) => item.origin), ['Jeddah'])
  assert.deepEqual(bob.sources.map((item) => item.id), [2])
})

test('the stored hash is never returned, and outsiders cannot read proposals', async () => {
  const id = await savedTrip()
  await role(ALICE)
  assert.ok(!JSON.stringify(await proposals(id)).includes('hash-a'))
  await role(CAROL)
  await denied(() => proposals(id))
})

test('only the administrator can begin, end, check or save a generation', async () => {
  const id = await twoMembers()
  await role(BOB)
  await denied(() => begin(id))
  await denied(() => finish(id))
  await denied(() => hasSaved(id))
  await role(CAROL)
  await denied(() => begin(id))
  await db.exec('reset role; set local role anon')
  await denied(() => begin(id))
})

test('a running generation blocks a second one until it ends or expires', async () => {
  const id = await twoMembers()
  await role(ALICE)
  assert.deepEqual(await begin(id), { started: true, version: 1 })
  assert.deepEqual(await begin(id), { started: false, version: null })
  await role(BOB)
  assert.equal((await proposals(id)).generating, true)
  await role(ALICE)
  await finish(id)
  assert.equal((await begin(id)).started, true)
  await root()
  await db.query("update public.proposal_generations set locked_until = now() - interval '1 second' where trip_id = $1", [id])
  await role(ALICE)
  assert.equal((await begin(id)).started, true)
})

test('saving needs the lock and the matching version, and replaces older proposals', async () => {
  const id = await twoMembers()
  await role(ALICE)
  await denied(() => saveAll(id), 'P0001')
  await begin(id)
  await denied(() => saveAll(id, 5), 'P0001')
  await saveAll(id, 1, 'hash-a', true, [storedProposal(id, 1), storedProposal(id, 2), storedProposal(id, 3)])
  assert.equal((await proposals(id)).proposals.length, 3)
  await denied(() => saveAll(id, 2), 'P0001')
  assert.deepEqual(await begin(id), { started: true, version: 2 })
  await saveAll(id, 2, 'hash-b', true, [storedProposal(id, 1)])
  const latest = await proposals(id)
  assert.equal(latest.version, 2)
  assert.equal(latest.proposals.length, 1)
  assert.equal(latest.generating, false)
})

test('saving rejects empty lists, another trip and private fields', async () => {
  const id = await twoMembers()
  const other = await trip()
  await role(ALICE)
  await begin(id)
  const invalid = [[], [storedProposal(other.id)], [{ ...storedProposal(id), max_budget_sar: '4000' }], [storedProposal(id), storedProposal(id, 2), storedProposal(id, 3), storedProposal(id, 1)]]
  for (const list of invalid) await denied(() => saveAll(id, 1, 'h', true, list), '23514')
  assert.deepEqual((await proposals(id)).proposals, [])
})

test('saved proposals are found only for the same hash, while fresh and complete', async () => {
  const id = await savedTrip()
  await role(ALICE)
  assert.equal(await hasSaved(id), true)
  assert.equal(await hasSaved(id, 'other-hash'), false)
  await root()
  await db.query("update public.proposal_generations set generated_at = now() - interval '25 hours' where trip_id = $1", [id])
  await role(ALICE)
  assert.equal(await hasSaved(id), false)
  await begin(id)
  await saveAll(id, 2, 'partial', false)
  assert.equal(await hasSaved(id, 'partial'), false)
  assert.equal((await proposals(id)).complete, false)
})

test('a trip with no proposals reads as empty', async () => {
  const id = await twoMembers()
  await role(BOB)
  const empty = await proposals(id)
  assert.equal(empty.version, null)
  assert.deepEqual(empty.proposals, [])
  assert.equal(empty.generating, false)
})

test('browser roles can never save proposals, not even the administrator', async () => {
  const id = await twoMembers()
  await role(ALICE)
  await begin(id)
  await root()
  const privileges = (await db.query(`select
    has_function_privilege('authenticated', 'public.rihla_save_proposals(uuid,uuid,integer,text,boolean,jsonb)', 'execute') as signed_in,
    has_function_privilege('anon', 'public.rihla_save_proposals(uuid,uuid,integer,text,boolean,jsonb)', 'execute') as anonymous,
    has_function_privilege('service_role', 'public.rihla_save_proposals(uuid,uuid,integer,text,boolean,jsonb)', 'execute') as backend`)).rows[0]
  assert.deepEqual(privileges, { signed_in: false, anonymous: false, backend: true })
  const args = saveArgs(id, ALICE, 1, 'forged', true, [storedProposal(id)])
  await role(ALICE)
  await denied(() => rpc('rihla_save_proposals', args))
  await db.exec('reset role; set local role anon')
  await denied(() => rpc('rihla_save_proposals', args))
  await role(ALICE)
  assert.deepEqual((await proposals(id)).proposals, [])
})

test('the backend role can save only for the trip administrator', async () => {
  const id = await twoMembers()
  await role(ALICE)
  await begin(id)
  await asServiceRole()
  for (const admin of [BOB, CAROL, null]) {
    await denied(() => rpc('rihla_save_proposals', saveArgs(id, admin, 1, 'h', true, [storedProposal(id)])))
  }
})

test('a member whose departure city changed is told proposals need regenerating', async () => {
  const id = await savedTrip()
  await role(BOB)
  assert.equal((await proposals(id)).needs_regeneration, false)
  await savePreferences(id, member({ departure_city: 'Dammam' }))
  const changed = await proposals(id)
  assert.equal(changed.needs_regeneration, true)
  assert.deepEqual(changed.proposals[0].flights, [])
  await role(ALICE)
  assert.equal((await proposals(id)).needs_regeneration, true)
})

test('needs_regeneration turns true when any member changes a preference or joins', async () => {
  const id = await savedTrip()
  await role(BOB)
  await savePreferences(id, member({ departure_city: 'Jeddah', max_budget_sar: '9000' }))
  assert.equal((await proposals(id)).needs_regeneration, true)
  await role(ALICE)
  const answer = await proposals(id)
  assert.equal(answer.needs_regeneration, true)
  assert.ok(!JSON.stringify(answer).includes('fingerprint'))

  await role(ALICE)
  await begin(id)
  await saveAll(id, 2)
  assert.equal((await proposals(id)).needs_regeneration, false)

  const invitation = await rpc('rihla_issue_invitation', [id])
  await role(CAROL)
  await rpc('rihla_join_trip', [invitation.token])
  await role(ALICE)
  assert.equal((await proposals(id)).needs_regeneration, true)
})

test('needs_regeneration stays false when a member saves the same preferences', async () => {
  const id = await savedTrip()
  await role(BOB)
  await savePreferences(id, member({ departure_city: 'Jeddah' }))
  assert.equal((await proposals(id)).needs_regeneration, false)
})

test('proposals saved before fingerprints keep the departure city check only', async () => {
  const id = await savedTrip()
  await root()
  await db.query('update public.proposal_generations set input_fingerprint = null where trip_id = $1', [id])
  await role(BOB)
  await savePreferences(id, member({ departure_city: 'Jeddah', max_budget_sar: '9000' }))
  assert.equal((await proposals(id)).needs_regeneration, false)
})

async function savedWithIds() {
  const id = await savedTrip()
  await root()
  const { rows } = await db.query('select id from public.proposals where trip_id = $1', [id])
  return { id, proposalId: rows[0].id }
}
const flightContext = (id, proposalId, user) => rpc('rihla_flight_context', [id, proposalId, user])
const saveRefresh = (id, proposalId, user, flights, status = null) => rpc('rihla_save_flight_refresh', [id, proposalId, user, JSON.stringify(flights), status])

test('running the proposals migration again changes nothing and keeps the data', async () => {
  const { id } = await savedWithIds()
  const before = (await db.query('select count(*)::int as saved from public.proposals where trip_id = $1', [id])).rows[0]
  await db.exec(await readFile(new URL('../migrations/20261102000100_ai_proposals.sql', import.meta.url), 'utf8'))
  await root()
  assert.deepEqual((await db.query('select count(*)::int as saved from public.proposals where trip_id = $1', [id])).rows[0], before)
  const open = (await db.query("select has_function_privilege('authenticated', 'public.rihla_save_proposals(uuid,uuid,integer,text,boolean,jsonb)', 'execute') as browser")).rows[0]
  assert.equal(open.browser, false)
})

test('browser roles cannot read the flight context or save a refresh', async () => {
  const { id, proposalId } = await savedWithIds()
  const privileges = (await db.query(`select
    has_function_privilege('authenticated', 'public.rihla_flight_context(uuid,uuid,uuid)', 'execute') as read_signed_in,
    has_function_privilege('anon', 'public.rihla_flight_context(uuid,uuid,uuid)', 'execute') as read_anonymous,
    has_function_privilege('service_role', 'public.rihla_flight_context(uuid,uuid,uuid)', 'execute') as read_backend,
    has_function_privilege('authenticated', 'public.rihla_save_flight_refresh(uuid,uuid,uuid,jsonb,text)', 'execute') as save_signed_in,
    has_function_privilege('anon', 'public.rihla_save_flight_refresh(uuid,uuid,uuid,jsonb,text)', 'execute') as save_anonymous,
    has_function_privilege('service_role', 'public.rihla_save_flight_refresh(uuid,uuid,uuid,jsonb,text)', 'execute') as save_backend`)).rows[0]
  assert.deepEqual(privileges, { read_signed_in: false, read_anonymous: false, read_backend: true, save_signed_in: false, save_anonymous: false, save_backend: true })
  await role(ALICE)
  await denied(() => flightContext(id, proposalId, ALICE))
  await denied(() => saveRefresh(id, proposalId, ALICE, { origin: 'Riyadh' }))
})

test('the flight context counts travellers from the caller city, members only', async () => {
  const { id, proposalId } = await savedWithIds()
  await asServiceRole()
  const riyadh = await flightContext(id, proposalId, ALICE)
  assert.equal(riyadh.city, 'Riyadh')
  assert.equal(riyadh.adults, 1)
  assert.ok(riyadh.ceiling)
  await denied(() => flightContext(id, proposalId, CAROL))
})

test('the flight context counts same-city members together, ignoring case', async () => {
  const id = await twoMembers(member({ departure_city: 'Riyadh' }), member({ departure_city: ' riyadh ' }))
  await role(ALICE)
  await begin(id)
  await saveAll(id)
  await root()
  const { rows } = await db.query('select id from public.proposals where trip_id = $1', [id])
  await asServiceRole()
  assert.equal((await flightContext(id, rows[0].id, BOB)).adults, 2)
})

test('the flight group answers only for members, and closes to browsers', async () => {
  const same = await twoMembers(member({ departure_city: 'Riyadh' }), member({ departure_city: ' riyadh ' }))
  const mixed = await twoMembers(member({ departure_city: 'Riyadh' }), member({ departure_city: 'Jeddah' }))
  await root()
  const privileges = (await db.query(`select
    has_function_privilege('authenticated', 'public.rihla_flight_group(uuid,uuid)', 'execute') as browser,
    has_function_privilege('service_role', 'public.rihla_flight_group(uuid,uuid)', 'execute') as backend`)).rows[0]
  assert.deepEqual(privileges, { browser: false, backend: true })
  await asServiceRole()
  assert.deepEqual(await rpc('rihla_flight_group', [same, BOB]), { all_same_city: true, members: 2 })
  assert.equal((await rpc('rihla_flight_group', [mixed, BOB])).all_same_city, false)
  await denied(() => rpc('rihla_flight_group', [same, CAROL]))
})

test('a refresh replaces only the caller city, and no other proposal data', async () => {
  const { id, proposalId } = await savedWithIds()
  await asServiceRole()
  await saveRefresh(id, proposalId, BOB, { origin: 'jeddah', marker: 'new' }, 'includes_unconfirmed')
  await root()
  const { data } = (await db.query('select data from public.proposals where id = $1', [proposalId])).rows[0]
  assert.deepEqual(data.flights.map((item) => item.marker ?? item.origin), ['Riyadh', 'new'])
  assert.equal(data.budget_status, 'includes_unconfirmed')
  assert.equal(data.title, 'Option 1')
})

test('a refresh cannot write another member city, bad status, outsider or missing proposal', async () => {
  const { id, proposalId } = await savedWithIds()
  await asServiceRole()
  await denied(() => saveRefresh(id, proposalId, BOB, { origin: 'Riyadh' }), '23514')
  await denied(() => saveRefresh(id, proposalId, BOB, { origin: 'Jeddah' }, 'free'), '23514')
  await denied(() => saveRefresh(id, proposalId, CAROL, { origin: 'Jeddah' }))
  await denied(() => saveRefresh(id, CAROL, BOB, { origin: 'Jeddah' }), 'P0001')
  await denied(() => flightContext(id, CAROL, BOB), 'P0001')
})

test('needs_regeneration is false with no proposals and ignores letter case', async () => {
  const id = await twoMembers()
  await role(BOB)
  assert.equal((await proposals(id)).needs_regeneration, false)
  await root()
  await role(ALICE)
  await begin(id)
  await saveAll(id)
  await savePreferences(id, member({ departure_city: ' riyadh ' }))
  assert.equal((await proposals(id)).needs_regeneration, false)
})

test('several destinations in one field are alternatives, in SQL too', async () => {
  const pairs = [['فرنسا، البحرين', 'البحرين', []], ['France, Bahrain', 'bahrain', []], ['فرنسا، البحرين', 'اليابان', ['destinations']]]
  for (const [first, second, expected] of pairs) {
    await db.exec('savepoint options')
    const id = await twoMembers(member({ destinations: essential(first) }), member({ destinations: essential(second) }))
    assert.deepEqual((await conflicts(id)).conflicts, expected, `${first} / ${second}`)
    await root()
    await db.exec('rollback to savepoint options; release savepoint options')
  }
})

test('one member listing several Essential destinations has no conflict alone', async () => {
  const id = await twoMembers(member({ destinations: essential('فرنسا، البحرين') }), member())
  assert.deepEqual((await conflicts(id)).conflicts, [])
})
