import { useLanguage } from './lib/language'
import { lazy, Suspense, useEffect, useState, useSyncExternalStore } from 'react'
import { AuthProvider, useAuth } from './components/AuthProvider'
import { Brand } from './components/Brand'
import { PageMotion } from './components/PageMotion'
import { AuthPage } from './pages/AuthPage'
import { LandingPage } from './pages/LandingPage'
import { SetupPage } from './pages/SetupPage'
import { readPendingInvitation, rememberInvitation } from './lib/trips'
import { LanguageProvider } from './lib/language'
import { isWorkspaceRoute, navigate, navigationEvent, readReturnPath, readRoute, rememberReturnPath } from './lib/navigation'
import './workspace.css'
import './navbar.css'
import './motion.css'

const WorkspacePage = lazy(() => import('./pages/WorkspacePage').then((module) => ({ default: module.WorkspacePage })))

function subscribe(callback: () => void) {
  window.addEventListener('popstate', callback)
  window.addEventListener(navigationEvent, callback)
  return () => { window.removeEventListener('popstate', callback); window.removeEventListener(navigationEvent, callback) }
}
const currentPath = () => window.location.pathname

function CurrentPage() {
  const { t } = useLanguage()
  const { session, loading } = useAuth()
  const path = useSyncExternalStore(subscribe, currentPath)
  const route = readRoute(path)
  const [pending, setPending] = useState(readPendingInvitation)
  useEffect(() => {
    const acceptLink = () => {
      // Supabase owns Auth callback fragments; ordinary page anchors are not invitations.
      if (!new URLSearchParams(window.location.hash.slice(1)).has('invite')) return
      const invitation = readPendingInvitation()
      setPending(invitation)
      if (invitation) navigate('/trips/join')
    }
    const hasInviteFragment = new URLSearchParams(window.location.hash.slice(1)).has('invite')
    if (hasInviteFragment) acceptLink()
    else if (readPendingInvitation() && window.location.pathname === '/' && !window.location.hash) navigate('/trips/join', true)
    window.addEventListener('hashchange', acceptLink)
    return () => window.removeEventListener('hashchange', acceptLink)
  }, [])
  useEffect(() => { rememberInvitation(pending) }, [pending])
  useEffect(() => {
    if (!loading && !session && isWorkspaceRoute(readRoute(path))) rememberReturnPath(path)
    if (session && ['home', 'login', 'signup'].includes(readRoute(path).page)) {
      navigate(pending ? '/trips/join' : readReturnPath() ?? '/trips', true)
    }
    if (session && isWorkspaceRoute(readRoute(path))) rememberReturnPath(null)
  }, [loading, session, path, pending])

  if (route.page === 'setup') return <SetupPage />
  if (route.page === 'not-found') return <div className="route-message"><Brand /><main><p className="trip-eyebrow">{t("LET’S GET YOU BACK ON TRACK")}</p><h1>{t("This page took a detour.")}</h1><button className="trip-primary" onClick={() => navigate('/')}>{t("Back to Rihla")}</button></main></div>
  if (loading) return <div className="route-message"><Brand /><main><p role="status">{t("Opening your Rihla workspace…")}</p></main></div>
  if (session) {
    const destination = readRoute(pending && !isWorkspaceRoute(route) ? '/trips/join' : readReturnPath() ?? '/trips')
    return <Suspense fallback={<div className="route-message"><Brand /><main><p role="status">{t("Opening your trips…")}</p></main></div>}><WorkspacePage key={session.user.id} route={isWorkspaceRoute(route) ? route : isWorkspaceRoute(destination) ? destination : { page: 'trips' }} initialInvitation={pending} onInvitationHandled={() => setPending(null)} /></Suspense>
  }
  if (route.page === 'home') return <LandingPage
    onAction={(action) => { const next = action === 'create' ? '/trips/new' : '/trips/join'; rememberReturnPath(next); navigate(next) }}
    onLogin={() => navigate('/login')} />
  return <AuthPage key={route.page === 'signup' ? 'signup' : 'signin'}
    hasPendingInvitation={!!pending} initialMode={route.page === 'signup' ? 'signup' : 'signin'}
    intent={route.page === 'create' ? 'create' : route.page === 'join' || pending ? 'join' : null}
    onBack={() => { rememberReturnPath(null); navigate('/') }} />
}

export default function App() {
  return <LanguageProvider><AuthProvider><CurrentPage /><PageMotion /></AuthProvider></LanguageProvider>
}
