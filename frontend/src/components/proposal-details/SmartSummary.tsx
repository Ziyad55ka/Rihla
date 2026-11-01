import { useLanguage } from '../../lib/language'
import type { Proposal } from '../../types/proposal'
import { Hint } from './Hint'
import { SparkleIcon } from './icons'
import { nightsLabel } from './nights'

const budgetPoints = {
  within_group_budget: 'Fits the group budget',
  includes_unconfirmed: 'Fits the group budget so far, with some prices to confirm',
  over_group_budget: 'Over the group budget, so it needs a closer look',
}

/** Written from the proposal's own data, with no new AI request and no member's details. */
export function SmartSummary({ proposal }: { proposal: Proposal }) {
  const { t, language, locale } = useLanguage()
  const nights = proposal.cities.reduce((sum, stay) => sum + stay.nights, 0)
  const length = nightsLabel(nights, language, t, locale)
  const labels = proposal.cities.flatMap((stay) => (language === 'ar' ? stay.labels_ar : stay.labels_en) ?? [])
  const direct = proposal.flights.length > 0 && proposal.flights.every((route) => route.legs.every((leg) => leg.stops === 0))
  const points = [
    t(budgetPoints[proposal.budget_status]),
    proposal.cities.length === 1 ? t('{nights} in one city, with time to settle in', { nights: length }) : t('{nights} across {count} cities', { nights: length, count: proposal.cities.length.toLocaleString(locale) }),
    labels.length > 0 ? [...new Set(labels)].slice(0, 2).join(' · ') : direct ? t('Direct flights from your city') : null,
  ].filter((point): point is string => Boolean(point))
  return <section className="details-smart" aria-labelledby="details-smart">
    <h2 id="details-smart" className="details-smart-title"><span className="details-smart-spark"><SparkleIcon /></span>{t('Rihla’s smart summary')}<Hint text={t('Written from this proposal’s details. It never uses any member’s private information.')} /></h2>
    <ul>{points.map((point) => <li key={point}><bdi>{point}</bdi></li>)}</ul>
  </section>
}
