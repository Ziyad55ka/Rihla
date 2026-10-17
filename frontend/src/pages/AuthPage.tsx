import { useAuth } from '../components/AuthProvider'
import { AuthForm } from '../components/AuthForm'
import { Brand } from '../components/Brand'
import { supabase, supabaseConfiguration } from '../lib/supabase'
import '../auth.css'

interface AuthPageProps {
  hasPendingInvitation?: boolean
  initialMode?: 'signin' | 'signup'
  onBack?: () => void
  intent?: 'create' | 'join' | null
}

export function AuthPage({ hasPendingInvitation = false, initialMode = 'signin', onBack, intent = null }: AuthPageProps) {
  const { loading, error } = useAuth()
  return <div className="auth-page">
    <a className="auth-skip-link" href="#account">Skip to account form</a>
    <header className="auth-header rihla-navbar">
      <Brand />
      <span className="auth-header-note">A JOURNEY WORTH SHARING.</span>
      {onBack && <button className="auth-back rihla-navbar-action" type="button" onClick={onBack}><span aria-hidden="true">←</span> Back to home</button>}
    </header>

    <main id="main" className="auth-layout">
      <section className="auth-story" aria-labelledby="auth-story-title">
        <p className="auth-story-label"><span aria-hidden="true" /> MAKE SPACE FOR YOUR NEXT ADVENTURE</p>
        <h1 id="auth-story-title">Life’s better<br />when you<br /><span>go together.</span></h1>
        <p className="auth-story-description">A place for your people, your possibilities,<br />and a plan that works for everyone.</p>
        <div className="auth-story-route" aria-hidden="true">
          <svg viewBox="0 0 440 150" fill="none"><path d="M8 100h85c24 0 24-66 48-66h105c24 0 24 66 48 66h136" stroke="currentColor" /><path d="M8 116h92c28 0 28-66 48-66h91c23 0 23 66 55 66h136" stroke="currentColor" opacity=".35" /><circle cx="8" cy="100" r="5" fill="currentColor" /><circle cx="430" cy="100" r="5" fill="currentColor" /><circle cx="197" cy="34" r="14" fill="#e9e9df" stroke="currentColor" /><path d="m191 34 4 4 8-8" stroke="currentColor" strokeWidth="1.5" /></svg>
          <span>Your people.</span><span>Your common ground.</span><span>Your next chapter.</span>
        </div>
      </section>
      <section id="account" className="auth-account-column" aria-label="Your Rihla account">
        {(hasPendingInvitation || intent) && <p className="auth-invitation-note" role="status">{hasPendingInvitation
          ? 'Your group is waiting. Login or sign up to continue with your invitation.'
          : `Login or sign up, then ${intent === 'create' ? 'create your trip' : 'join your group with an invitation'}.`}</p>}
        <div className="auth-account-container">
          {loading ? <div className="auth-session-loading" role="status"><span className="auth-spinner" aria-hidden="true" /> Restoring your session…</div>
            : !supabase ? <div className="auth-configuration"><p className="auth-eyebrow">YOUR NEXT CHAPTER</p><h2>Almost ready.</h2><p>{supabaseConfiguration.message}</p></div>
            : <AuthForm key={initialMode} initialMode={initialMode} sessionError={error} />}
        </div>
      </section>
    </main>

    <footer className="auth-page-footer"><span>Good company. Great journeys.</span><span>رحلة <span aria-hidden="true">/</span> A journey worth sharing.</span></footer>
  </div>
}
