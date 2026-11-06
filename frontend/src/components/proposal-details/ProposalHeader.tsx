import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { budgetStatusLabels, proposalTitle } from '../../lib/proposals'
import type { Proposal } from '../../types/proposal'
import { SparkleIcon } from './icons'
import { nightsLabel } from './nights'
import { PlacePhoto } from './PlacePhoto'

function citiesLabel(count: number, t: ReturnType<typeof useLanguage>['t'], locale: string) {
  if (count === 1) return t('One city')
  if (count === 2) return t('Two cities')
  return t('{count} cities', { count: count.toLocaleString(locale) })
}

export function ProposalHeader({ proposal, total, stale = false }: { proposal: Proposal; total: number; stale?: boolean }) {
  const { t, locale, language } = useLanguage()
  const nights = proposal.cities.reduce((sum, stay) => sum + stay.nights, 0)
  const summary = [
    calendarDate(proposal.start_date, locale) + ' – ' + calendarDate(proposal.end_date, locale),
    nightsLabel(nights, language, t, locale),
    citiesLabel(proposal.cities.length, t, locale),
  ]
  const title = proposalTitle(proposal, language)
  const place = placeName(proposal.destination, language, proposal.destination_ar)
  return <header className={`details-hero${proposal.image ? ' details-hero--photo' : ''}`}>
    {proposal.image && <PlacePhoto image={proposal.image} place={place} variant="hero" />}
    <span className="details-ai-badge"><SparkleIcon /> {t('Suggested by AI')}</span>
    <p className="trip-eyebrow">{t('Option {number} of {total}', { number: proposal.option_number.toLocaleString(locale), total: total.toLocaleString(locale) })}</p>
    <h1 aria-label={title}><bdi aria-hidden="true">{title.split(' ').map((word, index) => <span className="details-word" key={index} style={{ animationDelay: `${index * 90 + 150}ms` }}>{word} </span>)}</bdi></h1>
    <p className="details-hero-summary"><bdi>{place}</bdi> · {summary.join(' · ')}</p>
    <span className={`planning-badge${!stale && proposal.budget_status === 'within_group_budget' ? ' planning-badge--ready' : ' planning-badge--conflict'}`}>{t(stale ? 'Regenerate to recheck budget and preferences' : budgetStatusLabels[proposal.budget_status])}</span>
  </header>
}
