export type WorkspaceRoute =
  | { page: 'trips' | 'create' | 'join' | 'account' }
  | { page: 'detail' | 'preferences'; tripId: string }
  | { page: 'proposal'; tripId: string; proposalId: string }
export type Route = WorkspaceRoute | { page: 'home' | 'login' | 'signup' | 'setup' | 'not-found' }

export function readRoute(path: string): Route {
  const routes: Record<string, Route> = {
    '/': { page: 'home' }, '/login': { page: 'login' }, '/signup': { page: 'signup' },
    '/setup': { page: 'setup' }, '/trips': { page: 'trips' }, '/trips/new': { page: 'create' },
    '/trips/join': { page: 'join' }, '/account': { page: 'account' },
  }
  if (Object.hasOwn(routes, path)) return routes[path]
  const proposal = /^\/trips\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/proposals\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(path)
  if (proposal) return { page: 'proposal', tripId: proposal[1], proposalId: proposal[2] }
  const match = /^\/trips\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(\/preferences)?$/i.exec(path)
  return match ? { page: match[2] ? 'preferences' : 'detail', tripId: match[1] } : { page: 'not-found' }
}

export function isWorkspaceRoute(route: Route): route is WorkspaceRoute {
  return ['trips', 'create', 'join', 'detail', 'preferences', 'proposal', 'account'].includes(route.page)
}

export const navigationEvent = 'rihla:navigation'
export function navigate(path: string, replace = false) {
  if (readRoute(path).page === 'not-found') return
  if (window.location.pathname === path && !window.location.search) return
  window.history[replace ? 'replaceState' : 'pushState'](null, '', path)
  window.dispatchEvent(new Event(navigationEvent))
}

const RETURN_KEY = 'rihla.afterSignIn'
export function rememberReturnPath(path: string | null) {
  try {
    if (path && isWorkspaceRoute(readRoute(path))) sessionStorage.setItem(RETURN_KEY, path)
    else sessionStorage.removeItem(RETURN_KEY)
  } catch { /* The current protected URL still preserves the action if storage is disabled. */ }
}
export function readReturnPath(): string | null {
  try {
    const path = sessionStorage.getItem(RETURN_KEY)
    return path && isWorkspaceRoute(readRoute(path)) ? path : null
  } catch { return null }
}
