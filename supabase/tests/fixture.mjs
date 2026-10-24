import { PGlite } from '@electric-sql/pglite'
import { readFile, readdir } from 'node:fs/promises'

export const fixtureUsers = [
  { id: '11111111-1111-4111-8111-111111111111', name: 'Alice', email: 'alice@example.test' },
  { id: '22222222-2222-4222-8222-222222222222', name: 'Bob', email: 'bob@example.test' },
  { id: '33333333-3333-4333-8333-333333333333', name: 'Carol', email: 'carol@example.test' },
]

export async function createFixtureDatabase({ throughMigration } = {}) {
  const db = new PGlite()
  await db.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create schema auth;
    grant usage on schema auth, public to anon, authenticated;
    create table auth.users(id uuid primary key, email text);
    create function auth.jwt() returns jsonb language sql stable as
      $$select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb$$;
    create function auth.uid() returns uuid language sql stable as
      $$select (auth.jwt()->>'sub')::uuid$$;
  `)
  const migrations = (await readdir(new URL('../migrations/', import.meta.url))).filter((name) => name.endsWith('.sql')).sort()
  for (const name of migrations) {
    if (!throughMigration || name <= throughMigration) await db.exec(await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8'))
  }
  for (const user of fixtureUsers) {
    await db.query('insert into auth.users(id, email) values ($1, $2)', [user.id, user.email])
    await db.query('insert into public.profiles(id, display_name) values ($1, $2)', [user.id, user.name])
  }
  return db
}
