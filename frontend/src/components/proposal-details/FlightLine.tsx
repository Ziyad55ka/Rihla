import { airlineName } from '../../lib/airlines'
import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { durationLabel, localTime } from '../../lib/proposals'
import type { FlightLeg } from '../../types/proposal'
import { PlaneIcon } from './icons'

const clock = (value?: string | null) => /[T ](\d{2}:\d{2})/.exec(value ?? '')?.[1] ?? null

function End({ time, code, city }: { time: string | null; code?: string | null; city: string }) {
  const { locale } = useLanguage()
  return <div className="details-line-end">
    {time && <strong className="details-line-time"><bdi>{localTime(time, locale)}</bdi></strong>}
    {code && <span className="details-line-code"><bdi>{code}</bdi></span>}
    <span className="details-line-city"><bdi>{city}</bdi></span>
  </div>
}

/** One direction, drawn the way flight apps draw it. A stop is a dot with its airport. */
export function FlightLine({ leg, from, to, fromCode, toCode }: { leg: FlightLeg; from: string; to: string; fromCode?: string | null; toCode?: string | null }) {
  const { t, language, locale } = useLanguage()
  const duration = durationLabel(leg.duration.value, language, locale)
  const stops = leg.stops ?? null
  const airports = leg.stop_airports ?? []
  const airline = leg.airline.value
  const stopWords = stops === null ? null : stops === 0 ? t('Nonstop') : stops === 1 ? t('One stop') : stops === 2 ? t('Two stops') : t('{count} stops', { count: stops.toLocaleString(locale) })
  return <div className="details-line">
    <p className="details-line-meta">
      <strong>{t(leg.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
      <span>{calendarDate(leg.date, locale)}</span>
      {airline && <span><bdi>{airlineName(airline, language)}</bdi></span>}
      {leg.flight_number && <span className="details-line-number"><bdi>{leg.flight_number}</bdi></span>}
    </p>
    <div className="details-line-track">
      <End time={clock(leg.departure_time)} code={fromCode} city={from} />
      <div className="details-line-path">
        {duration && <span className="details-line-label"><bdi>{duration}</bdi></span>}
        <div className="details-line-rail">
          <span className="details-line-dot" aria-hidden="true" />
          {Array.from({ length: stops ?? 0 }, (_, index) => {
            const airport = airports[index]
            return <span className="details-line-stop" key={index} tabIndex={airport ? 0 : undefined} aria-label={airport ? t('Stop at {airport}', { airport }) : undefined}>{airport && <span className="details-tip-text" role="tooltip"><bdi>{airport}</bdi></span>}</span>
          })}
          <span className="details-line-plane"><PlaneIcon /></span>
          <span className="details-line-dot" aria-hidden="true" />
        </div>
        {stopWords && <span className="details-line-label">{stopWords}</span>}
      </div>
      <End time={clock(leg.arrival_time)} code={toCode} city={to} />
    </div>
  </div>
}
