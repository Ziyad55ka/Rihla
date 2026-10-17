import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

interface AuthState { session: Session | null; loading: boolean; error: string }
const AuthContext = createContext<AuthState>({ session: null, loading: true, error: '' })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ session: null, loading: !!supabase, error: '' })
  useEffect(() => {
    if (!supabase) return
    let active = true
    let eventReceived = false
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      // Keep this synchronous: awaiting another SDK call here can deadlock Auth.
      eventReceived = true
      if (active) setState({ session, loading: false, error: '' })
    })
    void supabase.auth.getSession().then(({ data, error }) => {
      if (active && !eventReceived) setState({
        session: data.session, loading: false,
        error: error ? 'Could not restore your session. Please sign in again.' : '',
      })
    }).catch(() => {
      if (active) setState({ session: null, loading: false, error: 'Could not restore your session. Please sign in again.' })
    })
    return () => { active = false; subscription.unsubscribe() }
  }, [])
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
}

// Keeping the consumer here avoids an extra context-only module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() { return useContext(AuthContext) }
