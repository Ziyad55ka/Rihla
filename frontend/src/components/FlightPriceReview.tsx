import { useEffect, useState } from 'react'
import { Clock3, RefreshCw } from 'lucide-react'
import { flightReview, reviewClock } from '../lib/flightReview'
import { useLanguage } from '../lib/language'
import type { Flights } from '../types/proposal'

export function FlightPriceReview({ routes, minutes = 15, compact = false }: { routes: Flights[]; minutes?: number; compact?: boolean }) {
  const { t, locale } = useLanguage()
  const [now, setNow] = useState(() => Date.now())
  const review = flightReview(routes, minutes, now)
  useEffect(() => {
    setNow(Date.now())
    if (review.state !== 'countdown') return
    const tick = () => { if (!document.hidden) setNow(Date.now()) }
    const timer = window.setInterval(tick, 1000)
    document.addEventListener('visibilitychange', tick)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', tick) }
  }, [review.state, review.dueAt])
  const timed = review.state === 'countdown'
  return <div className={`flight-price-review${timed ? '' : ' flight-price-review--due'}${compact ? ' flight-price-review--compact' : ''}`}>
    <div className="flight-price-review-heading">{timed ? <Clock3 size={18} aria-hidden="true" /> : <RefreshCw size={18} aria-hidden="true" />}<span>{t(timed ? 'Review flight prices in' : review.state === 'unknown' ? 'Check flight prices before choosing' : 'Flight prices need a new check')}</span>
      {timed && <bdi className="flight-price-review-clock" role="timer" aria-live="off" aria-label={t('Time until flight price review')}>{reviewClock(review.seconds, locale)}</bdi>}
    </div>
    {!compact && <p>{t('A review reminder, not a reservation. Prices and availability can change at any time.')}</p>}
  </div>
}
