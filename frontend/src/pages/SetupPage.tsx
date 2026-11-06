import { useLanguage } from '../lib/language'
import { useEffect, useState } from 'react'
import { StatusBadge } from '../components/StatusBadge'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { AccountPanel } from '../components/AccountPanel'
import { API_BASE_URL, getBackendHealth } from '../lib/api'
import { supabaseConfiguration } from '../lib/supabase'
import type { BackendStatus } from '../types/api'
import { FlyIcon } from '../components/FlightIcons'

export function SetupPage() {
  const { t, locale } = useLanguage()
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
        <LanguageSwitcher />
        <a className="brand" href="#main" aria-label={t("Rihla home")}>
          <span className="brand-mark" aria-hidden="true">ر</span>
          <span>rihla<span className="brand-period">.</span></span>
        </a>
        <span className="workspace-label">{t("SWE 444 · Development")}</span>
      </header>

      <main id="main">
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow"><span aria-hidden="true" />{t("Sprint 01 / Accounts")}</p>
          <h1 id="page-title">{t("Every journey starts")}<br />{t("with a shared plan.")}</h1>
          <p className="intro-description">{t("A home for your group’s next adventure. Create your account and get ready to plan together.")}</p>
          <a className="foundation-label" href="#account"><span aria-hidden="true"><FlyIcon /></span> {t("Your account")}</a>
        </section>

        <AccountPanel />
        <section className="services" aria-labelledby="services-title">
          <div className="section-heading">
            <div><p className="eyebrow">{t("Connection checks")}</p><h2 id="services-title">{t("Your development workspace")}</h2></div>
            <span className="local-label">{t("Local environment")}</span>
          </div>

          <div className="service-grid">
            <article className="service-card">
              <div className="service-card-top"><span className="service-icon" aria-hidden="true">↔</span><span className="service-number">01</span></div>
              <h3>{t("Rihla backend")}</h3>
              <p className="service-description">{t("The FastAPI service will handle trip rules, validation, and permissions.")}</p>
              <div className="connection-result" role="status" aria-live="polite" aria-atomic="true">
                <StatusBadge tone={backend.state === 'connected' ? 'success' : backend.state === 'unavailable' ? 'warning' : 'neutral'}>
                  {backend.state === 'connected' ? t("Connected") : backend.state === 'unavailable' ? t("Unavailable") : t("Checking connection")}
                </StatusBadge>
                <p className="status-detail">{backend.state === 'connected'
                  ? t('Health check passed at {time}. Authentication and database access are separate checks.', { time: backend.checkedAt.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) })
                  : backend.state === 'unavailable' ? t(backend.message) : t("Requesting the backend health endpoint…")}</p>
              </div>
              <div className="card-footer"><code className="endpoint">{API_BASE_URL}</code><button type="button" onClick={recheck} disabled={backend.state === 'checking'}>{t("Check again")} <span aria-hidden="true">↻</span></button></div>
            </article>

            <article className="service-card">
              <div className="service-card-top"><span className="service-icon" aria-hidden="true">◇</span><span className="service-number">02</span></div>
              <h3>Supabase</h3>
              <p className="service-description">{t("User accounts and a PostgreSQL database for the group’s trip information.")}</p>
              <div className="connection-result">
                <StatusBadge tone={supabaseConfiguration.state === 'invalid' ? 'warning' : 'neutral'}>
                  {supabaseConfiguration.state === 'configured' ? t("Configured") : supabaseConfiguration.state === 'invalid' ? t("Check configuration") : t("Not configured")}
                </StatusBadge>
                <p className="status-detail">{t(supabaseConfiguration.message)}</p>
              </div>
              <div className="card-footer"><span className="footer-note">{t("Project URL + publishable key")}</span><span className="next-label">{t("Next step")} <span aria-hidden="true"><FlyIcon /></span></span></div>
            </article>
          </div>
        </section>

        <aside className="next-section" aria-labelledby="next-title"><span className="next-icon" aria-hidden="true">→</span><div><h2 id="next-title">{t("Next: plan together")}</h2><p>{t("Trips, invitations, preferences, and shared dates are the next Sprint 1 features.")}</p></div><span className="phase-label">{t("Accounts in progress")}</span></aside>
      </main>
      <footer className="site-footer"><span>{t("Rihla · Plan together. Travel together.")}</span><span>{t("SWE 444 course project")}</span></footer>
    </div>
  )
}
