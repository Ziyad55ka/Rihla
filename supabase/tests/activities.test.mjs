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

// --- US-11/12: per-member selections ---
async function tripWithActivities() {
  const id = await twoMembers(member(), member({ departure_city: 'Jeddah' }))
  await role(ALICE)
  await begin(id)
  const data = storedProposal(id)
  data.id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  data.cities = [{ activities: [{ id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' }] }]
  await saveAll(id, 1, 'hash-a', true, [data])
  return { trip: id, proposal: data.id, activity: data.cities[0].activities[0].id }
}
const getSelection = (p) => rpc('rihla_get_activity_selection', [p.trip, p.proposal])
const putSelection = (p, ids, version = 1) => rpc('rihla_set_activity_selection', [p.trip, p.proposal, version, ids])

const TOKEN = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const NEXT_TOKEN = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const claim = (p, user = ALICE, token = TOKEN, version = 1) => rpc('rihla_begin_activity_research', [p.trip, p.proposal, user, version, token])
const complete = (p, cities, sources = [], token = TOKEN) => rpc('rihla_finish_activity_research', [p.trip, p.proposal, ALICE, 1, token, JSON.stringify(cities), JSON.stringify(sources)])

test('research is backend-only, member checked, leased and cached', async () => {
  const p = await tripWithActivities()
  await denied(() => claim(p))
  await asServiceRole()
  await denied(() => claim(p, CAROL))
  await denied(() => claim(p, ALICE, TOKEN, 9), 'P0001')
  assert.equal((await claim(p)).started, true)
  assert.equal((await claim(p, BOB, NEXT_TOKEN)).started, false)
  await root()
  await db.query("update public.proposals set data=jsonb_set(data,'{cities,0,order}','1') where trip_id=$1", [p.trip])
  await asServiceRole()
  await denied(() => complete(p, [{ order: 1, activities: [] }], [], NEXT_TOKEN), 'P0001')
  await complete(p, [{ order: 1, activities: [] }])
  assert.deepEqual(await claim(p), { ready: true, started: false })
  await role(ALICE)
  const read = (await proposals(p.trip)).proposals[0]
  assert.equal(read.activity_research_status, 'ready')
  assert.equal(read.flights[0].origin, 'Riyadh')
})

test('cost aggregate adds each member choices without revealing them', async () => {
  const p = await tripWithActivities()
  await root()
  await db.query("update public.proposals set data=jsonb_set(data,'{cities,0,activities,0,price_per_person}', $2::jsonb) where trip_id=$1", [p.trip, JSON.stringify({ amount_sar: '65.50', status: 'Estimated', evidence: [] })])
  await role(BOB)
  await putSelection(p, [p.activity])
  await role(ALICE)
  const totals = () => rpc('rihla_get_activity_costs', [p.trip])
  let data = (await totals()).proposals[0]
  assert.deepEqual(data.activity_ids, [])
  assert.equal(data.group_cost.amount_sar, '65.50')
  await putSelection(p, [p.activity])
  data = (await totals()).proposals[0]
  assert.deepEqual(data.activity_ids, [p.activity])
  assert.equal(data.group_cost.amount_sar, '131.00')
  assert.equal(data.group_cost.partial, false)
  await role(CAROL)
  await denied(totals)
})

test('unknown prices are partial; no choices have a zero total', async () => {
  const p = await tripWithActivities()
  const total = async () => (await rpc('rihla_get_activity_costs', [p.trip])).proposals[0].group_cost
  assert.equal((await total()).amount_sar, '0')
  assert.equal((await total()).partial, false)
  await putSelection(p, [p.activity])
  assert.equal((await total()).partial, true)
  await putSelection(p, [])
  assert.equal((await total()).partial, false)
})

test('research retries after backoff; stale proposals cannot be patched', async () => {
  const p = await tripWithActivities()
  await asServiceRole()
  await claim(p)
  await rpc('rihla_fail_activity_research', [TOKEN])
  assert.equal((await claim(p, ALICE, NEXT_TOKEN)).started, false)
  await root()
  await db.exec("update public.activity_research_jobs set locked_until=now()-interval '1 second'")
  await asServiceRole()
  assert.equal((await claim(p, ALICE, NEXT_TOKEN)).started, true)
  await role(ALICE)
  await begin(p.trip)
  await saveAll(p.trip, 2)
  await asServiceRole()
  await denied(() => complete(p, []), 'P0001')
})

test('activity choices persist and are private even from the trip administrator', async () => {
  const p = await tripWithActivities()
  await role(BOB)
  assert.deepEqual((await getSelection(p)).activity_ids, [])
  await putSelection(p, [p.activity])
  assert.deepEqual((await getSelection(p)).activity_ids, [p.activity])
  await role(ALICE)
  assert.deepEqual((await getSelection(p)).activity_ids, [])
  await putSelection(p, [])
  await role(BOB)
  assert.deepEqual((await getSelection(p)).activity_ids, [p.activity])
  await putSelection(p, [])
  assert.deepEqual((await getSelection(p)).activity_ids, [])
})

test('activity RPCs reject outsiders, forged ids, duplicates and old versions', async () => {
  const p = await tripWithActivities()
  await denied(() => putSelection(p, [ALICE]), '23514')
  await denied(() => putSelection(p, [p.activity, p.activity]), '23514')
  await denied(() => putSelection(p, [p.activity], 2), 'P0001')
  await denied(() => putSelection(p, null), '23514')
  const other = await trip()
  await denied(() => getSelection({ ...p, trip: other.id }), 'P0001')
  await role(CAROL)
  await denied(() => getSelection(p))
  await denied(() => putSelection(p, []))
  await db.exec('reset role; set local role anon')
  await denied(() => getSelection(p))
})

test('selections cannot be written directly and regeneration removes stale choices', async () => {
  const p = await tripWithActivities()
  await putSelection(p, [p.activity])
  await denied(() => db.query('select * from public.activity_selections'))
  await begin(p.trip)
  await saveAll(p.trip, 2)
  await denied(() => getSelection(p), 'P0001')
  await denied(() => putSelection(p, [p.activity]), 'P0001')
  await root()
  assert.equal((await db.query('select count(*)::int as n from public.activity_selections')).rows[0].n, 0)
})

