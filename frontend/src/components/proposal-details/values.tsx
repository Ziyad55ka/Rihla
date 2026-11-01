import { useLanguage } from '../../lib/language'
import { safeLink, statusLabels } from '../../lib/proposals'
import type { Evidence, InfoField, InfoStatus, ProposalSource, SarPrice } from '../../types/proposal'

export function StatusBadge({ status, short = false }: { status: InfoStatus; short?: boolean }) {
  const { t } = useLanguage()
  return <span className={`planning-badge${status === 'Sourced' ? ' planning-badge--ready' : status === 'Unconfirmed' ? ' planning-badge--conflict' : ' details-badge--neutral'}`}>{t(short && status === 'Unconfirmed' ? 'Unconfirmed' : statusLabels[status])}</span>
}

function EvidenceDetails({ evidence, sources }: { evidence: Evidence[]; sources: ProposalSource[] }) {
  const { t } = useLanguage()
  if (evidence.length === 0) return null
  return <details className="details-evidence">
    <summary>{t('Show evidence')}</summary>
    <ul>{evidence.map((item, index) => {
      const source = sources.find((entry) => entry.id === item.source_id)
      const link = source ? safeLink(source.url) : null
      return <li key={index}>
        <q><bdi>{item.quote}</bdi></q>
        {source && (link ? <a href={link} target="_blank" rel="noopener noreferrer"><bdi>{source.title}</bdi></a> : <bdi>{source.title}</bdi>)}
      </li>
    })}</ul>
  </details>
}

export function InfoValue({ field, sources }: { field: InfoField; sources: ProposalSource[] }) {
  return <span className="details-value">
    <span><bdi>{field.status === 'Not available' || field.value === null ? '—' : field.value}</bdi></span>
    <StatusBadge status={field.status} />
    {field.status !== 'Not available' && <EvidenceDetails evidence={field.evidence} sources={sources} />}
  </span>
}

export function PriceValue({ price, unit, sources }: { price: SarPrice; unit?: string; sources: ProposalSource[] }) {
  const { t, locale } = useLanguage()
  const known = price.status !== 'Not available' && price.amount_sar !== null
  const amount = known ? t('{amount} SAR', { amount: Number(price.amount_sar).toLocaleString(locale) }) : '—'
  return <span className="details-value">
    <span>
      {known && price.status === 'Estimated' ? t('About {amount}', { amount }) : amount}
      {known && unit && ` ${t(unit)}`}
    </span>
    <StatusBadge status={price.status} />
    {known && <EvidenceDetails evidence={price.evidence} sources={sources} />}
  </span>
}

/** Every booking link leaves Rihla. Nothing about a booking is sent back or saved. */
export function BookingLink({ url, label, solid = false }: { url: string | null; label: string; solid?: boolean }) {
  const { t } = useLanguage()
  const link = safeLink(url)
  if (!link) return <p className="details-hint">{t('No booking link')}</p>
  return <div className="details-booking">
    <a className={solid ? 'trip-primary' : 'trip-secondary'} href={link} target="_blank" rel="noopener noreferrer">{label} <span aria-hidden="true">↗</span></a>
    <p className="details-hint">{t('This takes you to the seller’s site. Check the flight and price before paying.')}</p>
  </div>
}
