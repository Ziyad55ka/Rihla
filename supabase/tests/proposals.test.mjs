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

before(async () => {
  db = await createFixtureDatabase()
  await db.exec('grant usage on schema public to service_role')
})
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

// US-13: the cost context, read only by the backend's secret key.
const costContext = (id, user) => rpc('rihla_cost_context', [id, user])

test('the cost context is closed to browsers and answers only for members', async () => {
  const id = await savedTrip()
  await root()
  const privileges = (await db.query(`select
    has_function_privilege('authenticated', 'public.rihla_cost_context(uuid,uuid)', 'execute') as browser,
    has_function_privilege('anon', 'public.rihla_cost_context(uuid,uuid)', 'execute') as anonymous,
    has_function_privilege('service_role', 'public.rihla_cost_context(uuid,uuid)', 'execute') as backend`)).rows[0]
  assert.deepEqual(privileges, { browser: false, anonymous: false, backend: true })
  await role(ALICE)
  await denied(() => costContext(id, ALICE))
  await asServiceRole()
  await denied(() => costContext(id, CAROL))
  await denied(() => costContext(id, null))
})

test('the cost context gives the caller own budget, city counts and every route', async () => {
  const id = await twoMembers(
    member({ departure_city: 'Riyadh', max_budget_sar: '4500.50' }),
    member({ departure_city: ' riyadh ', max_budget_sar: '9000' }),
  )
  await role(ALICE)
  await begin(id)
  await saveAll(id)
  await asServiceRole()
  const forAlice = await costContext(id, ALICE)
  assert.equal(forAlice.member_count, 2)
  assert.equal(forAlice.own_budget_sar, '4500.50')
  assert.deepEqual(forAlice.origins, [{ origin: 'riyadh', members: 2 }])
  assert.deepEqual(forAlice.proposals[0].flights.map((route) => route.origin), ['Riyadh', 'Jeddah'])
  // Each member gets their own budget, never another member's.
  assert.equal((await costContext(id, BOB)).own_budget_sar, '9000')
  assert.ok(!JSON.stringify(forAlice).includes('9000'))
})
