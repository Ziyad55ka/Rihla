import { useEffect, useState } from 'react'
import { StatusBadge } from '../components/StatusBadge'
import { AccountPanel } from '../components/AccountPanel'
import { API_BASE_URL, getBackendHealth } from '../lib/api'
import { supabaseConfiguration } from '../lib/supabase'
import type { BackendStatus } from '../types/api'

export function SetupPage() {
  const [attempt, setAttempt] = useState(0)
  const [backend, setBackend] = useState<BackendStatus>({ state: 'checking' })

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    getBackendHealth({ signal: controller.signal })
      .then(() => {
        if (!disposed) setBackend({ state: 'connected', checkedAt: new Date() })
      })
      .catch((error: unknown) => {
        if (!disposed) setBackend({
          state: 'unavailable',
          message: error instanceof TypeError
            ? 'Could not reach the backend. Check that it is running and allows this frontend address.'
            : error instanceof Error ? error.message : 'Could not check the backend.',
        })
      })
    return () => {
      disposed = true
      controller.abort()
    }
  }, [attempt])

  const recheck = () => {
    setBackend({ state: 'checking' })
    setAttempt((value) => value + 1)
  }

  return (
    <div className="workspace">
      <header className="site-header">
        <a className="brand" href="#main" aria-label="Rihla home">
          <span className="brand-mark" aria-hidden="true">ر</span>
          <span>rihla<span className="brand-period">.</span></span>
        </a>
        <span className="workspace-label">SWE 444 · Development</span>
      </header>

      <main id="main">
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow"><span aria-hidden="true" />Sprint 01 / Accounts</p>
          <h1 id="page-title">Every journey starts<br />with a shared plan.</h1>
          <p className="intro-description">A home for your group’s next adventure. Create your account and get ready to plan together.</p>
          <a className="foundation-label" href="#account"><span aria-hidden="true">↗</span> Your account</a>
        </section>

        <AccountPanel />
        <section className="services" aria-labelledby="services-title">
          <div className="section-heading">
            <div><p className="eyebrow">Connection checks</p><h2 id="services-title">Your development workspace</h2></div>
            <span className="local-label">Local environment</span>
          </div>

          <div className="service-grid">
            <article className="service-card">
              <div className="service-card-top"><span className="service-icon" aria-hidden="true">↔</span><span className="service-number">01</span></div>
              <h3>Rihla backend</h3>
              <p className="service-description">The FastAPI service will handle trip rules, validation, and permissions.</p>
              <div className="connection-result" role="status" aria-live="polite" aria-atomic="true">
                <StatusBadge tone={backend.state === 'connected' ? 'success' : backend.state === 'unavailable' ? 'warning' : 'neutral'}>
                  {backend.state === 'connected' ? 'Connected' : backend.state === 'unavailable' ? 'Unavailable' : 'Checking connection'}
                </StatusBadge>
                <p className="status-detail">{backend.state === 'connected'
                  ? `Health check passed at ${backend.checkedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}. Authentication and database access are separate checks.`
                  : backend.state === 'unavailable' ? backend.message : 'Requesting the backend health endpoint…'}</p>
              </div>
              <div className="card-footer"><code className="endpoint">{API_BASE_URL}</code><button type="button" onClick={recheck} disabled={backend.state === 'checking'}>Check again <span aria-hidden="true">↻</span></button></div>
            </article>

            <article className="service-card">
              <div className="service-card-top"><span className="service-icon" aria-hidden="true">◇</span><span className="service-number">02</span></div>
              <h3>Supabase</h3>
              <p className="service-description">User accounts and a PostgreSQL database for the group’s trip information.</p>
              <div className="connection-result">
                <StatusBadge tone={supabaseConfiguration.state === 'invalid' ? 'warning' : 'neutral'}>
                  {supabaseConfiguration.state === 'configured' ? 'Configured' : supabaseConfiguration.state === 'invalid' ? 'Check configuration' : 'Not configured'}
                </StatusBadge>
                <p className="status-detail">{supabaseConfiguration.message}</p>
              </div>
              <div className="card-footer"><span className="footer-note">Project URL + publishable key</span><span className="next-label">Next step <span aria-hidden="true">↗</span></span></div>
            </article>
          </div>
        </section>

        <aside className="next-section" aria-labelledby="next-title"><span className="next-icon" aria-hidden="true">→</span><div><h2 id="next-title">Next: plan together</h2><p>Trips, invitations, preferences, and shared dates are the next Sprint 1 features.</p></div><span className="phase-label">Accounts in progress</span></aside>
      </main>
      <footer className="site-footer"><span>Rihla · Plan together. Travel together.</span><span>SWE 444 course project</span></footer>
    </div>
  )
}
