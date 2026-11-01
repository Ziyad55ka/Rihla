import { useLanguage } from '../../lib/language'
import { useCountUp } from '../../lib/motion'
import { priceAge, type PriceAgeLimits, safeLink, statusLabels } from '../../lib/proposals'
import type { InfoField, InfoStatus, SarPrice } from '../../types/proposal'
import { InfoIcon } from './icons'
import { useSar } from './useSar'

export function StatusBadge({ status }: { status: InfoStatus }) {
  const { t } = useLanguage()
  return <span className={`planning-badge${status === 'Sourced' ? ' planning-badge--ready' : status === 'Unconfirmed' ? ' planning-badge--conflict' : ' details-badge--neutral'}`}>{t(statusLabels[status])}</span>
}

/** A label only when the value is doubtful or missing, so pages do not repeat badges. */
export function InfoValue({ field, display }: { field: InfoField; display?: (value: string) => string }) {
  const missing = field.status === 'Not available' || field.value === null
  return <span className="details-value">
    <span><bdi>{missing ? '—' : display ? display(field.value as string) : field.value}</bdi></span>
    {(missing || field.status === 'Unconfirmed') && <StatusBadge status={field.status} />}
  </span>
}

/** The same note wherever a price is shown, so nobody takes one as final. */
export function PriceNotice() {
  const { t } = useLanguage()
  return <p className="details-notice"><InfoIcon /> <span>{t('Prices and seats change from time to time. The price shown is from the last check, and the final price is confirmed on the booking page.')}</span></p>
}

/** `startsFrom` is for flights: the cheapest fare is rarely the only one. */
export function PriceValue({ price, unit, startsFrom = false }: { price: SarPrice; unit?: string; startsFrom?: boolean }) {
  const { t } = useLanguage()
  const sar = useSar()
  const known = price.status !== 'Not available' && price.amount_sar !== null
  const target = Number(price.amount_sar ?? 0)
  const { value: moving, ref } = useCountUp<HTMLSpanElement>(target)
  // Whole riyals while it glides, then the exact price.
  const amount = known ? sar(moving === target ? target : Math.round(moving)) : '—'
  return <span className="details-value">
    <span ref={ref}>
      {known && startsFrom ? t('From {amount}', { amount }) : known && price.status === 'Estimated' ? t('About {amount}', { amount }) : amount}
      {known && unit && ` ${t(unit)}`}
    </span>
    <StatusBadge status={price.status} />
  </span>
}

export function PriceAgeBadge({ pricedAt, limits, canRefresh = false, now = Date.now() }: { pricedAt?: string | null; limits: PriceAgeLimits; canRefresh?: boolean; now?: number }) {
  const { t, locale } = useLanguage()
  const age = priceAge(pricedAt ?? limits.fallback ?? null, now, limits)
  if (!age) return null
  const count = age.count.toLocaleString(locale)
  const text = age.level === 'old'
    ? t(canRefresh ? 'Old price. Refresh it before booking.' : 'Old price. Check it before booking.')
    : age.level === 'recent'
      ? t('{count} hours ago. It may have changed.', { count })
      : t(age.unit === 'minutes' ? 'Updated {count} minutes ago' : 'Updated {count} hours ago', { count })
  return <span className={`planning-badge details-age details-age--${age.level}`}><span aria-hidden="true">●</span> {text}</span>
}

/** A stay's search page. It does not expire, and it does not confirm a room. */
export function StayLink({ url, label }: { url: string | null; label: string }) {
  const { t } = useLanguage()
  const link = safeLink(url)
  if (!link) return <p className="details-hint">{t('No booking link')}</p>
  return <div className="details-booking">
    <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{label} <span aria-hidden="true">↗</span></a>
    <p className="details-hint">{t('Check for enough rooms for the group.')}</p>
  </div>
}
