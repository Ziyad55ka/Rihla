import { describe, expect, it } from 'vitest'
import { readSupabaseConfiguration } from './supabase'

const projectUrl = 'https://example-project.supabase.co'
// Synthetic payloads test configuration handling only; these are not credentials.
const testJwt = (role: string) => `${btoa('{}')}.${btoa(JSON.stringify({ role }))}.test-signature`

describe('Supabase browser configuration', () => {
  it('runs without any Supabase credentials', () => {
    expect(readSupabaseConfiguration({}).state).toBe('not-configured')
    expect(readSupabaseConfiguration({ url: ' ', publishableKey: ' ' }).state).toBe('not-configured')
  })

  it('explains partial configuration', () => {
    expect(readSupabaseConfiguration({ url: projectUrl }).state).toBe('invalid')
    expect(readSupabaseConfiguration({ publishableKey: 'sb_publishable_example' }).state).toBe('invalid')
  })

  it('marks public configuration as present without claiming a live connection', () => {
    const config = readSupabaseConfiguration({ url: projectUrl, publishableKey: 'sb_publishable_example' })
    expect(config.state).toBe('configured')
    expect(config.message).toContain('check your identity and profile database access separately')
  })

  it('allows legacy anon keys and a local Supabase URL', () => {
    expect(readSupabaseConfiguration({ url: 'http://127.0.0.1:54321', publishableKey: testJwt('anon') }).state).toBe('configured')
  })

  it.each(['sb_secret_test-value', testJwt('service_role'), 'not-a-key', 'sb_publishable_'])('rejects a privileged or invalid key without exposing it', (key) => {
    const config = readSupabaseConfiguration({ url: projectUrl, publishableKey: key })
    expect(config.state).toBe('invalid')
    expect(config.message).not.toContain(key)
  })

  it.each(['not a URL', 'http://example-project.supabase.co', 'https://example.test/path', 'https://user:pass@example.test', 'https://example.test?key=secret'])('rejects an invalid project URL: %s', (url) => {
    expect(readSupabaseConfiguration({ url, publishableKey: 'sb_publishable_example' }).state).toBe('invalid')
  })
})
