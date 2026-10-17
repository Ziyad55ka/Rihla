import { AccountPanel } from '../components/AccountPanel'
import { Brand } from '../components/Brand'
import '../auth.css'

export function AuthPage({ hasPendingInvitation = false }: { hasPendingInvitation?: boolean }) {
  return <div className="auth-page">
    <a className="auth-skip-link" href="#account">Skip to account form</a>
    <header className="auth-header">
      <Brand />
      <span className="auth-header-note">GOOD COMPANY. GREAT JOURNEYS.</span>
      <span className="auth-header-tag">Made to go together <span aria-hidden="true">↗</span></span>
    </header>

    <main id="main" className="auth-layout">
      <section className="auth-story" aria-labelledby="auth-story-title">
        <p className="auth-story-label"><span aria-hidden="true" /> LESS GROUP CHAT. MORE GROUP TRIPS.</p>
        <h1 id="auth-story-title">Great trips.<br />Better<br /><span>company.</span></h1>
        <p className="auth-story-description">Bring your people. Find your dates.<br />Make the next adventure happen.</p>
        <figure className="auth-travel-figure">
          <img src="/images/rihla-travel-friends.jpg" alt="" width="1536" height="1024" fetchPriority="high" />
          <figcaption><span>GO SOMEWHERE GOOD.</span><span aria-hidden="true">↗</span></figcaption>
        </figure>
      </section>
      <div className="auth-account-column">
        {hasPendingInvitation && <p className="auth-invitation-note" role="status">You’ve been invited. Sign in or create an account, then join your group.</p>}
        <AccountPanel appearance="auth" />
      </div>
    </main>

    <footer className="auth-page-footer"><span>Plan together. Travel together.</span><span>رحلة <span aria-hidden="true">/</span> A journey worth sharing.</span></footer>
  </div>
}
