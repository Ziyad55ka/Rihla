import { useLanguage } from '../lib/language'
import { combineEstimateComponents } from '../lib/activities'
import type { ActivityProposalEstimate, EstimateComponent } from '../types/proposal'

export function ActivityEstimate({ estimate, dirty }: { estimate: ActivityProposalEstimate; dirty: boolean }) {
  const { t, locale } = useLanguage()
  function amount(part: EstimateComponent) {
    const formatted = Number(part.known_amount_sar).toLocaleString(locale, { style: 'currency', currency: 'SAR' })
    if (part.missing_items && part.known_amount_sar === '0.00') return t('Not available')
    return part.missing_items ? t('At least {amount}', { amount: formatted }) : formatted
  }
  const rows: { label: string; value: EstimateComponent }[] = [
    { label: 'Base proposal estimate', value: combineEstimateComponents([estimate.flights, estimate.accommodation, estimate.transport]) },
    { label: 'Saved activities and places', value: estimate.activities },
  ]
  return <section className="activity-estimate" aria-label={t('Proposal estimate per person')}>
    <div className="activity-estimate-heading"><h4>{t('Proposal estimate per person')}</h4><span>{t('Based on saved choices')}</span></div>
    <dl>{rows.map(row => <div key={row.label}><dt>{t(row.label)}</dt><dd>{amount(row.value)}{row.value.missing_items > 0 && <small>{t('Includes unavailable prices')}</small>}</dd></div>)}
      <div className="activity-estimate-total"><dt>{t('Proposal total including saved activities')}</dt><dd data-testid="proposal-estimate-total">{amount(estimate.total)}</dd></div>
    </dl>
    {estimate.total.missing_items > 0 && <p role="status">{t('This is a partial estimate. Unavailable costs are not counted as zero.')}</p>}
    {estimate.total.unconfirmed_items > 0 && <p>{t('This estimate includes unconfirmed prices.')}</p>}
    {estimate.total.estimated_items > 0 && <p>{t('Prices are estimates, not confirmed offers.')}</p>}
    <p>{t('One room per person; transport prices are per person. Only the listed cost categories are included.')}</p>
    {dirty && <p className="activity-estimate-pending" role="status">{t('Save your activity changes to update this proposal estimate.')}</p>}
  </section>
}
