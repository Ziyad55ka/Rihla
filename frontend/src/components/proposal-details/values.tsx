import { useLanguage } from '../../lib/language'
import { priceAge, type PriceAgeLimits, statusLabels } from '../../lib/proposals'
import type { InfoStatus, SarPrice } from '../../types/proposal'
import { ClockIcon, InfoIcon } from './icons'
import { useSar } from './useSar'

export function StatusBadge({ status }: { status: InfoStatus }) {
  const { t } = useLanguage()
  return <span className={`planning-badge${status === 'Sourced' ? ' planning-badge--ready' : status === 'Unconfirmed' ? ' planning-badge--conflict' : ' details-badge--neutral'}`}>{t(statusLabels[status])}</span>
}

/** Said once, above the flights. */
export function PriceNotice() {
  const { t } = useLanguage()
  return <p className="details-notice"><InfoIcon /> <span>{t("Approximate price. This is the base fare at the last check. The final price on the airline's site may be higher depending on your choices, such as seat selection, extra baggage, meals, or payment fees, or if the fare changes before you book.")}</span></p>
}

/** Said once, above the hotels. */
export function StayNotice() {
  const { t } = useLanguage()
  return <p className="details-notice"><InfoIcon /> <span>{t('Approximate nightly price. The final price may be higher depending on room type, taxes, and city fees.')}</span></p>
}

/** `startsFrom` is for flights: the cheapest fare is rarely the only one. */
export function PriceValue({ price, unit, startsFrom = false }: { price: SarPrice; unit?: string; startsFrom?: boolean }) {
  const { t } = useLanguage()
  const sar = useSar()
  const known = price.status !== 'Not available' && price.amount_sar !== null
  // Money must show the quoted amount immediately, including after a refresh.
  const amount = known ? sar(price.amount_sar!) : '—'
  return <span className="details-value">
    <span>
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
  return <span className={`planning-badge details-age details-age--${age.level}`}><ClockIcon /> {text}</span>
}

