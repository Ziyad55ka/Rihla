import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './components/AuthProvider'
import { AuthPage } from './pages/AuthPage'
import { WorkspacePage } from './pages/WorkspacePage'
import { SetupPage } from './pages/SetupPage'
import { readPendingInvitation, rememberInvitation } from './lib/trips'

function CurrentPage() {
  const { session } = useAuth()
  const [pending, setPending] = useState(readPendingInvitation)
  useEffect(() => {
    const acceptLink = () => setPending(readPendingInvitation())
    window.addEventListener('hashchange', acceptLink)
    return () => window.removeEventListener('hashchange', acceptLink)
  }, [])
  useEffect(() => { rememberInvitation(pending) }, [pending])
  if (window.location.pathname === '/setup') return <SetupPage />
  return session
    ? <WorkspacePage key={session.user.id} initialInvitation={pending} onInvitationHandled={() => setPending(null)} />
    : <AuthPage hasPendingInvitation={!!pending} />
}

export default function App() {
  return <AuthProvider><CurrentPage /></AuthProvider>
}
