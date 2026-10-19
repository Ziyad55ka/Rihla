import { useEffect, useState } from 'react'
import { PlanningPanel } from '../components/PlanningPanel'
import { getTrip } from '../lib/trips'
import type { TripDetail } from '../types/trips'
import { useLanguage } from '../lib/language'
import '../trip-detail.css'

export function TripDetailPage({ tripId, notice, onBack, onPreferences }: { tripId: string; notice: string; onBack: () => void; onPreferences: () => void }) {
  const { t } = useLanguage()
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setAttempt((value) => value + 1) }
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    getTrip(tripId, controller.signal).then((value) => { if (!controller.signal.aborted) setTrip(value) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load this trip.') })
    return () => controller.abort()
  }, [tripId, attempt])
  return <section className="trip-detail-page">
    <button type="button" className="trip-back" onClick={onBack}>← {t('Back to your trips')}</button>
    {error && !trip ? <div className="trip-feedback trip-feedback--error" role="alert">{t(error)}<button type="button" className="trip-text-button" onClick={() => setAttempt((value) => value + 1)}>{t("Try again")}</button></div>
      : !trip ? <p className="trip-loading" role="status">{t('Getting your group together…')}</p>
      : <>{notice && <p className="trip-feedback trip-feedback--success" role="status">{t(notice)}</p>}
        {error && <p className="trip-feedback trip-feedback--error" role="alert">{t("Could not refresh the group.")} {t(error)}</p>}
        <PlanningPanel key={`planning-${trip.id}`} trip={trip} revision={attempt} onRefresh={() => setAttempt((value) => value + 1)} onPreferences={onPreferences} />
      </>}
  </section>
}
