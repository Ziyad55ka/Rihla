// TEST ONLY: fictional Auth + RPC HTTP facade over ephemeral PostgreSQL.
// Never deployed or imported by the application. No real accounts or email.
import { createServer } from 'node:http'
import { createHmac } from 'node:crypto'
import { createFixtureDatabase, fixtureUsers } from './fixture.mjs'

const db = await createFixtureDatabase()
const sessions = new Map()
const rpcArguments = {
  rihla_list_trips: [], rihla_get_trip: ['p_trip_id'],
  rihla_create_trip: ['p_title', 'p_description'], rihla_join_trip: ['p_token'],
  rihla_get_invitation: ['p_trip_id'], rihla_issue_invitation: ['p_trip_id'],
  rihla_revoke_invitation: ['p_trip_id'],
  rihla_get_preferences: ['p_trip_id'],
  rihla_save_preferences: ['p_trip_id', 'p_preferences'],
  rihla_get_planning_status: ['p_trip_id'],
  rihla_check_trip_dates: ['p_trip_id', 'p_start', 'p_end'],
  rihla_get_group_conflicts: ['p_trip_id'],
  rihla_begin_proposal_generation: ['p_trip_id'], rihla_end_proposal_generation: ['p_trip_id'],
  rihla_has_saved_proposals: ['p_trip_id', 'p_input_hash', 'p_max_age_hours'],
  rihla_save_proposals: ['p_trip_id', 'p_version', 'p_input_hash', 'p_complete', 'p_proposals'],
  rihla_get_proposals: ['p_trip_id'],
}
let queue = Promise.resolve()
function account(user) {
  return { id: user.id, email: user.email, aud: 'authenticated', role: 'authenticated', is_anonymous: false,
    created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z', email_confirmed_at: '2026-10-16T00:00:00Z',
    app_metadata: { provider: 'email', providers: ['email'] }, user_metadata: {}, identities: [] }
}
function session(user) {
  const claims = { sub: user.id, email: user.email, role: 'authenticated', aud: 'authenticated', iss: 'http://127.0.0.1:54329/auth/v1', iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600 }
  const unsigned = [JSON.stringify({ alg: 'HS256', typ: 'JWT' }), JSON.stringify(claims)].map((part) => Buffer.from(part).toString('base64url')).join('.')
  const token = `${unsigned}.${createHmac('sha256', 'fictional-preview-signing-key').update(unsigned).digest('base64url')}`
  sessions.set(token, user)
  return { access_token: token, refresh_token: `preview-${user.id}`, expires_in: 3600, expires_at: claims.exp, token_type: 'bearer', user: account(user) }
}
const server = createServer(async (request, response) => {
  response.setHeader('Access-Control-Allow-Origin', 'http://localhost:5174')
  response.setHeader('Access-Control-Allow-Headers', 'authorization,apikey,content-type,x-client-info,x-supabase-api-version')
  response.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
  response.setHeader('Content-Type', 'application/json')
  response.setHeader('Cache-Control', 'no-store')
  const send = (status, value) => { response.writeHead(status); response.end(JSON.stringify(value)) }
  if (request.method === 'OPTIONS') { send(200, {}); return }
  const url = new URL(request.url, 'http://127.0.0.1:54329')
  let body = {}
  try { let text = ''; for await (const chunk of request) { text += chunk; if (text.length > 5000000) throw new Error('Body too large') } if (text) body = JSON.parse(text) }
  catch { send(400, {}); return }
  if (url.pathname === '/auth/v1/token') {
    const user = url.searchParams.get('grant_type') === 'refresh_token'
      ? fixtureUsers.find((value) => body.refresh_token === `preview-${value.id}`)
      : fixtureUsers.find((value) => value.email === body.email && body.password === 'PreviewOnly123!')
    if (!user) { send(400, { code: 'invalid_credentials', msg: 'Invalid preview credentials' }); return }
    send(200, session(user)); return
  }
  // Stands in for the backend's secret key. A fictional value with no real access.
  if (url.pathname === '/rest/v1/rpc/rihla_trip_generation_inputs') {
    if (request.headers.apikey !== 'sb_secret_local_preview') { send(401, { code: 'invalid_key' }); return }
    queue = queue.then(async () => {
      try {
        await db.exec('begin; set local role service_role')
        const result = await db.query('select public.rihla_trip_generation_inputs($1, $2) as result', [body.p_trip_id, body.p_admin_id])
        await db.exec('commit')
        send(200, result.rows[0].result)
      } catch (error) {
        await db.exec('rollback')
        send(error.code === '42501' ? 403 : 400, { code: error.code, message: error.message })
      }
    })
    return
  }
  const token = request.headers.authorization?.replace(/^Bearer /, '')
  const user = sessions.get(token)
  if (!user) { send(401, { code: 'invalid_jwt' }); return }
  if (url.pathname === '/auth/v1/user') { send(200, account(user)); return }
  if (url.pathname === '/auth/v1/logout') { sessions.delete(token); send(200, {}); return }
  const profileRequest = url.pathname === '/rest/v1/profiles'
  const rpc = url.pathname.replace('/rest/v1/rpc/', '')
  if (!profileRequest && !Object.hasOwn(rpcArguments, rpc)) { send(404, { code: 'PGRST202' }); return }
  const args = rpcArguments[rpc] ?? []
  if (!profileRequest && Object.keys(body).some((key) => !args.includes(key))) { send(400, {}); return }
  queue = queue.then(async () => {
    try {
      await db.exec('begin; set local role authenticated')
      await db.query("select set_config('request.jwt.claims', $1, true)", [JSON.stringify({ sub: user.id, role: 'authenticated' })])
      const result = profileRequest
        ? request.method === 'GET'
          ? await db.query('select id, display_name, created_at from public.profiles where id = $1', [user.id])
          : await db.query('insert into public.profiles(id, display_name) values ($1,$2) on conflict(id) do update set id = excluded.id, display_name = excluded.display_name returning id, display_name, created_at', [body.id, body.display_name])
        : await db.query(`select public.${rpc}(${args.map((_, index) => `$${index + 1}`).join(',')}) as result`, args.map((key) => body[key]))
      await db.exec('commit')
      send(200, profileRequest ? result.rows : result.rows[0].result)
    } catch (error) {
      await db.exec('rollback')
      send(error.code === '42501' ? 403 : 400, { code: error.code, message: error.message })
    }
  })
})
server.listen(54329, '127.0.0.1', () => process.stdout.write('Fictional preview server ready on 127.0.0.1:54329. No cloud database is used.\n'))
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => { void db.close().then(() => process.exit(0)) }))
