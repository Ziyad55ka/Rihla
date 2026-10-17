import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../components/AuthProvider'
import { AccountPanel } from '../components/AccountPanel'
import { Brand } from '../components/Brand'
import { CreateTripForm, JoinTripForm } from '../components/TripForms'
import { listTrips } from '../lib/trips'
import { supabase } from '../lib/supabase'
import type { TripDetail, TripSummary } from '../types/trips'
import { TripDetailPage } from './TripDetailPage'
import '../workspace.css'

type View = 'trips' | 'create' | 'join' | 'detail' | 'account'

export function WorkspacePage({ initialInvitation, onInvitationHandled }: { initialInvitation: string | null; onInvitationHandled: () => void }) {
  const { session } = useAuth()
  const [view, setView] = useState<View>(initialInvitation ? 'join' : 'trips')
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => { if (initialInvitation) setView('join') }, [initialInvitation])
  useEffect(() => { mainRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0) }, [view])

  useEffect(() => {
    if (view !== 'trips') return
    const controller = new AbortController()
    setLoading(true); setError('')
    listTrips(controller.signal).then((value) => { if (!controller.signal.aborted) setTrips(value) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load your trips.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [view, attempt])

  function openTrip(trip: TripDetail | TripSummary, message = '') { setSelected(trip.id); setNotice(message); setView('detail') }
  function back() { setNotice(''); setView('trips'); setAttempt((value) => value + 1) }
  async function signOut() {
    if (!supabase || signingOut) return
    setSigningOut(true); setActionError('')
    try { const { error: failed } = await supabase.auth.signOut({ scope: 'local' }); if (failed) throw failed }
    catch { setActionError('Could not sign out. Please try again.') }
    finally { setSigningOut(false) }
  }

  return <div className="trip-workspace">
    <a className="auth-skip-link" href="#trip-main">Skip to your trips</a>
    <header className="trip-header"><Brand /><nav aria-label="Main navigation"><button type="button" aria-current={view === 'account' ? undefined : 'page'} onClick={back}>My trips</button><button type="button" aria-current={view === 'account' ? 'page' : undefined} onClick={() => setView('account')}>Your account</button></nav><button type="button" className="trip-sign-out" disabled={signingOut} onClick={() => void signOut()}>{signingOut ? 'Signing out…' : 'Sign out'} <span aria-hidden="true">↗</span></button></header>
    <main id="trip-main" className="trip-main" ref={mainRef} tabIndex={-1}>
      {actionError && <p className="trip-feedback trip-feedback--error" role="alert">{actionError}</p>}
      {view === 'create' ? <CreateTripForm onBack={back} onCreated={(trip) => openTrip(trip, 'Your trip has been created. Invite your people to join.')} />
        : view === 'join' ? <JoinTripForm key={initialInvitation ?? 'manual-invitation'} initialInvitation={initialInvitation} onBack={() => { onInvitationHandled(); back() }} onJoined={(trip, already) => { onInvitationHandled(); openTrip(trip, already ? 'You’re already part of this trip. Welcome back.' : 'You’re in. Welcome to the group!') }} />
        : view === 'detail' ? <TripDetailPage key={selected} tripId={selected} notice={notice} onBack={back} />
        : view === 'account' ? <div className="trip-account-page"><button className="trip-back" type="button" onClick={back}>← Back to your trips</button><AccountPanel /></div>
        : <><section className="trip-dashboard-hero"><div><p className="trip-eyebrow">GOOD COMPANY. GREAT JOURNEYS.</p><h1>Your people.<br /><span>Your next trip.</span></h1><p className="trip-intro-copy">Less back-and-forth. More looking forward.<br />Bring your next group adventure together.</p><div className="trip-button-row"><button className="trip-primary" type="button" onClick={() => setView('create')}>Create a trip <span aria-hidden="true">↗</span></button><button className="trip-secondary" type="button" onClick={() => setView('join')}>Join a trip</button></div></div><figure><img src="/images/rihla-travel-friends.jpg" alt="" width="1536" height="1024" /><figcaption>THE BEST DESTINATION? TOGETHER. <span aria-hidden="true">↗</span></figcaption></figure></section>
          <section className="trip-collection" aria-labelledby="trips-title"><div className="trip-collection-heading"><h2 id="trips-title">Your trips {!loading && !error && <span>{trips.length.toString().padStart(2, '0')}</span>}</h2><span>Made for the memories ahead.</span></div>
            {loading ? <p className="trip-loading" role="status">Finding your next adventure…</p>
              : error ? <div className="trip-state-panel"><span className="trip-state-icon" aria-hidden="true">↗</span><h3>We couldn’t load your trips.</h3><p role="alert">{error}</p><button className="trip-secondary" type="button" onClick={() => setAttempt((value) => value + 1)}>Try again</button></div>
              : trips.length === 0 ? <div className="trip-state-panel"><span className="trip-state-icon" aria-hidden="true">↗</span><p className="trip-eyebrow">A BLANK PAGE. A WORLD OF POSSIBILITIES.</p><h3>Where are we going next?</h3><p>Create a trip for your people, or join one with an invitation.</p><button className="trip-text-button" type="button" onClick={() => setView('create')}>Start your first trip <span aria-hidden="true">↗</span></button></div>
              : <div className="trip-card-grid">{trips.map((trip, index) => <button type="button" key={trip.id} className="trip-card" onClick={() => openTrip(trip)}><div className="trip-card-top"><span>{(index + 1).toString().padStart(2, '0')}</span><span className="trip-role">{trip.role === 'administrator' ? 'Administrator' : 'Member'}</span></div><h3>{trip.title}</h3><p>{trip.description || 'A journey worth sharing.'}</p><div className="trip-card-footer"><span>{trip.member_count} {trip.member_count === 1 ? 'person' : 'people'} in the group</span><span aria-hidden="true">↗</span></div></button>)}</div>}
          </section></>}
    </main>
    <footer className="trip-footer"><span>Plan together. Travel together.</span><span>{session?.user.email && view === 'account' ? session.user.email : 'رحلة / A journey worth sharing.'}</span></footer>
  </div>
}
