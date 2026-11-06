import { useState, type FormEvent } from 'react'
import { authErrorMessage, submitCredentials } from '../lib/auth'
import { supabase } from '../lib/supabase'
import { useLanguage } from '../lib/language'

function Arrow() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

function PasswordField({ id, label, value, onChange, newPassword, disabled, t }: {
  id: string; label: string; value: string; onChange: (value: string) => void; newPassword: boolean; disabled: boolean; t: (value: string) => string
}) {
  const [visible, setVisible] = useState(false)
  return <div className="auth-field">
    <label htmlFor={id}>{t(label)}</label>
    <div className="auth-password-wrap">
      <input id={id} name={id} type={visible ? 'text' : 'password'} autoComplete={newPassword ? 'new-password' : 'current-password'}
        minLength={newPassword ? 8 : 1} maxLength={128} required value={value} disabled={disabled}
        placeholder={t(label === 'Confirm password' ? 'One more time' : newPassword ? 'Create a strong password' : 'Enter your password')}
        onChange={(event) => onChange(event.target.value)} />
      <button className="password-toggle" type="button" aria-label={t(`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`)} aria-pressed={visible} disabled={disabled} onClick={() => setVisible((current) => !current)}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          {visible ? <><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.8 5.3A11 11 0 0 1 12 5c5.5 0 9 7 9 7a18 18 0 0 1-3 4M6.2 6.2A20 20 0 0 0 3 12s3.5 7 9 7a10 10 0 0 0 5-1.4" /></>
            : <><path d="M3 12s3.5-7 9-7 9 7 9 7-3.5 7-9 7-9-7-9-7Z" /><circle cx="12" cy="12" r="3" /></>}
        </svg>
      </button>
    </div>
  </div>
}

export function AuthForm({ sessionError = '', initialMode = 'signin' }: { sessionError?: string; initialMode?: 'signin' | 'signup' }) {
  const { t } = useLanguage()
  const [mode, setMode] = useState<'signin' | 'signup'>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const signingUp = mode === 'signup'

  function changeMode(next: 'signin' | 'signup') {
    if (next === mode || busy) return
    setMode(next); setError(''); setNotice(''); setPassword(''); setConfirmation('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase || busy) return
    setError(''); setNotice('')
    if (signingUp && password !== confirmation) { setError('The passwords do not match.'); return }
    setBusy(true)
    try {
      const result = await submitCredentials(supabase, mode, email, password, window.location.origin)
      setPassword(''); setConfirmation('')
      if (result === 'confirmation-required') {
        setMode('signin')
        setNotice('Check your inbox for a confirmation link before signing in. If this account already exists, use your existing password.')
      }
    } catch (err) { setError(authErrorMessage(err)) }
    finally { setBusy(false) }
  }

  return <div className="auth-form-view">
    <div className="auth-mode-switch" role="group" aria-label={t("Account access")}>
      <button type="button" aria-pressed={!signingUp} disabled={busy} onClick={() => changeMode('signin')}>{t('Login')}</button>
      <button type="button" aria-pressed={signingUp} disabled={busy} onClick={() => changeMode('signup')}>{t('Sign up')}</button>
    </div>

    <div className="auth-form-heading">
      <p className="auth-eyebrow">{t(signingUp ? 'A NEW ADVENTURE AWAITS' : 'PICK UP WHERE YOU LEFT OFF')}</p>
      <h2 id="account-title">{t(signingUp ? 'Your journey starts here.' : 'Welcome back.')}</h2>
      <p>{signingUp ? t("A few details, then you’re one step closer to your next trip.") : t("Your people. Your plans. All in one place.")}</p>
    </div>

    <form className="auth-form" onSubmit={(event) => void submit(event)} aria-labelledby="account-title" aria-busy={busy}>
      <div className="auth-field"><label htmlFor="account-email">{t('Email address')}</label>
        <input id="account-email" name="email" type="email" autoComplete="email" required maxLength={254} placeholder="you@example.com"
          value={email} disabled={busy} onChange={(event) => setEmail(event.target.value)} /></div>
      <PasswordField key={`password-${mode}`} id="account-password" label="Password" value={password} onChange={setPassword} newPassword={signingUp} disabled={busy} t={t} />
      {signingUp && <><p className="auth-password-hint">{t("At least 8 characters. Make it a password that’s just for you.")}</p>
        <PasswordField id="confirm-password" label="Confirm password" value={confirmation} onChange={setConfirmation} newPassword disabled={busy} t={t} />
        <p className="auth-confirmation-note">{t("We’ll send you an email to confirm your account.")}</p></>}
      {(error || sessionError) && <p className="auth-feedback auth-feedback--error" role="alert">{t(error || sessionError)}</p>}
      {notice && <p className="auth-feedback auth-feedback--success" role="status">{t(notice)}</p>}
      <button className="auth-submit" disabled={busy} type="submit">
        <span>{busy ? t(signingUp ? 'Creating your account…' : 'Signing you in…') : signingUp ? t("Create my account") : t("Let’s go")}</span>
        {busy ? <span className="auth-spinner" aria-hidden="true" /> : <Arrow />}
      </button>
    </form>

    <p className="auth-switch-prompt">{signingUp ? t("Already part of the journey?") : t("New adventures start with an account.")}<br />
      <button type="button" disabled={busy} onClick={() => changeMode(signingUp ? 'signin' : 'signup')}>{signingUp ? t("Sign in instead") : t("Join Rihla")} <span aria-hidden="true">↗</span></button>
    </p>
    <div className="auth-form-footer"><span className="auth-tiny-compass" aria-hidden="true">↗</span><span>{t("A little planning. A lot to look forward to.")}</span></div>
  </div>
}
