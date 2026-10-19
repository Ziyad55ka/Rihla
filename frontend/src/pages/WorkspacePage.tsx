import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../components/AuthProvider'
import { AccountPanel } from '../components/AccountPanel'
import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../lib/language'
import { CreateTripForm, JoinTripForm } from '../components/TripForms'
import { TripCard } from '../components/TripCard'
import { listTrips } from '../lib/trips'
import { navigate, type WorkspaceRoute } from '../lib/navigation'
import { supabase } from '../lib/supabase'
import type { TripDetail, TripSummary } from '../types/trips'
import { TripDetailPage } from './TripDetailPage'
import { PreferencesPage } from './PreferencesPage'
import '../workspace.css'

export function WorkspacePage({ route, initialInvitation, onInvitationHandled }: {
  route: WorkspaceRoute; initialInvitation: string | null; onInvitationHandled: () => void
}) {
  const { t } = useLanguage()
  const { session } = useAuth()
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState('')
  const mainRef = useRef<HTMLElement>(null)
  const selected = 'tripId' in route ? route.tripId : ''

  useEffect(() => { mainRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0) }, [route.page, selected])
  useEffect(() => {
    if (route.page !== 'trips') return
    const refresh = () => { if (document.visibilityState === 'visible') setAttempt((value) => value + 1) }
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [route.page])
  useEffect(() => {
    if (route.page !== 'trips') return
    const controller = new AbortController()
    setLoading(true); setError('')
    listTrips(controller.signal).then((value) => { if (!controller.signal.aborted) setTrips(value) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'We couldn’t load your trips.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [route.page, attempt])

  function openTrip(trip: TripDetail, message = '') { setNotice(message); navigate(`/trips/${trip.id}`) }
  function back() { setNotice(''); navigate('/trips') }
  async function signOut() {
    if (!supabase || signingOut) return
    setSigningOut(true); setActionError('')
    try {
      const { error: failed } = await supabase.auth.signOut({ scope: 'local' })
      if (failed) throw failed
      navigate('/', true)
    } catch { setActionError('Could not sign out. Please try again.') }
    finally { setSigningOut(false) }
  }

  return <div className="trip-workspace">
    <a className="auth-skip-link" href="#trip-main">{t('Skip to your trips')}</a>
    <header className="trip-header rihla-navbar"><Brand /><nav className="rihla-navbar-links" aria-label={t("Main navigation")}><button type="button" aria-current={route.page === 'account' ? undefined : 'page'} onClick={back}>{t('My trips')}</button><button type="button" aria-current={route.page === 'account' ? 'page' : undefined} onClick={() => navigate('/account')}>{t('Your account')}</button></nav><div className="rihla-navbar-actions"><button type="button" className="trip-sign-out rihla-navbar-action" disabled={signingOut} onClick={() => void signOut()}>{signingOut ? t('Signing out…') : t('Sign out')} <span aria-hidden="true">↗</span></button><LanguageSwitcher /></div></header>
    <main id="trip-main" className="trip-main" ref={mainRef} tabIndex={-1}>
      {actionError && <p className="trip-feedback trip-feedback--error" role="alert">{t(actionError)}</p>}
      {route.page === 'create' ? <CreateTripForm onBack={back} onCreated={(trip) => openTrip(trip, 'Your trip has been created. Invite your people to join.')} />
        : route.page === 'join' ? <JoinTripForm key={initialInvitation ?? 'manual-invitation'} initialInvitation={initialInvitation} onBack={() => { onInvitationHandled(); back() }} onJoined={(trip, already) => { onInvitationHandled(); openTrip(trip, already ? 'You’re already part of this trip. Welcome back.' : 'You’re in. Welcome to the group!') }} />
        : route.page === 'detail' ? <TripDetailPage key={selected} tripId={selected} notice={notice} onBack={back} onPreferences={() => { setNotice(''); navigate(`/trips/${selected}/preferences`) }} />
        : route.page === 'preferences' ? <PreferencesPage key={selected} tripId={selected} onBack={() => navigate(`/trips/${selected}`)} onSaved={() => { setNotice('Your preferences have been saved.'); navigate(`/trips/${selected}`) }} />
        : route.page === 'account' ? <div className="trip-account-page"><button className="trip-back" type="button" onClick={back}>← {t('Back to your trips')}</button><AccountPanel /></div>
        : <>
          <section className="trip-dashboard-hero"><div><p className="trip-eyebrow"><span className="workspace-live-dot" /> {t('YOUR SHARED TRAVEL WORKSPACE')}</p><h1>{t('A little planning.')}<br /><span>{t('A lot to look forward to.')}</span></h1><p className="trip-intro-copy">{t('Your people, your preferences, your next great escape.')}<br />{t('Let’s bring it all together.')}</p></div><div className="dashboard-actions"><button className="trip-primary" type="button" onClick={() => navigate('/trips/new')}>{t('Create a trip')} <span aria-hidden="true">↗</span></button><button className="trip-secondary" type="button" onClick={() => navigate('/trips/join')}>{t('Join a trip')} <span aria-hidden="true">+</span></button></div></section>
          <section className="trip-collection" aria-labelledby="trips-title"><div className="trip-collection-heading"><div><p className="trip-eyebrow">{t('A JOURNEY WORTH SHARING')}</p><h2 id="trips-title">{t('Your trips')} <span>{trips.length.toString().padStart(2, '0')}</span></h2></div><button className="trip-text-button" type="button" disabled={loading} onClick={() => setAttempt((value) => value + 1)}>{loading ? t('Checking…') : t('Refresh trips')} <span aria-hidden="true">↻</span></button></div>
            {error ? <div className="trip-state-panel"><span className="trip-state-icon" aria-hidden="true">↗</span><h3>{t("We couldn’t load your trips.")}</h3><p role="alert">{t(error)}</p><button className="trip-secondary" type="button" onClick={() => setAttempt((value) => value + 1)}>{t("Try again")}</button></div>
              : loading && trips.length === 0 ? <p className="trip-loading" role="status">{t("Finding your next adventure…")}</p>
                : trips.length === 0 ? <div className="trip-state-panel"><span className="trip-state-icon" aria-hidden="true">↗</span><p className="trip-eyebrow">{t("A BLANK PAGE. A WORLD OF POSSIBILITIES.")}</p><h3>{t("Where are we going next?")}</h3><p>{t("Create a trip for your people, or join one with an invitation.")}</p><button className="trip-primary" type="button" onClick={() => navigate('/trips/new')}>{t("Create your first trip")} <span aria-hidden="true">↗</span></button></div>
                  : <div className="trip-card-grid">{trips.map((trip, index) => <TripCard trip={trip} key={trip.id} index={index} revision={attempt} />)}</div>}
          </section>
          <aside className="dashboard-note"><span aria-hidden="true">✳</span><p>{t("A great trip starts with everyone.")}<br /><span>{t("Add your preferences, find your shared dates, and take the next step together.")}</span></p><span className="dashboard-note-label">{t("MADE FOR YOUR PEOPLE")}</span></aside>
        </>}
    </main>
    <footer className="trip-footer"><span>{t("Rihla — a journey worth sharing.")}</span><span>{session?.user.email && route.page === 'account' ? session.user.email : t("Plan together. Go further.")}</span></footer>
  </div>
}
