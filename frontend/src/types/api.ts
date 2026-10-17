export interface HealthResponse {
  status: 'ok'
  service: 'rihla-api'
}

export type BackendStatus =
  | { state: 'checking' }
  | { state: 'connected'; checkedAt: Date }
  | { state: 'unavailable'; message: string }
