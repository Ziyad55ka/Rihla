import { useEffect, useState, type FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useAuth } from './AuthProvider'
import { StatusBadge } from './StatusBadge'
import { accountRequest, type Account, type Profile } from '../lib/accounts'
import { AuthForm } from './AuthForm'
import { supabase, supabaseConfiguration } from '../lib/supabase'

function message(error: unknown): string {
  return error instanceof TypeError ? 'Could not reach the backend. Check that it is running and allows this frontend address.'
    : error instanceof Error ? error.message : 'The request failed. Please try again.'
}

function SignedInAccount({ session }: { session: Session }) {
  const [verified, setVerified] = useState(false)
  const [database, setDatabase] = useState(false)
  const [checking, setChecking] = useState(true)
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    async function verify() {
      setChecking(true); setVerified(false); setDatabase(false); setError(''); setNotice('')
      try {
        const account = await accountRequest<Account>('/api/me', { signal: controller.signal })
        if (controller.signal.aborted) return
        if (account.id !== session.user.id) throw new Error('The verified account does not match your session. Please sign in again.')
        setVerified(true)
        const profile = await accountRequest<Profile | null>('/api/profile', { signal: controller.signal })
        if (controller.signal.aborted) return
        setDatabase(true)
        setDisplayName(profile?.display_name ?? '')
        setNotice(profile ? 'Your private profile was loaded.' : 'Account verified. Add your display name to save your profile.')
      } catch (err) {
        if (!controller.signal.aborted) setError(message(err))
      } finally {
        if (!controller.signal.aborted) setChecking(false)
      }
    }
    void verify()
    return () => controller.abort()
  }, [session.user.id, session.access_token, attempt])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const profile = await accountRequest<Profile>('/api/profile', { displayName })
      setDisplayName(profile.display_name); setNotice('Your private profile was saved.'); setDatabase(true)
    } catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }

  async function signOut() {
    if (!supabase) return
    setBusy(true); setError('')
    try {
      const { error: signOutError } = await supabase.auth.signOut({ scope: 'local' })
      if (signOutError) throw signOutError
    } catch { setError('Could not sign out. Please try again.') }
    finally { setBusy(false) }
  }

  return <div className="account-content">
    <div className="account-heading"><div><h3>Your account</h3><p className="account-email">{session.user.email}</p></div>
      <button className="secondary-button" type="button" onClick={() => void signOut()} disabled={busy}>Sign out</button></div>
    <div className="account-checks" role="status" aria-live="polite">
      <StatusBadge tone={verified ? 'success' : 'neutral'}>{verified ? 'Backend identity verified' : checking ? 'Verifying account…' : 'Identity unverified'}</StatusBadge>
      <StatusBadge tone={database ? 'success' : 'neutral'}>{database ? 'Profile database reachable' : 'Profile database unverified'}</StatusBadge>
    </div>
    <form className="account-form" onSubmit={(event) => void save(event)}>
      <label htmlFor="display-name">Display name</label>
      <input id="display-name" name="displayName" autoComplete="nickname" minLength={2} maxLength={80} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} disabled={!database || busy || checking} />
      <p className="form-hint">Your display name is visible to people in your trips. Only you can change it.</p>
      <div className="account-actions"><button className="primary-button" disabled={!database || busy || checking || displayName.trim().length < 2}>{busy ? 'Please wait…' : 'Save profile'}</button>
        <button className="secondary-button" type="button" disabled={checking || busy} onClick={() => setAttempt((value) => value + 1)}>Check again</button></div>
    </form>
    {error && <p className="form-error" role="alert">{error}</p>}
    {notice && <p className="form-notice" role="status">{notice}</p>}
  </div>
}

export function AccountPanel({ appearance = 'default' }: { appearance?: 'default' | 'auth' }) {
  const { session, loading, error: sessionError } = useAuth()
  const standalone = appearance === 'auth'
  return <section className={standalone ? 'auth-account-section' : 'account-section'} id="account" aria-label="Your Rihla account">
    {!standalone && <div className="section-heading"><div><p className="eyebrow">Start your journey</p><h2>Your Rihla account</h2></div></div>}
    <div className={standalone ? 'auth-account-container' : 'account-card'}>
      {loading ? <div className="auth-session-loading" role="status"><span className="auth-spinner" aria-hidden="true" /> Restoring your session…</div>
        : !supabase ? <div className="auth-configuration"><p className="auth-eyebrow">YOUR NEXT CHAPTER</p><h2>Almost ready.</h2><p>{supabaseConfiguration.message}</p></div>
        : session ? <SignedInAccount key={session.user.id} session={session} />
        : <AuthForm sessionError={sessionError} />}
    </div>
  </section>
}
