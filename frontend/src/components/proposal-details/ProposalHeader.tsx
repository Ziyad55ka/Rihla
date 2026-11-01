import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { budgetStatusLabels, proposalTitle } from '../../lib/proposals'
import type { Proposal } from '../../types/proposal'
import { nightsLabel } from './nights'

function citiesLabel(count: number, t: ReturnType<typeof useLanguage>['t'], locale: string) {
  if (count === 1) return t('One city')
  if (count === 2) return t('Two cities')
  return t('{count} cities', { count: count.toLocaleString(locale) })
}

export function ProposalHeader({ proposal, total }: { proposal: Proposal; total: number }) {
  const { t, locale, language } = useLanguage()
  const nights = proposal.cities.reduce((sum, stay) => sum + stay.nights, 0)
  const summary = [
    calendarDate(proposal.start_date, locale) + ' – ' + calendarDate(proposal.end_date, locale),
    nightsLabel(nights, language, t, locale),
    citiesLabel(proposal.cities.length, t, locale),
  ]
  return <header className="details-hero">
    <p className="trip-eyebrow">{t('Option {number} of {total}', { number: proposal.option_number.toLocaleString(locale), total: total.toLocaleString(locale) })}</p>
    <h1><bdi>{proposalTitle(proposal, language)}</bdi></h1>
    <p className="details-hero-summary"><bdi>{placeName(proposal.destination, language, proposal.destination_ar)}</bdi> · {summary.join(' · ')}</p>
    <span className={`planning-badge${proposal.budget_status === 'within_group_budget' ? ' planning-badge--ready' : ' planning-badge--conflict'}`}>{t(budgetStatusLabels[proposal.budget_status])}</span>
    {proposal.flexible_adjustments.map((item, index) => <p className="details-adjustment" key={index}><strong>{t('Adjustment:')}</strong> <bdi>{item.explanation}</bdi></p>)}
  </header>
}
