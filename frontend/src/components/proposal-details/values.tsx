import { useLanguage } from '../../lib/language'
import { priceAge, type PriceAgeLimits, safeLink, statusLabels } from '../../lib/proposals'
import type { InfoField, InfoStatus, SarPrice } from '../../types/proposal'
import { useSar } from './useSar'

export function StatusBadge({ status, short = false }: { status: InfoStatus; short?: boolean }) {
  const { t } = useLanguage()
  return <span className={`planning-badge${status === 'Sourced' ? ' planning-badge--ready' : status === 'Unconfirmed' ? ' planning-badge--conflict' : ' details-badge--neutral'}`}>{t(short && status === 'Unconfirmed' ? 'Unconfirmed' : statusLabels[status])}</span>
}

/** A label only when the value is doubtful or missing, so pages do not repeat badges. */
export function InfoValue({ field }: { field: InfoField }) {
  const missing = field.status === 'Not available' || field.value === null
  return <span className="details-value">
    <span><bdi>{missing ? '—' : field.value}</bdi></span>
    {(missing || field.status === 'Unconfirmed') && <StatusBadge status={field.status} />}
  </span>
}

export function PriceValue({ price, unit }: { price: SarPrice; unit?: string }) {
  const { t } = useLanguage()
  const sar = useSar()
  const known = price.status !== 'Not available' && price.amount_sar !== null
  const amount = known ? sar(price.amount_sar as string) : '—'
  return <span className="details-value">
    <span>
      {known && price.status === 'Estimated' ? t('About {amount}', { amount }) : amount}
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
    <p className="details-hint">{t('Prices and availability change, and we cannot guarantee them. Check for enough rooms for the group.')}</p>
  </div>
}
